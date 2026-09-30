#include "mc_ble.h"

#include <errno.h>
#include <psa/crypto.h>
#include <string.h>
#include <zephyr/data/json.h>
#include <zephyr/sys/base64.h>
#include <zephyr/sys/crc.h>
#include <zephyr/sys/util.h>

#include "mc_json.h"

#define VERSION 1
#define DIR_APP_TO_DEV 0
#define DIR_DEV_TO_APP 1

/* --- crypto (PSA) ----------------------------------------------------------------------------------- */

static void clamp(uint8_t k[32])
{
	k[0] &= 248;
	k[31] &= 127;
	k[31] |= 64;
}

static int import_x25519(const uint8_t priv[32], psa_key_id_t *id)
{
	psa_key_attributes_t at = PSA_KEY_ATTRIBUTES_INIT;

	psa_set_key_type(&at, PSA_KEY_TYPE_ECC_KEY_PAIR(PSA_ECC_FAMILY_MONTGOMERY));
	psa_set_key_bits(&at, 255);
	psa_set_key_usage_flags(&at, PSA_KEY_USAGE_DERIVE);
	psa_set_key_algorithm(&at, PSA_ALG_ECDH);
	return psa_import_key(&at, priv, 32, id) == PSA_SUCCESS ? 0 : -EIO;
}

/* Public key for a (clamped) X25519 private key. */
static int x25519_public(const uint8_t priv[32], uint8_t pub[32])
{
	psa_key_id_t id;
	size_t n;

	if (import_x25519(priv, &id)) {
		return -EIO;
	}
	psa_status_t st = psa_export_public_key(id, pub, 32, &n);

	psa_destroy_key(id);
	return st == PSA_SUCCESS && n == 32 ? 0 : -EIO;
}

static int x25519_shared(const uint8_t priv[32], const uint8_t peer[32], uint8_t out[32])
{
	psa_key_id_t id;
	size_t n;

	if (import_x25519(priv, &id)) {
		return -EIO;
	}
	psa_status_t st = psa_raw_key_agreement(PSA_ALG_ECDH, id, peer, 32, out, 32, &n);

	psa_destroy_key(id);
	return st == PSA_SUCCESS && n == 32 ? 0 : -EIO;
}

/* HKDF-SHA256: salt = PoP, info = "mc-ble-v1" || A || B || nonce_d, 32 bytes (ble.md §7.3). */
static int hkdf(const uint8_t *salt, size_t salt_len, const uint8_t shared[32],
		const uint8_t *info, size_t info_len, uint8_t out[32])
{
	psa_key_derivation_operation_t op = PSA_KEY_DERIVATION_OPERATION_INIT;
	psa_status_t st = psa_key_derivation_setup(&op, PSA_ALG_HKDF(PSA_ALG_SHA_256));

	if (st == PSA_SUCCESS) {
		st = psa_key_derivation_input_bytes(&op, PSA_KEY_DERIVATION_INPUT_SALT, salt, salt_len);
	}
	if (st == PSA_SUCCESS) {
		st = psa_key_derivation_input_bytes(&op, PSA_KEY_DERIVATION_INPUT_SECRET, shared, 32);
	}
	if (st == PSA_SUCCESS) {
		st = psa_key_derivation_input_bytes(&op, PSA_KEY_DERIVATION_INPUT_INFO, info, info_len);
	}
	if (st == PSA_SUCCESS) {
		st = psa_key_derivation_output_bytes(&op, out, 32);
	}
	psa_key_derivation_abort(&op);
	return st == PSA_SUCCESS ? 0 : -EIO;
}

/* HMAC(k_mac, who || A || B || nonce_d) */
static int confirm_mac(const struct mc_ble_session *s, const char *who, uint8_t out[32])
{
	psa_key_attributes_t at = PSA_KEY_ATTRIBUTES_INIT;
	uint8_t msg[3 + 32 + 32 + 16];
	psa_key_id_t id;
	size_t n;

	memcpy(msg, who, 3);
	memcpy(msg + 3, s->a, 32);
	memcpy(msg + 35, s->b, 32);
	memcpy(msg + 67, s->nonce_d, 16);
	psa_set_key_type(&at, PSA_KEY_TYPE_HMAC);
	psa_set_key_bits(&at, 128);
	psa_set_key_usage_flags(&at, PSA_KEY_USAGE_SIGN_MESSAGE);
	psa_set_key_algorithm(&at, PSA_ALG_HMAC(PSA_ALG_SHA_256));
	if (psa_import_key(&at, s->k_mac, 16, &id) != PSA_SUCCESS) {
		return -EIO;
	}
	psa_status_t st = psa_mac_compute(id, PSA_ALG_HMAC(PSA_ALG_SHA_256), msg, sizeof(msg), out,
					  32, &n);

	psa_destroy_key(id);
	return st == PSA_SUCCESS && n == 32 ? 0 : -EIO;
}

