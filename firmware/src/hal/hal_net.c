/*
 * WiFi station + MQTT 3.1.1 over TLS 1.2 with a pre-shared key (contracts/mqtt.md §2),
 * SNTP, and the `struct mc_io` the wake cycle runs on.
 *
 * Synchronous on purpose: a wake cycle is a short, linear conversation.
 */
#include "hal.h"
#include "mc_payload.h"

#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/net/mqtt.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/sntp.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/tls_credentials.h>
#include <zephyr/net/wifi_mgmt.h>
#ifdef CONFIG_MC_LOW_TX_POWER
#include <esp_wifi.h>
#endif

LOG_MODULE_REGISTER(hal_net, LOG_LEVEL_INF);

#define WIFI_TIMEOUT_S 25
#define IP_TIMEOUT_S 15
#define CONNACK_TIMEOUT_MS 10000
#define ACK_TIMEOUT_MS 5000
#define TLS_TAG 42
#define MAX_IN 1024
/* TLS_PSK_WITH_AES_128_GCM_SHA256 */
#define CIPHER_PSK_AES128_GCM_SHA256 0x00A8

static struct hal_prov prov;

static int io_publish(void *u, const char *suffix, const char *payload, size_t len, bool retain);
static void io_disconnect(void *u);

/* --- WiFi ------------------------------------------------------------------------------------ */

static struct net_mgmt_event_callback net_cb;
static K_SEM_DEFINE(wifi_done, 0, 1);
static K_SEM_DEFINE(ip_ready, 0, 1);
static volatile int wifi_status = -1;

static void net_event(struct net_mgmt_event_callback *cb, uint64_t event, struct net_if *iface)
{
	if (event == NET_EVENT_WIFI_CONNECT_RESULT) {
		const struct wifi_status *st = cb->info;

		LOG_INF("wifi: connect result %d (conn_status %d, disconn_reason %d)", st->status,
			st->conn_status, st->disconn_reason);
		wifi_status = st->status;
		k_sem_give(&wifi_done);
	} else if (event == NET_EVENT_WIFI_DISCONNECT_RESULT) {
		const struct wifi_status *st = cb->info;

		LOG_INF("wifi: disconnected (status %d, reason %d)", st->status, st->disconn_reason);
	} else if (event == NET_EVENT_IPV4_ADDR_ADD) {
		LOG_INF("wifi: got an IPv4 address");
		k_sem_give(&ip_ready);
	}
}

#ifdef CONFIG_MC_WIFI_DIAG
/* After a failed join: what does the board actually see? (2.4 GHz only: no 5 GHz networks.) */
static struct net_mgmt_event_callback scan_cb;
static K_SEM_DEFINE(scan_done, 0, 1);
static int scan_count;
static bool scan_saw_ours;

static void scan_event(struct net_mgmt_event_callback *cb, uint64_t event, struct net_if *iface)
{
	if (event == NET_EVENT_WIFI_SCAN_RESULT) {
		const struct wifi_scan_result *r = cb->info;
		char ssid[WIFI_SSID_MAX_LEN + 1] = {0};

		memcpy(ssid, r->ssid, MIN(r->ssid_length, WIFI_SSID_MAX_LEN));
		scan_count++;
		if (strcmp(ssid, prov.ssid) == 0) {
			scan_saw_ours = true;
		}
		LOG_INF("  seen: '%s' ch %u rssi %d security %s", ssid, r->channel, r->rssi,
			wifi_security_txt(r->security));
	} else if (event == NET_EVENT_WIFI_SCAN_DONE) {
		k_sem_give(&scan_done);
	}
}

static void wifi_diag(struct net_if *iface)
{
	struct wifi_scan_params params = {0};

	scan_count = 0;
	scan_saw_ours = false;
	k_sem_reset(&scan_done);
	net_mgmt_init_event_callback(&scan_cb, scan_event,
				     NET_EVENT_WIFI_SCAN_RESULT | NET_EVENT_WIFI_SCAN_DONE);
	net_mgmt_add_event_callback(&scan_cb);
	LOG_INF("could not join '%s' (%u chars): scanning", prov.ssid, (unsigned)strlen(prov.ssid));
	if (net_mgmt(NET_REQUEST_WIFI_SCAN, iface, &params, sizeof(params)) == 0) {
		k_sem_take(&scan_done, K_SECONDS(10));
	}
	net_mgmt_del_event_callback(&scan_cb);
	LOG_INF("%d networks seen, ours %s", scan_count, scan_saw_ours ? "among them" : "NOT among them");
	if (scan_saw_ours) {
		LOG_WRN("network is visible but the join failed: most likely a wrong password "
			"(WPA2 handshake timeout); check MC_DEV_WIFI_PASSWORD");
	} else {
		LOG_WRN("network not visible: check the name, and that it is 2.4 GHz (an iPhone "
			"hotspot needs \"Maximize Compatibility\")");
	}
}
#endif

