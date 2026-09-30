/*
 * WiFi station + MQTT 3.1.1 over TLS 1.2 with a pre-shared key (contracts/mqtt.md §2),
 * SNTP, and the `struct mc_io` the wake cycle runs on.
 *
 * Synchronous on purpose: a wake cycle is a short, linear conversation.
 */
#include "hal.h"

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

LOG_MODULE_REGISTER(hal_net, LOG_LEVEL_INF);

#define WIFI_TIMEOUT_S 15
#define IP_TIMEOUT_S 15
#define CONNACK_TIMEOUT_MS 10000
#define ACK_TIMEOUT_MS 5000
#define TLS_TAG 42
#define MAX_IN 1024
#define IN_QUEUE 8
/* TLS_PSK_WITH_AES_128_GCM_SHA256 */
#define CIPHER_PSK_AES128_GCM_SHA256 0x00A8

static struct hal_prov prov;

/* --- WiFi ------------------------------------------------------------------------------------ */

static struct net_mgmt_event_callback net_cb;
static K_SEM_DEFINE(wifi_done, 0, 1);
static K_SEM_DEFINE(ip_ready, 0, 1);
static volatile int wifi_status = -1;

static void net_event(struct net_mgmt_event_callback *cb, uint64_t event, struct net_if *iface)
{
	if (event == NET_EVENT_WIFI_CONNECT_RESULT) {
		const struct wifi_status *st = cb->info;

		wifi_status = st->status;
		k_sem_give(&wifi_done);
	} else if (event == NET_EVENT_IPV4_ADDR_ADD) {
		k_sem_give(&ip_ready);
	}
}

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
				     NET_EVENT_WIFI_CONNECT_RESULT | NET_EVENT_IPV4_ADDR_ADD);
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
	int err = net_mgmt(NET_REQUEST_WIFI_CONNECT, iface, &p, sizeof(p));

	if (err) {
		LOG_ERR("wifi connect request failed: %d", err);
		return err;
	}
	if (k_sem_take(&wifi_done, K_SECONDS(WIFI_TIMEOUT_S)) != 0 || wifi_status != 0) {
		LOG_ERR("wifi: no association (status %d)", wifi_status);
		return -ETIMEDOUT;
	}
	if (k_sem_take(&ip_ready, K_SECONDS(IP_TIMEOUT_S)) != 0) {
		LOG_ERR("wifi: no IP address");
		return -ETIMEDOUT;
	}
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

struct inmsg {
	enum mc_in_kind kind;
	size_t len;
	uint8_t data[MAX_IN];
};
static struct inmsg queue[IN_QUEUE];
static int q_head, q_count;

static void enqueue(enum mc_in_kind kind, const uint8_t *data, size_t len)
{
	if (q_count == IN_QUEUE) {
		LOG_WRN("inbox full, dropping a message");
		return;
	}
	struct inmsg *m = &queue[(q_head + q_count) % IN_QUEUE];

	m->kind = kind;
	m->len = len;
	memcpy(m->data, data, len);
	q_count++;
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
		while (q_count) {
			struct inmsg *m = &queue[q_head];

			cb(cb_user, m->kind, m->data, m->len);
			q_head = (q_head + 1) % IN_QUEUE;
			q_count--;
		}
		int32_t left = (int32_t)(end - k_uptime_get());

		if (left <= 0 || !connected) {
			break;
		}
		pump(MIN(left, 100));
	} while (k_uptime_get() < end || q_count);
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