static bool mac_equal(const struct mc_ble_session *s, const char *who, const uint8_t *got)
{
	uint8_t want[32];
	uint8_t diff = 0;

	if (confirm_mac(s, who, want)) {
		return false;
	}
	for (int i = 0; i < 32; i++) {
		diff |= want[i] ^ got[i]; /* constant time */
	}
	return diff == 0;
}

static void make_nonce(uint8_t n[12], uint8_t dir, uint64_t ctr)
{
	memset(n, 0, 12);
	n[0] = dir;
	for (int i = 0; i < 8; i++) {
		n[11 - i] = (uint8_t)(ctr >> (8 * i));
	}
}

static int aead(const struct mc_ble_session *s, bool encrypt, uint8_t dir, uint64_t ctr,
		const uint8_t *in, size_t in_len, uint8_t *out, size_t cap, size_t *out_len)
{
	psa_key_attributes_t at = PSA_KEY_ATTRIBUTES_INIT;
	psa_key_id_t id;
	uint8_t nonce[12];

	make_nonce(nonce, dir, ctr);
	psa_set_key_type(&at, PSA_KEY_TYPE_AES);
	psa_set_key_bits(&at, 128);
	psa_set_key_usage_flags(&at, PSA_KEY_USAGE_ENCRYPT | PSA_KEY_USAGE_DECRYPT);
	psa_set_key_algorithm(&at, PSA_ALG_GCM);
	if (psa_import_key(&at, s->k_enc, 16, &id) != PSA_SUCCESS) {
		return -EIO;
	}
	psa_status_t st = encrypt
		? psa_aead_encrypt(id, PSA_ALG_GCM, nonce, 12, NULL, 0, in, in_len, out, cap, out_len)
		: psa_aead_decrypt(id, PSA_ALG_GCM, nonce, 12, NULL, 0, in, in_len, out, cap, out_len);

	psa_destroy_key(id);
	return st == PSA_SUCCESS ? 0 : -EBADMSG;
}

/* --- small helpers ---------------------------------------------------------------------------------------- */

static void wipe(void *p, size_t n)
{
	volatile uint8_t *v = p;

	while (n--) {
		*v++ = 0;
	}
}

static int b64_enc(const uint8_t *in, size_t n, char *out, size_t cap)
{
	size_t len;

	if (base64_encode((uint8_t *)out, cap - 1, &len, in, n) != 0) {
		return -ENOMEM;
	}
	out[len] = '\0';
	return 0;
}

/* Decodes exactly `want` bytes. */
static int b64_dec_exact(const char *in, uint8_t *out, size_t want)
{
	uint8_t tmp[64];
	size_t len;

	if (strlen(in) > 96 ||
	    base64_decode(tmp, sizeof(tmp), &len, (const uint8_t *)in, strlen(in)) != 0 || len != want) {
		return -EINVAL;
	}
	memcpy(out, tmp, want);
	return 0;
}

static int hexval(char c)
{
	if (c >= '0' && c <= '9') {
		return c - '0';
	}
	if (c >= 'a' && c <= 'f') {
		return c - 'a' + 10;
	}
	if (c >= 'A' && c <= 'F') {
		return c - 'A' + 10;
	}
	return -1;
}

static int hex32(const char *hex, uint8_t out[32])
{
	if (strlen(hex) != 64) {
		return -EINVAL;
	}
	for (int i = 0; i < 32; i++) {
		int hi = hexval(hex[2 * i]), lo = hexval(hex[2 * i + 1]);

		if (hi < 0 || lo < 0) {
			return -EINVAL;
		}
		out[i] = (uint8_t)(hi << 4 | lo);
	}
	return 0;
}

/* Reads 4 hex digits at `r` (after "\u"); -1 if malformed. */
static int hex4(const char *r)
{
	int cp = 0;

	for (int i = 0; i < 4; i++) {
		int v = hexval(r[i]);

		if (v < 0) {
			return -1;
		}
		cp = cp << 4 | v;
	}
	return cp;
}