static int wifi_up(int32_t *rssi)
{
	struct net_if *iface = net_if_get_first_wifi();

	if (iface == NULL) {
		return -ENODEV;
	}
	k_sem_reset(&wifi_done);
	k_sem_reset(&ip_ready);
	wifi_status = -1;
	net_mgmt_init_event_callback(&net_cb, net_event,
				     NET_EVENT_WIFI_CONNECT_RESULT | NET_EVENT_WIFI_DISCONNECT_RESULT |
				     NET_EVENT_IPV4_ADDR_ADD);
	net_mgmt_add_event_callback(&net_cb);

	struct wifi_connect_req_params p = {
		.ssid = (const uint8_t *)prov.ssid,
		.ssid_length = strlen(prov.ssid),
		.psk = (const uint8_t *)prov.wifi_password,
		.psk_length = strlen(prov.wifi_password),
		.security = prov.wifi_password[0] ? WIFI_SECURITY_TYPE_PSK : WIFI_SECURITY_TYPE_NONE,
		.band = WIFI_FREQ_BAND_2_4_GHZ,
		.channel = WIFI_CHANNEL_ANY,
		.mfp = WIFI_MFP_OPTIONAL,
	};
#ifdef CONFIG_MC_LOW_TX_POWER
	LOG_INF("wifi: transmit power 8 dBm (set: %d)", (int)esp_wifi_set_max_tx_power(32));
#endif
	int err = net_mgmt(NET_REQUEST_WIFI_CONNECT, iface, &p, sizeof(p));

	LOG_INF("wifi: connect request to '%s' returned %d", prov.ssid, err);
	if (err) {
		LOG_ERR("wifi connect request failed: %d", err);
		return err;
	}
	if (k_sem_take(&wifi_done, K_SECONDS(WIFI_TIMEOUT_S)) != 0 || wifi_status != 0) {
		LOG_ERR("wifi: no association (status %d)", wifi_status);
#ifdef CONFIG_MC_WIFI_DIAG
		wifi_diag(iface);
#endif
		return -ETIMEDOUT;
	}
	if (k_sem_take(&ip_ready, K_SECONDS(IP_TIMEOUT_S)) != 0) {
		LOG_ERR("wifi: no IP address");
		return -ETIMEDOUT;
	}
	hal_heap_log("after wifi");
	struct wifi_iface_status st = {0};

	if (net_mgmt(NET_REQUEST_WIFI_IFACE_STATUS, iface, &st, sizeof(st)) == 0) {
		*rssi = st.rssi;
	}
	return 0;
}

static void wifi_down(void)
{
	struct net_if *iface = net_if_get_first_wifi();

	if (iface) {
		net_mgmt(NET_REQUEST_WIFI_DISCONNECT, iface, NULL, 0);
	}
}

/* --- SNTP -------------------------------------------------------------------------------------- */

static int io_sntp(void *u, int64_t *unix_s)
{
	struct zsock_addrinfo hints = {.ai_family = AF_INET, .ai_socktype = SOCK_DGRAM};
	struct zsock_addrinfo *ai = NULL;
	struct sntp_ctx ctx;
	struct sntp_time ts;

	if (zsock_getaddrinfo(CONFIG_MC_NTP_SERVER, "123", &hints, &ai) != 0 || ai == NULL) {
		return -EHOSTUNREACH;
	}
	int err = sntp_init(&ctx, ai->ai_addr, ai->ai_addrlen);

	zsock_freeaddrinfo(ai);
	if (err < 0) {
		return err;
	}
	err = sntp_query(&ctx, 4000, &ts);
	sntp_close(&ctx);
	if (err == 0) {
		*unix_s = (int64_t)ts.seconds;
	}
	return err;
}

/* --- MQTT ---------------------------------------------------------------------------------------- */

static struct mqtt_client client;
static uint8_t rx_buf[2048], tx_buf[2048];
static struct sockaddr_storage broker;
static struct zsock_pollfd fds[1];
static char topic_prefix[48];
static char will_topic[64];
static char will_msg[32];
static bool connected;
static volatile bool connack_ok, connack_seen;
static volatile uint16_t acked_id, suback_id;
static uint16_t next_id = 1;

