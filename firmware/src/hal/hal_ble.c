/*
 * BLE pairing service (contracts/ble.md): GATT, advertising, pairing window.
 * The protocol itself is src/core/mc_ble.c; this file only moves bytes and runs the window.
 */
#include "hal.h"

#include <string.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#ifdef CONFIG_MC_LOW_TX_POWER
#include <esp_bt.h>
#endif

LOG_MODULE_REGISTER(hal_ble, LOG_LEVEL_INF);

#define UUID_SERVICE BT_UUID_128_ENCODE(0x6d630001, 0x8a3f, 0x4b6e, 0x9d2c, 0x7f1e5a9b0c01)
#define UUID_RX BT_UUID_128_ENCODE(0x6d630002, 0x8a3f, 0x4b6e, 0x9d2c, 0x7f1e5a9b0c01)
#define UUID_TX BT_UUID_128_ENCODE(0x6d630003, 0x8a3f, 0x4b6e, 0x9d2c, 0x7f1e5a9b0c01)

#define MAX_CHUNK 244            /* ATT_MTU 247 - 3 */
#define CONFIRM_TIMEOUT_S 10     /* ble.md §7.3 */
#define MAX_FAILED_HANDSHAKES 5  /* ble.md §3 */

static struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(UUID_SERVICE);
static struct bt_uuid_128 rx_uuid = BT_UUID_INIT_128(UUID_RX);
static struct bt_uuid_128 tx_uuid = BT_UUID_INIT_128(UUID_TX);

struct chunk {
	uint8_t len;
	uint8_t data[MAX_CHUNK];
};
K_MSGQ_DEFINE(rxq, sizeof(struct chunk), 8, 4);
static K_SEM_DEFINE(event, 0, 1);

static struct mc_ble_session session;
static struct bt_conn *conn;
static bool notify_enabled;
static bool advertising;
static bool window_open;
static uint8_t window_pop[MC_BLE_POP_LEN];
static volatile int failed_handshakes;
static volatile bool paired;
static char adv_name[16];

/* What `set_wifi` / `set_mqtt` collect until `commit`. */
static struct hal_prov pending;

/* --- GATT ------------------------------------------------------------------------------------------------- */

static ssize_t on_write(struct bt_conn *c, const struct bt_gatt_attr *attr, const void *buf,
			uint16_t len, uint16_t offset, uint8_t flags)
{
	struct chunk ch;

	if (offset != 0 || len == 0 || len > MAX_CHUNK) {
		return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
	}
	ch.len = (uint8_t)len;
	memcpy(ch.data, buf, len);
	if (k_msgq_put(&rxq, &ch, K_NO_WAIT) != 0) {
		return BT_GATT_ERR(BT_ATT_ERR_INSUFFICIENT_RESOURCES);
	}
	return len;
}

static void tx_ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
	notify_enabled = value == BT_GATT_CCC_NOTIFY;
}

BT_GATT_SERVICE_DEFINE(mc_svc, BT_GATT_PRIMARY_SERVICE(&svc_uuid),
		       BT_GATT_CHARACTERISTIC(&rx_uuid.uuid, BT_GATT_CHRC_WRITE, BT_GATT_PERM_WRITE,
					      NULL, on_write, NULL),
		       BT_GATT_CHARACTERISTIC(&tx_uuid.uuid, BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_NONE,
					      NULL, NULL, NULL),
		       BT_GATT_CCC(tx_ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE));

#define TX_ATTR (&mc_svc.attrs[4])

/* --- provisioning operations ------------------------------------------------------------------------------- */

static int op_info(void *u, struct mc_ble_info *out)
{
	bt_addr_le_t addr[CONFIG_BT_ID_MAX];
	size_t n = ARRAY_SIZE(addr);
	struct hal_prov cur;

	bt_id_get(addr, &n);
	if (n > 0) {
		const uint8_t *a = addr[0].a.val;

		snprintk(out->hw_mac, sizeof(out->hw_mac), "%02X:%02X:%02X:%02X:%02X:%02X", a[5], a[4],
			 a[3], a[2], a[1], a[0]);
	}
	out->provisioned = hal_store_load_prov(&cur);
	if (out->provisioned) {
		strncpy(out->device_id, cur.device_id, sizeof(out->device_id) - 1);
	}
	return 0;
}

static int op_scan(void *u, struct mc_ble_net *out, size_t max)
{
	return hal_net_wifi_scan(out, max);
}

