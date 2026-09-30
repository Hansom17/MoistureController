/*
 * BLE pairing session, device side (contracts/ble.md §4, §7): handshake authenticated by
 * the PoP, AES-GCM frames, and the provisioning messages. No Bluetooth in here: bytes in
 * (mc_ble_feed), bytes out (mc_ble_take), what the device can do through `struct mc_ble_ops`.
 * Checked against the Python reference with contracts/ble_vectors.json.
 */
#ifndef MC_BLE_H
#define MC_BLE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define MC_BLE_MAX_MSG 1024
#define MC_BLE_MAX_BODY (MC_BLE_MAX_MSG + 16)
#define MC_BLE_POP_LEN 16
#define MC_BLE_SSID_MAX 32
#define MC_BLE_PASSWORD_MAX 64
#define MC_BLE_NETWORKS_MAX 16

/* Why a session ended (mc_ble_feed returned < 0). Handshake failures count against the window. */
enum mc_ble_fail {
	MC_BLE_OK = 0,
	MC_BLE_FAIL_PROTOCOL,  /* not a valid handshake frame */
	MC_BLE_FAIL_VERSION,   /* hello with an unsupported version */
	MC_BLE_FAIL_CONFIRM,   /* the PoP did not match (or an impostor) */
	MC_BLE_FAIL_FRAME,     /* bad tag, counter or size after the handshake */
	MC_BLE_FAIL_CRYPTO,    /* the crypto library failed */
};

enum mc_ble_state { MC_BLE_NEW, MC_BLE_HELLO_ACKED, MC_BLE_OPEN, MC_BLE_FAILED };

struct mc_ble_info {
	char hw_mac[18];
	bool provisioned;
	char device_id[32];     /* only if provisioned */
};

struct mc_ble_net {
	char ssid[MC_BLE_SSID_MAX + 1];
	int8_t rssi;
	bool secure;
};

struct mc_ble_test {
	bool wifi_ok;
	bool mqtt_ok;
	char detail[64];
};

/* What the pairing service can do. Return 0 on success, <0 on failure (-EINVAL: bad values). */
struct mc_ble_ops {
	int (*info)(void *u, struct mc_ble_info *out);
	/* Fills up to `max` entries, strongest first; returns the count or <0. */
	int (*wifi_scan)(void *u, struct mc_ble_net *out, size_t max);
	int (*set_wifi)(void *u, const char *ssid, const char *password);
	int (*set_mqtt)(void *u, const char *device_id, const char *host, int port,
			const uint8_t psk[32]);
	/* Joins WiFi and connects to the broker with the settings above; <0: could not even try. */
	int (*test)(void *u, struct mc_ble_test *out);
	/* Persists the settings; the caller restarts the device after the reply was sent. */
	int (*commit)(void *u);
	void (*abort)(void *u);
};

struct mc_ble_session {
	enum mc_ble_state state;
	enum mc_ble_fail fail;
	uint8_t pop[MC_BLE_POP_LEN];
	uint8_t priv[32];
	uint8_t a[32], b[32], nonce_d[16];
	uint8_t k_enc[16], k_mac[16];
	uint64_t send_ctr, recv_ctr;

	uint8_t rx[2 + MC_BLE_MAX_BODY];
	size_t rx_len;
	uint8_t tx[2 * (2 + MC_BLE_MAX_BODY)];
	size_t tx_len, tx_off;

	const struct mc_ble_ops *ops;
	void *ops_user;
	bool have_wifi, have_mqtt;
	bool commit_done;       /* commit succeeded and was acknowledged: restart now */
	bool aborted;

	/* unit tests only: fixed ephemeral private key and nonce instead of random ones */
	const uint8_t *fixed_priv;
	const uint8_t *fixed_nonce;
};

void mc_ble_init(struct mc_ble_session *s, const uint8_t pop[MC_BLE_POP_LEN],
		 const struct mc_ble_ops *ops, void *ops_user);

/*
 * Bytes written by the app. Complete frames are handled right away (the ops may block,
 * `test` for a long time). Returns 0, or <0 if the session must be closed: `s->fail` says why.
 */
int mc_ble_feed(struct mc_ble_session *s, const uint8_t *data, size_t len);

/* Copies up to `max` bytes of what the device wants to send; returns the count (0 = nothing). */
size_t mc_ble_take(struct mc_ble_session *s, uint8_t *dst, size_t max);
bool mc_ble_has_output(const struct mc_ble_session *s);

/* Wipes the keys (call when the connection ends). */
void mc_ble_close(struct mc_ble_session *s);

/* --- factory partition and label (ble.md §7.6, §7.7) ------------------------------------------ */

#define MC_FACTORY_SIZE 25 /* "MCFP" + version + PoP + CRC32 */
/* Parses the factory page; false if the magic, version or CRC do not match. */
bool mc_factory_parse(const uint8_t page[MC_FACTORY_SIZE], uint8_t pop[MC_BLE_POP_LEN]);

#endif /* MC_BLE_H */