/* In-place JSON string unescape (the Zephyr parser leaves escapes untouched). */
static bool unescape(char *s)
{
	char *w = s;

	for (const char *r = s; *r; r++) {
		if (*r != '\\') {
			*w++ = *r;
			continue;
		}
		r++;
		switch (*r) {
		case '"': case '\\': case '/': *w++ = *r; break;
		case 'b': *w++ = '\b'; break;
		case 'f': *w++ = '\f'; break;
		case 'n': *w++ = '\n'; break;
		case 'r': *w++ = '\r'; break;
		case 't': *w++ = '\t'; break;
		case 'u': {
			int cp = hex4(r + 1);

			if (cp < 0) {
				return false;
			}
			r += 4;
			if (cp >= 0xD800 && cp < 0xDC00 && r[1] == '\\' && r[2] == 'u') { /* surrogate pair */
				int lo = hex4(r + 3);

				if (lo < 0) {
					return false;
				}
				cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
				r += 6;
			}
			if (cp < 0x80) {
				*w++ = (char)cp;
			} else if (cp < 0x800) {
				*w++ = (char)(0xC0 | (cp >> 6));
				*w++ = (char)(0x80 | (cp & 0x3F));
			} else if (cp < 0x10000) {
				*w++ = (char)(0xE0 | (cp >> 12));
				*w++ = (char)(0x80 | ((cp >> 6) & 0x3F));
				*w++ = (char)(0x80 | (cp & 0x3F));
			} else {
				*w++ = (char)(0xF0 | (cp >> 18));
				*w++ = (char)(0x80 | ((cp >> 12) & 0x3F));
				*w++ = (char)(0x80 | ((cp >> 6) & 0x3F));
				*w++ = (char)(0x80 | (cp & 0x3F));
			}
			break;
		}
		default:
			return false;
		}
	}
	*w = '\0';
	return true;
}

/* --- output -------------------------------------------------------------------------------------------------- */

static int queue_frame(struct mc_ble_session *s, const uint8_t *body, size_t len)
{
	if (s->tx_off) { /* compact what was already taken */
		memmove(s->tx, s->tx + s->tx_off, s->tx_len - s->tx_off);
		s->tx_len -= s->tx_off;
		s->tx_off = 0;
	}
	if (s->tx_len + 2 + len > sizeof(s->tx)) {
		return -ENOMEM;
	}
	s->tx[s->tx_len++] = (uint8_t)(len >> 8);
	s->tx[s->tx_len++] = (uint8_t)len;
	memcpy(s->tx + s->tx_len, body, len);
	s->tx_len += len;
	return 0;
}

static int send_sealed(struct mc_ble_session *s, const char *json, size_t len)
{
	static uint8_t body[MC_BLE_MAX_BODY];
	size_t n;

	if (aead(s, true, DIR_DEV_TO_APP, s->send_ctr, (const uint8_t *)json, len, body,
		 sizeof(body), &n)) {
		return -EIO;
	}
	s->send_ctr++;
	return queue_frame(s, body, n);
}

/* --- handshake -------------------------------------------------------------------------------------------------- */

struct hello_j {
	const char *t;
	int32_t v;
	const char *pub;
};
static const struct json_obj_descr hello_descr[] = {
	JSON_OBJ_DESCR_PRIM(struct hello_j, t, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct hello_j, v, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct hello_j, pub, JSON_TOK_STRING),
};

struct confirm_j {
	const char *t;
	const char *mac;
};
static const struct json_obj_descr confirm_descr[] = {
	JSON_OBJ_DESCR_PRIM(struct confirm_j, t, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct confirm_j, mac, JSON_TOK_STRING),
};

static int fail(struct mc_ble_session *s, enum mc_ble_fail why)
{
	s->state = MC_BLE_FAILED;
	s->fail = why;
	wipe(s->k_enc, sizeof(s->k_enc));
	wipe(s->k_mac, sizeof(s->k_mac));
	wipe(s->priv, sizeof(s->priv));
	return -EPROTO;
}

