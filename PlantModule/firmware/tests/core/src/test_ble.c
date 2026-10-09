/* The BLE pairing session against the frames the Python reference produced. */
#include <zephyr/ztest.h>
#include <string.h>
#include <zephyr/sys/crc.h>

#include "ble_vectors.h"
#include "mc_ble.h"

static struct mc_ble_session sess;

struct fake {
	char ssid[40], password[80], device_id[40], host[70];
	int port;
	uint8_t psk[32];
	int set_wifi, set_mqtt, commits, aborts;
};
static struct fake fk;

static int hex(const char *h, uint8_t *out, size_t cap)
{
	size_t n = strlen(h) / 2;

	zassert_true(n <= cap);
	for (size_t i = 0; i < n; i++) {
		unsigned v;

		sscanf(h + 2 * i, "%2x", &v);
		out[i] = (uint8_t)v;
	}
	return (int)n;
}

static int op_info(void *u, struct mc_ble_info *o)
{
	strcpy(o->hw_mac, "24:6F:28:AA:BB:CC");
	o->provisioned = false;
	return 0;
}
static int op_scan(void *u, struct mc_ble_net *o, size_t max)
{
	strcpy(o[0].ssid, "Home");
	o[0].rssi = -50;
	o[0].secure = true;
	strcpy(o[1].ssid, "Guest");
	o[1].rssi = -70;
	o[1].secure = false;
	return 2;
}
static int op_set_wifi(void *u, const char *ssid, const char *pw)
{
	strcpy(fk.ssid, ssid);
	strcpy(fk.password, pw);
	fk.set_wifi++;
	return 0;
}
static int op_set_mqtt(void *u, const char *id, const char *host, int port, const uint8_t psk[32])
{
	strcpy(fk.device_id, id);
	strcpy(fk.host, host);
	fk.port = port;
	memcpy(fk.psk, psk, 32);
	fk.set_mqtt++;
	return 0;
}
static int op_test(void *u, struct mc_ble_test *t)
{
	t->wifi_ok = true;
	t->mqtt_ok = false;
	strcpy(t->detail, "tls handshake failed");
	return 0;
}
static int op_commit(void *u)
{
	fk.commits++;
	return 0;
}
static void op_abort(void *u)
{
	fk.aborts++;
}

static const struct mc_ble_ops ops = {.info = op_info, .wifi_scan = op_scan, .set_wifi = op_set_wifi,
				      .set_mqtt = op_set_mqtt, .test = op_test, .commit = op_commit,
				      .abort = op_abort};

static uint8_t priv[32], nonce[16], pop[16];

static void start(const uint8_t *use_pop)
{
	memset(&fk, 0, sizeof(fk));
	hex(vec_pop, pop, sizeof(pop));
	hex(vec_device_private, priv, sizeof(priv));
	hex(vec_nonce_d, nonce, sizeof(nonce));
	mc_ble_init(&sess, use_pop ? use_pop : pop, &ops, NULL);
	sess.fixed_priv = priv;
	sess.fixed_nonce = nonce;
}

/* Feeds `n` bytes in pieces of `chunk` (0 = all at once). */
static int feed(const uint8_t *d, size_t n, size_t chunk)
{
	int rc = 0;

	for (size_t off = 0; off < n && rc == 0; off += chunk ? chunk : n) {
		rc = mc_ble_feed(&sess, d + off, MIN(chunk ? chunk : n, n - off));
	}
	return rc;
}

static size_t drain(uint8_t *out, size_t cap)
{
	size_t n = 0, got;

	while ((got = mc_ble_take(&sess, out + n, MIN(cap - n, (size_t)7))) > 0) {
		n += got; /* taken in odd-sized pieces on purpose */
	}
	return n;
}

/* Replays a scripted session: every app->dev frame in, the next dev->app frame must match. */
static void replay(const struct vframe *frames, size_t count, size_t chunk)
{
	static uint8_t in[1200], want[1200], got[1200];

	for (size_t i = 0; i < count; i++) {
		if (!frames[i].to_dev) {
			continue;
		}
		int n = hex(frames[i].hex, in, sizeof(in));

		zassert_equal(feed(in, n, chunk), 0, "frame %d rejected, fail=%d", (int)i, sess.fail);
		zassert_true(i + 1 < count && !frames[i + 1].to_dev);
		int wn = hex(frames[i + 1].hex, want, sizeof(want));
		size_t gn = drain(got, sizeof(got));

		zassert_equal(gn, (size_t)wn, "reply to frame %d: %d bytes, want %d", (int)i, (int)gn, wn);
		zassert_mem_equal(got, want, wn, "reply to frame %d differs", (int)i);
	}
}