static int op_set_wifi(void *u, const char *ssid, const char *password)
{
	memset(pending.ssid, 0, sizeof(pending.ssid));
	memset(pending.wifi_password, 0, sizeof(pending.wifi_password));
	strncpy(pending.ssid, ssid, sizeof(pending.ssid) - 1);
	strncpy(pending.wifi_password, password, sizeof(pending.wifi_password) - 1);
	return 0;
}

static int op_set_mqtt(void *u, const char *device_id, const char *host, int port,
		       const uint8_t psk[32])
{
	memset(pending.device_id, 0, sizeof(pending.device_id));
	memset(pending.host, 0, sizeof(pending.host));
	strncpy(pending.device_id, device_id, sizeof(pending.device_id) - 1);
	strncpy(pending.host, host, sizeof(pending.host) - 1);
	pending.port = (uint16_t)port;
	memcpy(pending.psk, psk, sizeof(pending.psk));
	return 0;
}

static int op_test(void *u, struct mc_ble_test *out)
{
	return hal_net_test(&pending, out);
}

static int op_commit(void *u)
{
	/* a new pairing is a new identity: the old config and cycle state belong to the old one */
	int err = hal_store_save_prov(&pending);

	if (err == 0) {
		hal_store_clear_config();
		hal_rtc_clear();
		LOG_INF("paired as %s, gateway %s:%u", pending.device_id, pending.host, pending.port);
	}
	return err;
}

static void op_abort(void *u)
{
	memset(&pending, 0, sizeof(pending));
}

static const struct mc_ble_ops pairing_ops = {
	.info = op_info, .wifi_scan = op_scan, .set_wifi = op_set_wifi, .set_mqtt = op_set_mqtt,
	.test = op_test, .commit = op_commit, .abort = op_abort,
};

/* --- connection handling ------------------------------------------------------------------------------------ */

static void confirm_timeout(struct k_work *work)
{
	if (conn && session.state != MC_BLE_OPEN) {
		LOG_WRN("no valid handshake within %d s", CONFIRM_TIMEOUT_S);
		failed_handshakes++;
		bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
		k_sem_give(&event);
	}
}
static K_WORK_DELAYABLE_DEFINE(confirm_work, confirm_timeout);

static void on_connected(struct bt_conn *c, uint8_t err)
{
	if (err || conn) {
		return;
	}
	conn = bt_conn_ref(c);
	advertising = false;
	notify_enabled = false;
	k_msgq_purge(&rxq);
	mc_ble_init(&session, window_pop, &pairing_ops, NULL);
	memset(&pending, 0, sizeof(pending));
	k_work_reschedule(&confirm_work, K_SECONDS(CONFIRM_TIMEOUT_S));
	hal_board_led(HAL_LED_CONNECTED);
	LOG_INF("app connected");
}

static void on_disconnected(struct bt_conn *c, uint8_t reason)
{
	if (c != conn) {
		return;
	}
	k_work_cancel_delayable(&confirm_work);
	mc_ble_close(&session);
	bt_conn_unref(conn);
	conn = NULL;
	notify_enabled = false;
	k_msgq_purge(&rxq);
	LOG_INF("app disconnected (0x%02x)", reason);
	if (window_open) {
		hal_board_led(HAL_LED_PAIRING);
	}
	k_sem_give(&event);
}

BT_CONN_CB_DEFINE(conn_cbs) = {.connected = on_connected, .disconnected = on_disconnected};

/* --- worker: frames in, replies out ---------------------------------------------------------------------------- */

static void flush_tx(void)
{
	uint8_t buf[MAX_CHUNK];

	while (conn && mc_ble_has_output(&session)) {
		uint16_t mtu = bt_gatt_get_mtu(conn);
		size_t max = MIN((size_t)(mtu > 3 ? mtu - 3 : 20), sizeof(buf));
		size_t n = mc_ble_take(&session, buf, max);

		for (int tries = 0; tries < 200 && conn; tries++) {
			int err = notify_enabled ? bt_gatt_notify(conn, TX_ATTR, buf, n) : -ENOTCONN;

			if (err == 0) {
				break;
			}
			if (err != -ENOMEM) {
				LOG_ERR("notify failed: %d (are notifications enabled?)", err);
				return;
			}
			k_msleep(10); /* out of buffers: wait for the controller */
		}
	}
}