static int on_hello(struct mc_ble_session *s, char *body, size_t len)
{
	struct hello_j h = {.v = -1};
	uint8_t shared[32], info[9 + 32 + 32 + 16], k[32];
	char pub_b64[48], nonce_b64[32], out[160];
	struct mc_jw w;

	if (json_obj_parse(body, len, hello_descr, ARRAY_SIZE(hello_descr), &h) < 0 || h.t == NULL ||
	    strcmp(h.t, "hello") != 0 || h.pub == NULL) {
		return fail(s, MC_BLE_FAIL_PROTOCOL);
	}
	if (h.v != VERSION) {
		const char *e = "{\"t\":\"error\",\"error\":\"unsupported_version\"}";

		queue_frame(s, (const uint8_t *)e, strlen(e));
		return fail(s, MC_BLE_FAIL_VERSION);
	}
	if (b64_dec_exact(h.pub, s->a, 32)) {
		return fail(s, MC_BLE_FAIL_PROTOCOL);
	}
	if (s->fixed_priv) {
		memcpy(s->priv, s->fixed_priv, 32);
	} else if (psa_generate_random(s->priv, 32) != PSA_SUCCESS) {
		return fail(s, MC_BLE_FAIL_CRYPTO);
	}
	clamp(s->priv);
	if (s->fixed_nonce) {
		memcpy(s->nonce_d, s->fixed_nonce, 16);
	} else if (psa_generate_random(s->nonce_d, 16) != PSA_SUCCESS) {
		return fail(s, MC_BLE_FAIL_CRYPTO);
	}
	if (x25519_public(s->priv, s->b) || x25519_shared(s->priv, s->a, shared)) {
		return fail(s, MC_BLE_FAIL_CRYPTO);
	}
	memcpy(info, "mc-ble-v1", 9);
	memcpy(info + 9, s->a, 32);
	memcpy(info + 41, s->b, 32);
	memcpy(info + 73, s->nonce_d, 16);
	if (hkdf(s->pop, MC_BLE_POP_LEN, shared, info, sizeof(info), k)) {
		return fail(s, MC_BLE_FAIL_CRYPTO);
	}
	memcpy(s->k_enc, k, 16);
	memcpy(s->k_mac, k + 16, 16);
	wipe(shared, sizeof(shared));
	wipe(k, sizeof(k));
	wipe(s->priv, sizeof(s->priv)); /* not needed any more */

	if (b64_enc(s->b, 32, pub_b64, sizeof(pub_b64)) ||
	    b64_enc(s->nonce_d, 16, nonce_b64, sizeof(nonce_b64))) {
		return fail(s, MC_BLE_FAIL_CRYPTO);
	}
	mc_jw_init(&w, out, sizeof(out));
	mc_jw_obj(&w);
	mc_jw_kv_str(&w, "t", "hello_ack");
	mc_jw_kv_str(&w, "pub", pub_b64);
	mc_jw_kv_str(&w, "nonce", nonce_b64);
	mc_jw_end_obj(&w);
	int n = mc_jw_finish(&w);

	if (n < 0 || queue_frame(s, (const uint8_t *)out, (size_t)n)) {
		return fail(s, MC_BLE_FAIL_CRYPTO);
	}
	s->state = MC_BLE_HELLO_ACKED;
	return 0;
}

static int on_confirm(struct mc_ble_session *s, char *body, size_t len)
{
	struct confirm_j c = {0};
	uint8_t mac[32], mine[32];
	char mac_b64[64], out[128];
	struct mc_jw w;

	if (json_obj_parse(body, len, confirm_descr, ARRAY_SIZE(confirm_descr), &c) < 0 ||
	    c.t == NULL || strcmp(c.t, "confirm") != 0 || c.mac == NULL ||
	    b64_dec_exact(c.mac, mac, 32)) {
		return fail(s, MC_BLE_FAIL_PROTOCOL);
	}
	if (!mac_equal(s, "app", mac)) {
		return fail(s, MC_BLE_FAIL_CONFIRM); /* wrong code: the window counts this */
	}
	if (confirm_mac(s, "dev", mine) || b64_enc(mine, 32, mac_b64, sizeof(mac_b64))) {
		return fail(s, MC_BLE_FAIL_CRYPTO);
	}
	mc_jw_init(&w, out, sizeof(out));
	mc_jw_obj(&w);
	mc_jw_kv_str(&w, "t", "confirm");
	mc_jw_kv_str(&w, "mac", mac_b64);
	mc_jw_end_obj(&w);
	int n = mc_jw_finish(&w);

	if (n < 0 || queue_frame(s, (const uint8_t *)out, (size_t)n)) {
		return fail(s, MC_BLE_FAIL_CRYPTO);
	}
	s->state = MC_BLE_OPEN;
	return 0;
}