/* Inbound messages wait in a byte ring: [kind:1][len:2][payload]. Mostly small commands, now and
 * then a 1 KB config; a fixed array of full-size slots would waste most of it. */
#define INBOX_BYTES 4096
static uint8_t inbox_ring[INBOX_BYTES];
static size_t inbox_head, inbox_used;

static void ring_put(const uint8_t *d, size_t n)
{
	for (size_t i = 0; i < n; i++) {
		inbox_ring[(inbox_head + inbox_used + i) % INBOX_BYTES] = d[i];
	}
	inbox_used += n;
}

static void ring_get(uint8_t *d, size_t n)
{
	for (size_t i = 0; i < n; i++) {
		d[i] = inbox_ring[(inbox_head + i) % INBOX_BYTES];
	}
	inbox_head = (inbox_head + n) % INBOX_BYTES;
	inbox_used -= n;
}

static void enqueue(enum mc_in_kind kind, const uint8_t *data, size_t len)
{
	uint8_t hdr[3] = {(uint8_t)kind, (uint8_t)(len >> 8), (uint8_t)len};

	if (inbox_used + sizeof(hdr) + len > INBOX_BYTES) {
		LOG_WRN("inbox full, dropping a message");
		return;
	}
	ring_put(hdr, sizeof(hdr));
	ring_put(data, len);
}

static void on_publish(const struct mqtt_evt *evt)
{
	const struct mqtt_publish_param *p = &evt->param.publish;
	size_t tlen = p->message.topic.topic.size, len = p->message.payload.len;
	const char *suffix = NULL;
	uint8_t buf[MAX_IN];

	if (tlen > strlen(topic_prefix) &&
	    strncmp((const char *)p->message.topic.topic.utf8, topic_prefix, strlen(topic_prefix)) == 0) {
		suffix = (const char *)p->message.topic.topic.utf8 + strlen(topic_prefix);
		tlen -= strlen(topic_prefix);
	}
	bool wanted = suffix && len <= MAX_IN &&
		      ((tlen == 3 && strncmp(suffix, "cmd", 3) == 0) ||
		       (tlen == 14 && strncmp(suffix, "config/desired", 14) == 0));
	size_t got = 0;

	/* the payload must be consumed from the socket even if we don't want it */
	while (got < len) {
		int n = mqtt_read_publish_payload_blocking(&client, buf, MIN(len - got, sizeof(buf)));

		if (n <= 0) {
			return;
		}
		if (wanted && got == 0 && (size_t)n == len) {
			enqueue(suffix[0] == 'c' && tlen == 3 ? MC_IN_CMD : MC_IN_CONFIG, buf, len);
		}
		got += n;
	}
	if (p->message.topic.qos == MQTT_QOS_1_AT_LEAST_ONCE) {
		struct mqtt_puback_param ack = {.message_id = p->message_id};

		mqtt_publish_qos1_ack(&client, &ack);
	}
}

static void mqtt_evt(struct mqtt_client *c, const struct mqtt_evt *evt)
{
	switch (evt->type) {
	case MQTT_EVT_CONNACK:
		connack_seen = true;
		connack_ok = evt->result == 0;
		break;
	case MQTT_EVT_DISCONNECT:
		connected = false;
		break;
	case MQTT_EVT_PUBACK:
		acked_id = evt->param.puback.message_id;
		break;
	case MQTT_EVT_SUBACK:
		suback_id = evt->param.suback.message_id;
		break;
	case MQTT_EVT_PUBLISH:
		on_publish(evt);
		break;
	default:
		break;
	}
}

/* Handles incoming packets and keep-alive for up to `timeout_ms`. */
static int pump(int32_t timeout_ms)
{
	if (!connected) {
		return -ENOTCONN;
	}
	fds[0].fd = client.transport.tls.sock;
	fds[0].events = ZSOCK_POLLIN;
	int r = zsock_poll(fds, 1, timeout_ms);

	if (r < 0) {
		return -errno;
	}
	if (r > 0) {
		if (fds[0].revents & ZSOCK_POLLIN) {
			int err = mqtt_input(&client);

			if (err < 0) {
				connected = false;
				return err;
			}
		}
		if (fds[0].revents & (ZSOCK_POLLERR | ZSOCK_POLLHUP | ZSOCK_POLLNVAL)) {
			connected = false;
			return -ECONNRESET;
		}
	}
	return mqtt_live(&client) == -EAGAIN ? 0 : 0;
}