ZTEST(ble, test_main_session_matches_the_reference_byte_for_byte)
{
	size_t chunks[] = {0, 185, 20, 1};

	for (size_t c = 0; c < ARRAY_SIZE(chunks); c++) {
		start(NULL);
		replay(vec_frames, VEC_FRAMES_N, chunks[c]);
		zassert_equal(sess.state, MC_BLE_OPEN);
		zassert_true(sess.commit_done);
		zassert_equal(fk.commits, 1);
	}
	/* what the device stored after the last run: escapes resolved, UTF-8 intact */
	zassert_str_equal(fk.ssid, "Home \"5G\"");
	zassert_str_equal(fk.password, "pa\\ss w\xC3\xB6rd");
	zassert_str_equal(fk.device_id, "mc-8f3kq2v7xw1m9hzt");
	zassert_str_equal(fk.host, "192.168.1.20");
	zassert_equal(fk.port, 8883);
	for (int i = 0; i < 32; i++) {
		zassert_equal(fk.psk[i], 0xab);
	}
	zassert_equal(fk.set_wifi, 1);
	zassert_equal(fk.set_mqtt, 1);
}

ZTEST(ble, test_ops_session_errors_and_results_match_the_reference)
{
	start(NULL);
	replay(vec_ops_frames, VEC_OPS_FRAMES_N, 0);
	zassert_equal(fk.aborts, 1);
	zassert_equal(fk.commits, 0, "commit after abort is refused");
	zassert_false(sess.commit_done);
	zassert_equal(fk.set_wifi, 1, "the empty ssid never reached the ops");
	zassert_equal(fk.set_mqtt, 1, "the bad key never reached the ops");
}

ZTEST(ble, test_wrong_pop_fails_the_confirmation)
{
	static uint8_t in[400];
	uint8_t other[16];

	memset(other, 0x42, sizeof(other));
	start(other);
	int n = hex(vec_frames[0].hex, in, sizeof(in));

	zassert_equal(feed(in, n, 0), 0);
	zassert_true(mc_ble_has_output(&sess)); /* a HELLO_ACK goes out either way */
	n = hex(vec_frames[2].hex, in, sizeof(in));
	zassert_true(feed(in, n, 0) < 0);
	zassert_equal(sess.fail, MC_BLE_FAIL_CONFIRM);
	zassert_equal(sess.state, MC_BLE_FAILED);
	/* the failed session is dead: nothing more is accepted */
	zassert_true(feed(in, n, 0) < 0);
}

static void open_session(void)
{
	static uint8_t in[400];

	start(NULL);
	for (int i = 0; i < 4; i++) {
		if (vec_frames[i].to_dev) {
			int n = hex(vec_frames[i].hex, in, sizeof(in));

			zassert_equal(feed(in, n, 0), 0);
		}
	}
	zassert_equal(sess.state, MC_BLE_OPEN);
	uint8_t drop[400];

	drain(drop, sizeof(drop));
}

ZTEST(ble, test_tampered_replayed_and_reordered_frames_end_the_session)
{
	static uint8_t f[1200];
	int n;

	open_session();
	n = hex(vec_frames[4].hex, f, sizeof(f));
	f[n - 1] ^= 1;
	zassert_true(feed(f, n, 0) < 0);
	zassert_equal(sess.fail, MC_BLE_FAIL_FRAME);

	open_session(); /* replay */
	n = hex(vec_frames[4].hex, f, sizeof(f));
	zassert_equal(feed(f, n, 0), 0);
	zassert_true(feed(f, n, 0) < 0);
	zassert_equal(sess.fail, MC_BLE_FAIL_FRAME);

	open_session(); /* reordering: the second request first */
	n = hex(vec_frames[6].hex, f, sizeof(f));
	zassert_true(feed(f, n, 0) < 0);
	zassert_equal(sess.fail, MC_BLE_FAIL_FRAME);
}

ZTEST(ble, test_a_frame_the_device_itself_sent_is_not_accepted_back)
{
	static uint8_t f[1200];

	open_session();
	int n = hex(vec_frames[5].hex, f, sizeof(f)); /* the device's own reply to `info` */

	zassert_true(feed(f, n, 0) < 0);
	zassert_equal(sess.fail, MC_BLE_FAIL_FRAME);
}