/* --- requests ------------------------------------------------------------------------------------------------------- */

struct req_j {
	int32_t id;
	const char *op;
	const char *ssid;
	const char *password;
	const char *device_id;
	const char *host;
	int32_t port;
	const char *psk;
};
static const struct json_obj_descr req_descr[] = {
	JSON_OBJ_DESCR_PRIM(struct req_j, id, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct req_j, op, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct req_j, ssid, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct req_j, password, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct req_j, device_id, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct req_j, host, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct req_j, port, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct req_j, psk, JSON_TOK_STRING),
};

/* `{"id":n,"ok":false,"error":code[,"detail":..]}` */
static int reply_error(struct mc_ble_session *s, int32_t id, const char *code, const char *detail)
{
	char out[192];
	struct mc_jw w;

	mc_jw_init(&w, out, sizeof(out));
	mc_jw_obj(&w);
	mc_jw_kv_int(&w, "id", id);
	mc_jw_kv_bool(&w, "ok", false);
	mc_jw_kv_str(&w, "error", code);
	if (detail && detail[0]) {
		mc_jw_kv_str(&w, "detail", detail);
	}
	mc_jw_end_obj(&w);
	int n = mc_jw_finish(&w);

	return n < 0 ? -ENOMEM : send_sealed(s, out, (size_t)n);
}

static int reply_ok(struct mc_ble_session *s, int32_t id)
{
	char out[48];
	struct mc_jw w;

	mc_jw_init(&w, out, sizeof(out));
	mc_jw_obj(&w);
	mc_jw_kv_int(&w, "id", id);
	mc_jw_kv_bool(&w, "ok", true);
	mc_jw_end_obj(&w);
	return send_sealed(s, out, (size_t)mc_jw_finish(&w));
}

static int reply_scan(struct mc_ble_session *s, int32_t id, const struct mc_ble_net *nets, int count)
{
	static char out[MC_BLE_MAX_MSG + 1];
	struct mc_jw w;

	/* as many as fit into one message, strongest first */
	for (int take = count; take >= 0; take--) {
		mc_jw_init(&w, out, sizeof(out));
		mc_jw_obj(&w);
		mc_jw_kv_int(&w, "id", id);
		mc_jw_kv_bool(&w, "ok", true);
		mc_jw_key(&w, "networks");
		mc_jw_arr(&w);
		for (int i = 0; i < take; i++) {
			mc_jw_obj(&w);
			mc_jw_kv_str(&w, "ssid", nets[i].ssid);
			mc_jw_kv_int(&w, "rssi", nets[i].rssi);
			mc_jw_kv_bool(&w, "secure", nets[i].secure);
			mc_jw_end_obj(&w);
		}
		mc_jw_end_arr(&w);
		mc_jw_end_obj(&w);
		int n = mc_jw_finish(&w);

		if (n >= 0) {
			return send_sealed(s, out, (size_t)n);
		}
	}
	return reply_error(s, id, "too_large", "");
}