static int resolve_broker(void)
{
	struct zsock_addrinfo hints = {.ai_family = AF_INET, .ai_socktype = SOCK_STREAM};
	struct zsock_addrinfo *ai = NULL;
	char port[8];

	snprintk(port, sizeof(port), "%u", prov.port);
	if (zsock_getaddrinfo(prov.host, port, &hints, &ai) != 0 || ai == NULL) {
		LOG_ERR("cannot resolve %s", prov.host);
		return -EHOSTUNREACH;
	}
	memcpy(&broker, ai->ai_addr, ai->ai_addrlen);
	zsock_freeaddrinfo(ai);
	return 0;
}

static int install_psk(void)
{
	tls_credential_delete(TLS_TAG, TLS_CREDENTIAL_PSK);
	tls_credential_delete(TLS_TAG, TLS_CREDENTIAL_PSK_ID);
	int err = tls_credential_add(TLS_TAG, TLS_CREDENTIAL_PSK_ID, prov.device_id,
				     strlen(prov.device_id));

	if (err) {
		return err;
	}
	return tls_credential_add(TLS_TAG, TLS_CREDENTIAL_PSK, prov.psk, sizeof(prov.psk));
}

static int mqtt_up(const char *will, size_t will_len)
{
	static const sec_tag_t tags[] = {TLS_TAG};
	static const int ciphers[] = {CIPHER_PSK_AES128_GCM_SHA256};
	static struct mqtt_topic lwt_topic;
	static struct mqtt_utf8 lwt_msg;
	int err = resolve_broker();

	if (err) {
		return err;
	}
	if ((err = install_psk())) {
		LOG_ERR("psk credential: %d", err);
		return err;
	}
	snprintk(topic_prefix, sizeof(topic_prefix), "mc/v1/%s/", prov.device_id);
	snprintk(will_topic, sizeof(will_topic), "%sstatus", topic_prefix);
	memcpy(will_msg, will, MIN(will_len, sizeof(will_msg)));

	mqtt_client_init(&client);
	client.broker = &broker;
	client.evt_cb = mqtt_evt;
	client.client_id.utf8 = (uint8_t *)prov.device_id; /* = PSK identity; no user/password (§2) */
	client.client_id.size = strlen(prov.device_id);
	client.password = NULL;
	client.user_name = NULL;
	client.protocol_version = MQTT_VERSION_3_1_1;
	client.clean_session = 0;                /* the broker queues QoS 1 while we sleep */
	client.keepalive = 60;
	client.rx_buf = rx_buf;
	client.rx_buf_size = sizeof(rx_buf);
	client.tx_buf = tx_buf;
	client.tx_buf_size = sizeof(tx_buf);
	lwt_topic.topic.utf8 = (uint8_t *)will_topic;
	lwt_topic.topic.size = strlen(will_topic);
	lwt_topic.qos = MQTT_QOS_1_AT_LEAST_ONCE;
	lwt_msg.utf8 = (uint8_t *)will_msg;
	lwt_msg.size = MIN(will_len, sizeof(will_msg));
	client.will_topic = &lwt_topic;
	client.will_message = &lwt_msg;
	client.will_retain = 1;
	client.transport.type = MQTT_TRANSPORT_SECURE;
	struct mqtt_sec_config *tls = &client.transport.tls.config;

	tls->peer_verify = TLS_PEER_VERIFY_NONE; /* the key is the authentication */
	tls->cipher_list = ciphers;
	tls->cipher_count = 1;
	tls->sec_tag_list = tags;
	tls->sec_tag_count = 1;
	tls->hostname = NULL;

	connack_seen = connack_ok = false;
	connected = false;
	if ((err = mqtt_connect(&client)) < 0) {
		LOG_ERR("mqtt_connect: %d", err);
		return err;
	}
	connected = true;
	hal_heap_log("after tls connect");
	int64_t deadline = k_uptime_get() + CONNACK_TIMEOUT_MS;

	while (!connack_seen && connected && k_uptime_get() < deadline) {
		pump(200);
	}
	if (!connack_seen || !connack_ok) {
		LOG_ERR("mqtt: no CONNACK");
		mqtt_abort(&client);
		connected = false;
		return -ECONNREFUSED;
	}
	return 0;
}