ZTEST(ble, test_unsupported_version_is_told_and_refused)
{
	static const char hello[] = "{\"t\":\"hello\",\"v\":2,\"pub\":\"AAAA\"}";
	uint8_t f[80], out[120];
	size_t n = strlen(hello);

	start(NULL);
	f[0] = 0;
	f[1] = (uint8_t)n;
	memcpy(f + 2, hello, n);
	zassert_true(feed(f, n + 2, 0) < 0);
	zassert_equal(sess.fail, MC_BLE_FAIL_VERSION);
	size_t got = drain(out, sizeof(out));

	zassert_true(got > 2);
	out[got] = '\0';
	zassert_not_null(strstr((char *)out + 2, "unsupported_version"));
}

ZTEST(ble, test_garbage_before_the_handshake)
{
	static const uint8_t junk[] = {0x00, 0x05, 'h', 'e', 'l', 'l', 'o'};
	static const uint8_t huge[] = {0xff, 0xff};

	start(NULL);
	zassert_true(feed(junk, sizeof(junk), 0) < 0);
	zassert_equal(sess.fail, MC_BLE_FAIL_PROTOCOL);
	start(NULL);
	zassert_true(feed(huge, sizeof(huge), 0) < 0);
	zassert_equal(sess.fail, MC_BLE_FAIL_FRAME);
	/* a confirm before any hello */
	static const char c[] = "{\"t\":\"confirm\",\"mac\":\"AAAA\"}";
	uint8_t f[60];

	start(NULL);
	f[0] = 0;
	f[1] = strlen(c);
	memcpy(f + 2, c, strlen(c));
	zassert_true(feed(f, strlen(c) + 2, 0) < 0);
}

ZTEST(ble, test_keys_are_wiped_on_close)
{
	open_session();
	mc_ble_close(&sess);
	uint8_t zero[16] = {0};

	zassert_mem_equal(sess.k_enc, zero, 16);
	zassert_mem_equal(sess.k_mac, zero, 16);
	zassert_mem_equal(sess.pop, zero, 16);
}

ZTEST(ble, test_random_keys_work_too_and_differ_per_session)
{
	/* production path: no fixed key or nonce */
	static uint8_t in[400], a[100], b[100];

	start(NULL);
	sess.fixed_priv = NULL;
	sess.fixed_nonce = NULL;
	int n = hex(vec_frames[0].hex, in, sizeof(in));

	zassert_equal(feed(in, n, 0), 0);
	size_t na = drain(a, sizeof(a));

	start(NULL);
	sess.fixed_priv = NULL;
	sess.fixed_nonce = NULL;
	zassert_equal(feed(in, n, 0), 0);
	size_t nb = drain(b, sizeof(b));

	zassert_true(na > 0 && na == nb);
	zassert_true(memcmp(a, b, na) != 0, "two sessions answered identically");
}

ZTEST(ble, test_factory_page)
{
	uint8_t page[MC_FACTORY_SIZE] = {'M', 'C', 'F', 'P', 1};
	uint8_t out[16];

	for (int i = 0; i < 16; i++) {
		page[5 + i] = (uint8_t)(0xA0 + i);
	}
	uint32_t crc = crc32_ieee(page, 21);

	page[21] = crc;
	page[22] = crc >> 8;
	page[23] = crc >> 16;
	page[24] = crc >> 24;
	zassert_true(mc_factory_parse(page, out));
	zassert_equal(out[0], 0xA0);
	zassert_equal(out[15], 0xAF);
	page[10] ^= 1;
	zassert_false(mc_factory_parse(page, out)); /* CRC */
	page[10] ^= 1;
	page[4] = 2;
	zassert_false(mc_factory_parse(page, out)); /* version */
	memset(page, 0xff, sizeof(page));
	zassert_false(mc_factory_parse(page, out)); /* erased flash */

	/* the page the Python tool writes (same CRC, same layout) */
	hex(vec_factory_page, page, sizeof(page));
	zassert_true(mc_factory_parse(page, out));
	zassert_equal(out[0], 0x00);
	zassert_equal(out[15], 0x0f);
}

ZTEST_SUITE(ble, NULL, NULL, NULL, NULL, NULL);