static int handle_request(struct mc_ble_session *s, char *plain, size_t len)
{
	struct req_j r = {.id = -1, .port = -1};
	const struct mc_ble_ops *ops = s->ops;
	struct mc_jw w;
	char out[256];

	if (json_obj_parse(plain, len, req_descr, ARRAY_SIZE(req_descr), &r) < 0 || r.op == NULL ||
	    r.id < 0) {
		return reply_error(s, r.id < 0 ? 0 : r.id, "bad_request", "");
	}
	bool ok = true;

	if (r.ssid) {
		ok = ok && unescape((char *)r.ssid);
	}
	if (r.password) {
		ok = ok && unescape((char *)r.password);
	}
	if (r.device_id) {
		ok = ok && unescape((char *)r.device_id);
	}
	if (r.host) {
		ok = ok && unescape((char *)r.host);
	}
	if (!ok) {
		return reply_error(s, r.id, "bad_request", "bad escape");
	}

	if (strcmp(r.op, "info") == 0) {
		struct mc_ble_info info = {0};

		if (ops->info == NULL || ops->info(s->ops_user, &info) < 0) {
			return reply_error(s, r.id, "failed", "");
		}
		mc_jw_init(&w, out, sizeof(out));
		mc_jw_obj(&w);
		mc_jw_kv_int(&w, "id", r.id);
		mc_jw_kv_bool(&w, "ok", true);
		mc_jw_kv_str(&w, "hw_mac", info.hw_mac);
		mc_jw_kv_str(&w, "fw", "0.1.0");
		mc_jw_kv_bool(&w, "provisioned", info.provisioned);
		if (info.provisioned) {
			mc_jw_kv_str(&w, "device_id", info.device_id);
		}
		mc_jw_end_obj(&w);
		int n = mc_jw_finish(&w);

		return n < 0 ? reply_error(s, r.id, "too_large", "") : send_sealed(s, out, (size_t)n);
	}
	if (strcmp(r.op, "wifi_scan") == 0) {
		static struct mc_ble_net nets[MC_BLE_NETWORKS_MAX];
		int count = ops->wifi_scan ? ops->wifi_scan(s->ops_user, nets, MC_BLE_NETWORKS_MAX) : -1;

		return count < 0 ? reply_error(s, r.id, "failed", "scan failed")
				 : reply_scan(s, r.id, nets, count);
	}
	if (strcmp(r.op, "set_wifi") == 0) {
		if (r.ssid == NULL || r.ssid[0] == '\0' || strlen(r.ssid) > MC_BLE_SSID_MAX ||
		    (r.password && strlen(r.password) > MC_BLE_PASSWORD_MAX)) {
			return reply_error(s, r.id, "bad_request", "ssid 1-32 bytes, password 0-64 bytes");
		}
		if (ops->set_wifi == NULL ||
		    ops->set_wifi(s->ops_user, r.ssid, r.password ? r.password : "") < 0) {
			return reply_error(s, r.id, "bad_request", "");
		}
		s->have_wifi = true;
		return reply_ok(s, r.id);
	}
	if (strcmp(r.op, "set_mqtt") == 0) {
		uint8_t psk[32];

		if (r.device_id == NULL || strncmp(r.device_id, "mc-", 3) != 0 ||
		    strlen(r.device_id) > 31 || r.host == NULL || r.host[0] == '\0' ||
		    strlen(r.host) > 63 || r.port < 1 || r.port > 65535 || r.psk == NULL ||
		    hex32(r.psk, psk)) {
			return reply_error(s, r.id, "bad_request", "device_id, host, port, psk (64 hex)");
		}
		int rc = ops->set_mqtt ? ops->set_mqtt(s->ops_user, r.device_id, r.host, r.port, psk) : -1;

		wipe(psk, sizeof(psk));
		if (rc < 0) {
			return reply_error(s, r.id, "bad_request", "");
		}
		s->have_mqtt = true;
		return reply_ok(s, r.id);
	}
	if (strcmp(r.op, "test") == 0) {
		struct mc_ble_test t = {0};

		if (!s->have_wifi || !s->have_mqtt) {
			return reply_error(s, r.id, "not_ready", "set_wifi and set_mqtt first");
		}
		if (ops->test == NULL || ops->test(s->ops_user, &t) < 0) {
			return reply_error(s, r.id, "failed", "");
		}
		mc_jw_init(&w, out, sizeof(out));
		mc_jw_obj(&w);
		mc_jw_kv_int(&w, "id", r.id);
		mc_jw_kv_bool(&w, "ok", true);
		mc_jw_kv_str(&w, "wifi", t.wifi_ok ? "ok" : "err");
		mc_jw_kv_str(&w, "mqtt", t.mqtt_ok ? "ok" : "err");
		mc_jw_kv_str(&w, "detail", t.detail);
		mc_jw_end_obj(&w);
		int n = mc_jw_finish(&w);

		return n < 0 ? reply_error(s, r.id, "too_large", "") : send_sealed(s, out, (size_t)n);
	}
	if (strcmp(r.op, "commit") == 0) {
		if (!s->have_wifi || !s->have_mqtt) {
			return reply_error(s, r.id, "not_ready", "set_wifi and set_mqtt first");
		}
		if (ops->commit == NULL || ops->commit(s->ops_user) < 0) {
			return reply_error(s, r.id, "failed", "could not store the settings");
		}
		int rc = reply_ok(s, r.id);

		s->commit_done = true; /* the reply is queued: the caller restarts once it was sent */
		return rc;
	}
	if (strcmp(r.op, "abort") == 0) {
		if (ops->abort) {
			ops->abort(s->ops_user);
		}
		s->have_wifi = s->have_mqtt = false;
		s->aborted = true;
		return reply_ok(s, r.id);
	}
	return reply_error(s, r.id, "unknown_op", "");
}

