#include <zephyr/ztest.h>
#include <string.h>

#include "mc_json.h"

static int build(char *buf, size_t cap, void (*fn)(struct mc_jw *))
{
	struct mc_jw w;

	mc_jw_init(&w, buf, cap);
	fn(&w);
	return mc_jw_finish(&w);
}

static void compose(struct mc_jw *w)
{
	mc_jw_obj(w);
	mc_jw_kv_int(w, "a", 1);
	mc_jw_kv_str(w, "s", "x");
	mc_jw_key(w, "list");
	mc_jw_arr(w);
	mc_jw_int(w, -5);
	mc_jw_obj(w);
	mc_jw_kv_bool(w, "t", true);
	mc_jw_end_obj(w);
	mc_jw_end_arr(w);
	mc_jw_key(w, "o");
	mc_jw_obj(w);
	mc_jw_end_obj(w);
	mc_jw_end_obj(w);
}

ZTEST(json, test_compact_nesting_and_commas)
{
	char buf[128];

	zassert_true(build(buf, sizeof(buf), compose) > 0);
	zassert_str_equal(buf, "{\"a\":1,\"s\":\"x\",\"list\":[-5,{\"t\":true}],\"o\":{}}");
}

static void escapes(struct mc_jw *w)
{
	mc_jw_str(w, "q\"b\\n\n\x01\xC2\xB0");
}

ZTEST(json, test_escaping_keeps_utf8)
{
	char buf[64];

	zassert_true(build(buf, sizeof(buf), escapes) > 0);
	zassert_str_equal(buf, "\"q\\\"b\\\\n\\u000a\\u0001\xC2\xB0\"");
}

static void decimals(struct mc_jw *w)
{
	mc_jw_arr(w);
	mc_jw_dec1(w, 415);
	mc_jw_dec1(w, 0);
	mc_jw_dec1(w, 5);
	mc_jw_dec1(w, -75);
	mc_jw_dec1(w, 1000);
	mc_jw_int(w, INT64_MIN);
	mc_jw_end_arr(w);
}

ZTEST(json, test_one_decimal_and_extremes)
{
	char buf[96];

	zassert_true(build(buf, sizeof(buf), decimals) > 0);
	zassert_str_equal(buf, "[41.5,0.0,0.5,-7.5,100.0,-9223372036854775808]");
}

ZTEST(json, test_overflow_is_reported_not_written)
{
	char buf[8];

	zassert_equal(build(buf, sizeof(buf), compose), -1);
	zassert_true(strlen(buf) < sizeof(buf));
}

ZTEST_SUITE(json, NULL, NULL, NULL, NULL, NULL);