static void worker(void *a, void *b, void *c)
{
	struct chunk ch;

	while (true) {
		/* k_msgq_purge() (connect / disconnect) wakes this with an error and no data */
		if (k_msgq_get(&rxq, &ch, K_FOREVER) != 0 || conn == NULL) {
			continue;
		}
		bool was_open = session.state == MC_BLE_OPEN;
		int rc = mc_ble_feed(&session, ch.data, ch.len);

		flush_tx();
		if (rc < 0) {
			LOG_WRN("session ended: reason %d", session.fail);
			if (!was_open && (session.fail == MC_BLE_FAIL_PROTOCOL ||
					  session.fail == MC_BLE_FAIL_VERSION ||
					  session.fail == MC_BLE_FAIL_CONFIRM)) {
				failed_handshakes++; /* ble.md §3: five and the window closes */
			}
			if (conn) {
				bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
			}
		} else if (session.state == MC_BLE_OPEN && !was_open) {
			k_work_cancel_delayable(&confirm_work);
			LOG_INF("secure session open");
		}
		if (session.commit_done && !mc_ble_has_output(&session)) {
			paired = true;
		}
		k_sem_give(&event);
	}
}
K_THREAD_DEFINE(ble_worker, 6144, worker, NULL, NULL, NULL, 5, 0, 0);

/* --- advertising and the window ------------------------------------------------------------------------------------ */

static int advertise(void)
{
	const struct bt_data ad[] = {
		BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR),
		BT_DATA(BT_DATA_NAME_COMPLETE, adv_name, strlen(adv_name)),
	};
	const struct bt_data sd[] = {BT_DATA_BYTES(BT_DATA_UUID128_ALL, UUID_SERVICE)};
	int err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));

	if (err && err != -EALREADY) {
		LOG_ERR("advertising failed: %d", err);
		return err;
	}
	advertising = true;
	return 0;
}

int hal_ble_init(void)
{
	int err = bt_enable(NULL);

	if (err) {
		LOG_ERR("bluetooth init failed: %d", err);
		return err;
	}
	hal_heap_log("after bluetooth");
#ifdef CONFIG_MC_LOW_TX_POWER
	esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_DEFAULT, ESP_PWR_LVL_N9);
	esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV, ESP_PWR_LVL_N9);
	LOG_INF("bluetooth transmit power lowered (MC_LOW_TX_POWER)");
#endif
	bt_addr_le_t addr[CONFIG_BT_ID_MAX];
	size_t n = ARRAY_SIZE(addr);

	bt_id_get(addr, &n);
	snprintk(adv_name, sizeof(adv_name), "MC-%02X%02X", n ? addr[0].a.val[1] : 0,
		 n ? addr[0].a.val[0] : 0); /* last four hex digits of the MAC (ble.md §3) */
	bt_set_name(adv_name);
	return 0;
}

enum hal_ble_result hal_ble_pairing_window(const uint8_t pop[MC_BLE_POP_LEN], int32_t window_s)
{
	enum hal_ble_result result = HAL_BLE_TIMEOUT;
	int64_t deadline = k_uptime_get() + (int64_t)window_s * 1000;

	memcpy(window_pop, pop, MC_BLE_POP_LEN);
	failed_handshakes = 0;
	paired = false;
	window_open = true;
	hal_board_led(HAL_LED_PAIRING);
	if (advertise()) {
		window_open = false;
		return HAL_BLE_ERROR;
	}
	LOG_INF("pairing window open for %d s as '%s'", window_s, adv_name);

	while (k_uptime_get() < deadline) {
		k_sem_take(&event, K_MSEC(250));
		if (paired) {
			result = HAL_BLE_PAIRED;
			break;
		}
		if (failed_handshakes >= MAX_FAILED_HANDSHAKES) {
			LOG_WRN("%d failed handshakes: window closed", failed_handshakes);
			result = HAL_BLE_LOCKED;
			break;
		}
		if (conn == NULL && !advertising) {
			advertise();
		}
	}
	window_open = false;
	bt_le_adv_stop();
	advertising = false;
	if (result == HAL_BLE_PAIRED) {
		k_msleep(500); /* let the last notification leave */
	}
	/* `conn` is cleared by the Bluetooth thread when the app hangs up: read it once, after waiting */
	struct bt_conn *c = conn;

	if (c) {
		bt_conn_disconnect(c, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
		k_msleep(300);
	}
	hal_board_led(HAL_LED_OFF);
	return result;
}