static int subscribe_all(void)
{
	static char t_cmd[64], t_cfg[64];
	struct mqtt_topic topics[2] = {{.qos = MQTT_QOS_1_AT_LEAST_ONCE},
				       {.qos = MQTT_QOS_1_AT_LEAST_ONCE}};

	snprintk(t_cmd, sizeof(t_cmd), "%scmd", topic_prefix);
	snprintk(t_cfg, sizeof(t_cfg), "%sconfig/desired", topic_prefix);
	topics[0].topic.utf8 = (uint8_t *)t_cmd;
	topics[0].topic.size = strlen(t_cmd);
	topics[1].topic.utf8 = (uint8_t *)t_cfg;
	topics[1].topic.size = strlen(t_cfg);

	struct mqtt_subscription_list list = {.list = topics, .list_count = 2,
					      .message_id = next_id++};
	int err = mqtt_subscribe(&client, &list);

	if (err < 0) {
		return err;
	}
	int64_t deadline = k_uptime_get() + ACK_TIMEOUT_MS;

	while (suback_id != list.message_id && connected && k_uptime_get() < deadline) {
		pump(200);
	}
	return suback_id == list.message_id ? 0 : -ETIMEDOUT;
}

/* --- pairing support (ble.md §7.5) ----------------------------------------------------------------------- */

static struct net_mgmt_event_callback list_cb;
static K_SEM_DEFINE(list_done, 0, 1);
static struct mc_ble_net *list_out;
static size_t list_max, list_n;

static void list_event(struct net_mgmt_event_callback *cb, uint64_t event, struct net_if *iface)
{
	if (event == NET_EVENT_WIFI_SCAN_RESULT) {
		const struct wifi_scan_result *r = cb->info;
		char ssid[MC_BLE_SSID_MAX + 1] = {0};

		memcpy(ssid, r->ssid, MIN(r->ssid_length, MC_BLE_SSID_MAX));
		if (ssid[0] == '\0') {
			return; /* hidden network */
		}
		for (size_t i = 0; i < list_n; i++) { /* same name on several APs: keep the strongest */
			if (strcmp(list_out[i].ssid, ssid) == 0) {
				if (r->rssi > list_out[i].rssi) {
					list_out[i].rssi = r->rssi;
				}
				return;
			}
		}
		if (list_n < list_max) {
			strcpy(list_out[list_n].ssid, ssid);
			list_out[list_n].rssi = r->rssi;
			list_out[list_n].secure = r->security != WIFI_SECURITY_TYPE_NONE;
			list_n++;
		}
	} else if (event == NET_EVENT_WIFI_SCAN_DONE) {
		k_sem_give(&list_done);
	}
}

int hal_net_wifi_scan(struct mc_ble_net *out, size_t max)
{
	struct net_if *iface = net_if_get_first_wifi();
	struct wifi_scan_params params = {0};

	if (iface == NULL) {
		return -ENODEV;
	}
	list_out = out;
	list_max = max;
	list_n = 0;
	k_sem_reset(&list_done);
	net_mgmt_init_event_callback(&list_cb, list_event,
				     NET_EVENT_WIFI_SCAN_RESULT | NET_EVENT_WIFI_SCAN_DONE);
	net_mgmt_add_event_callback(&list_cb);
	int err = net_mgmt(NET_REQUEST_WIFI_SCAN, iface, &params, sizeof(params));

	if (err == 0) {
		k_sem_take(&list_done, K_SECONDS(10));
	}
	net_mgmt_del_event_callback(&list_cb);
	if (err) {
		return err;
	}
	for (size_t i = 1; i < list_n; i++) { /* strongest first */
		struct mc_ble_net tmp = out[i];
		size_t j = i;

		while (j > 0 && out[j - 1].rssi < tmp.rssi) {
			out[j] = out[j - 1];
			j--;
		}
		out[j] = tmp;
	}
	return (int)list_n;
}

int hal_net_test(const struct hal_prov *p, struct mc_ble_test *out)
{
	struct hal_prov saved = prov;
	int32_t rssi = 0;
	char payload[96];
	static const char will[] = "{\"state\":\"offline\"}";

	memset(out, 0, sizeof(*out));
	prov = *p;
	if (wifi_up(&rssi) != 0) {
		strcpy(out->detail, "could not join the WiFi");
		goto done;
	}
	out->wifi_ok = true;
	int err = mqtt_up(will, strlen(will));

	if (err == 0) {
		err = subscribe_all();
	}
	if (err != 0) {
		snprintk(out->detail, sizeof(out->detail), "broker: error %d (address, key?)", err);
		goto done;
	}
	int n = mc_enc_status_online(payload, sizeof(payload), 0);

	if (n > 0 && io_publish(NULL, "status", payload, (size_t)n, true) == 0) {
		out->mqtt_ok = true;
	} else {
		strcpy(out->detail, "connected, but the broker took no message");
	}
done:
	io_disconnect(NULL);
	prov = saved;
	return 0;
}