static int on_encrypted(struct mc_ble_session *s, const uint8_t *body, size_t len)
{
	static char plain[MC_BLE_MAX_MSG + 1];
	size_t n;

	if (len < 16 || aead(s, false, DIR_APP_TO_DEV, s->recv_ctr, body, len, (uint8_t *)plain,
			     MC_BLE_MAX_MSG, &n)) {
		return fail(s, MC_BLE_FAIL_FRAME);
	}
	s->recv_ctr++;
	plain[n] = '\0';
	if (handle_request(s, plain, n) < 0) {
		return fail(s, MC_BLE_FAIL_CRYPTO);
	}
	return 0;
}

/* --- public ----------------------------------------------------------------------------------------------------------- */

void mc_ble_init(struct mc_ble_session *s, const uint8_t pop[MC_BLE_POP_LEN],
		 const struct mc_ble_ops *ops, void *ops_user)
{
	memset(s, 0, sizeof(*s));
	memcpy(s->pop, pop, MC_BLE_POP_LEN);
	s->ops = ops;
	s->ops_user = ops_user;
	s->state = MC_BLE_NEW;
	psa_crypto_init();
}

int mc_ble_feed(struct mc_ble_session *s, const uint8_t *data, size_t len)
{
	if (s->state == MC_BLE_FAILED) {
		return -EPROTO;
	}
	while (len > 0) {
		/* the 2-byte length first, then the body */
		size_t want = s->rx_len < 2 ? 2 - s->rx_len
					    : 2 + (((size_t)s->rx[0] << 8) | s->rx[1]) - s->rx_len;
		size_t take = MIN(want, len);

		memcpy(s->rx + s->rx_len, data, take);
		s->rx_len += take;
		data += take;
		len -= take;
		if (s->rx_len < 2) {
			continue;
		}
		size_t body_len = ((size_t)s->rx[0] << 8) | s->rx[1];

		if (body_len > MC_BLE_MAX_BODY) {
			return fail(s, MC_BLE_FAIL_FRAME);
		}
		if (s->rx_len < 2 + body_len) {
			continue;
		}
		uint8_t *body = s->rx + 2;
		int rc;

		s->rx_len = 0; /* the frame is complete: handlers may take their time */
		switch (s->state) {
		case MC_BLE_NEW:
			body[body_len] = '\0';
			rc = on_hello(s, (char *)body, body_len);
			break;
		case MC_BLE_HELLO_ACKED:
			body[body_len] = '\0';
			rc = on_confirm(s, (char *)body, body_len);
			break;
		case MC_BLE_OPEN:
			rc = on_encrypted(s, body, body_len);
			break;
		default:
			rc = -EPROTO;
		}
		if (rc < 0) {
			return rc;
		}
	}
	return 0;
}

size_t mc_ble_take(struct mc_ble_session *s, uint8_t *dst, size_t max)
{
	size_t n = MIN(max, s->tx_len - s->tx_off);

	memcpy(dst, s->tx + s->tx_off, n);
	s->tx_off += n;
	if (s->tx_off == s->tx_len) {
		s->tx_off = s->tx_len = 0;
	}
	return n;
}

bool mc_ble_has_output(const struct mc_ble_session *s)
{
	return s->tx_len > s->tx_off;
}

void mc_ble_close(struct mc_ble_session *s)
{
	wipe(s->k_enc, sizeof(s->k_enc));
	wipe(s->k_mac, sizeof(s->k_mac));
	wipe(s->priv, sizeof(s->priv));
	wipe(s->pop, sizeof(s->pop));
	s->state = MC_BLE_FAILED;
}

bool mc_factory_parse(const uint8_t page[MC_FACTORY_SIZE], uint8_t pop[MC_BLE_POP_LEN])
{
	uint32_t crc = crc32_ieee(page, 21);
	uint32_t stored = (uint32_t)page[21] | ((uint32_t)page[22] << 8) |
			  ((uint32_t)page[23] << 16) | ((uint32_t)page[24] << 24);

	if (memcmp(page, "MCFP", 4) != 0 || page[4] != 1 || crc != stored) {
		return false;
	}
	memcpy(pop, page + 5, MC_BLE_POP_LEN);
	return true;
}