/* --- struct mc_io ------------------------------------------------------------------------------------ */

static int io_connect(void *u, const char *will, size_t will_len, int32_t *rssi, int32_t *wifi_ms)
{
	int64_t t0 = k_uptime_get();
	int err = wifi_up(rssi);

	if (err == 0) {
		err = mqtt_up(will, will_len);
	}
	if (err == 0) {
		err = subscribe_all();
	}
	if (err) {
		wifi_down();
		return err;
	}
	*wifi_ms = (int32_t)(k_uptime_get() - t0);
	return 0;
}

static int io_publish(void *u, const char *suffix, const char *payload, size_t len, bool retain)
{
	char topic[64];

	snprintk(topic, sizeof(topic), "%s%s", topic_prefix, suffix);
	struct mqtt_publish_param p = {
		.message.topic.qos = MQTT_QOS_1_AT_LEAST_ONCE,
		.message.topic.topic.utf8 = (uint8_t *)topic,
		.message.topic.topic.size = strlen(topic),
		.message.payload.data = (uint8_t *)payload,
		.message.payload.len = len,
		.message_id = next_id++,
		.dup_flag = 0,
		.retain_flag = retain ? 1 : 0,
	};

	if (next_id == 0) {
		next_id = 1;
	}
	if (!connected || mqtt_publish(&client, &p) < 0) {
		return -ECONNRESET;
	}
	int64_t deadline = k_uptime_get() + ACK_TIMEOUT_MS;

	while (acked_id != p.message_id && connected && k_uptime_get() < deadline) {
		pump(200);
	}
	return acked_id == p.message_id ? 0 : -ETIMEDOUT;
}

static void io_poll(void *u, int32_t timeout_ms, mc_in_fn cb, void *cb_user)
{
	int64_t end = k_uptime_get() + timeout_ms;

	do {
		while (inbox_used) {
			static uint8_t msg[MAX_IN];
			uint8_t hdr[3];

			ring_get(hdr, sizeof(hdr));
			size_t len = ((size_t)hdr[1] << 8) | hdr[2];

			ring_get(msg, len);
			cb(cb_user, (enum mc_in_kind)hdr[0], msg, len);
		}
		int32_t left = (int32_t)(end - k_uptime_get());

		if (left <= 0 || !connected) {
			break;
		}
		pump(MIN(left, 100));
	} while (k_uptime_get() < end || inbox_used);
}

static void io_disconnect(void *u)
{
	if (connected) {
		mqtt_disconnect(&client, NULL); /* clean: the Last Will stays quiet */
		connected = false;
	}
	mqtt_abort(&client);
	wifi_down();
}

static int io_read_adc(void *u, const struct mc_slot *s, int32_t *raw)
{
	return hal_board_read_adc(s->pin, raw);
}

static int32_t io_battery(void *u)
{
	return hal_board_battery_mv();
}

static void io_pump(void *u, const struct mc_slot *s, bool on, bool hold)
{
	hal_board_pump(s->pin, s->active_high, on, hold);
}

static void io_delay(void *u, int32_t ms)
{
	k_msleep(ms);
}

static void io_identify(void *u, int32_t seconds)
{
	hal_board_identify(seconds);
}

static uint32_t io_uptime(void *u)
{
	return (uint32_t)k_uptime_get();
}

static int io_save(void *u, const struct mc_config *c)
{
	return hal_store_save_config(c);
}

static void io_log(void *u, const char *msg)
{
	LOG_INF("%s", msg);
}

void hal_net_set_prov(const struct hal_prov *p)
{
	prov = *p;
}

const struct mc_io hal_io = {
	.read_adc = io_read_adc,
	.battery_mv = io_battery,
	.pump_set = io_pump,
	.delay_ms = io_delay,
	.identify = io_identify,
	.uptime_ms = io_uptime,
	.sntp = io_sntp,
	.save_config = io_save,
	.connect = io_connect,
	.publish = io_publish,
	.poll = io_poll,
	.disconnect = io_disconnect,
	.log = io_log,
};
