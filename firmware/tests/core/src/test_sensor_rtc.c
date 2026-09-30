#include <zephyr/ztest.h>
#include <string.h>

#include "mc_rtc.h"
#include "mc_sensor.h"

ZTEST(sensor, test_moisture_calibration)
{
	int32_t v;

	/* dry 3000 = 0 %, wet 1200 = 100 % */
	zassert_equal(mc_moisture_convert(3000, 3000, 1200, &v), MC_SENSOR_OK);
	zassert_equal(v, 0);
	zassert_equal(mc_moisture_convert(1200, 3000, 1200, &v), MC_SENSOR_OK);
	zassert_equal(v, 1000);
	zassert_equal(mc_moisture_convert(2100, 3000, 1200, &v), MC_SENSOR_OK);
	zassert_equal(v, 500);
	zassert_equal(mc_moisture_convert(2143, 3000, 1200, &v), MC_SENSOR_OK);
	zassert_equal(v, 476); /* 47.6 % */
	/* slightly outside the span is clamped, far outside is an error */
	zassert_equal(mc_moisture_convert(3100, 3000, 1200, &v), MC_SENSOR_OK);
	zassert_equal(v, 0);
	zassert_equal(mc_moisture_convert(1100, 3000, 1200, &v), MC_SENSOR_OK);
	zassert_equal(v, 1000);
	zassert_equal(mc_moisture_convert(3500, 3000, 1200, &v), MC_SENSOR_OUT_OF_RANGE);
	zassert_equal(mc_moisture_convert(800, 3000, 1200, &v), MC_SENSOR_OUT_OF_RANGE);
}

ZTEST(sensor, test_nothing_connected)
{
	int32_t v;

	zassert_equal(mc_moisture_convert(4095, 3000, 1200, &v), MC_SENSOR_NO_SIGNAL);
	zassert_equal(mc_moisture_convert(0, 3000, 1200, &v), MC_SENSOR_NO_SIGNAL);
}

ZTEST(sensor, test_resistive_orientation_is_handled)
{
	int32_t v;

	/* a sensor that reads higher when wet: dry < wet */
	zassert_equal(mc_moisture_convert(1000, 1000, 3000, &v), MC_SENSOR_OK);
	zassert_equal(v, 0);
	zassert_equal(mc_moisture_convert(2000, 1000, 3000, &v), MC_SENSOR_OK);
	zassert_equal(v, 500);
}

ZTEST(sensor, test_reading_from_slot)
{
	struct mc_slot s = {.slot = 1, .module = MC_MOD_MOISTURE_CAPACITIVE, .cal_dry = 3000,
			    .cal_wet = 1200};
	struct mc_reading r;

	mc_moisture_reading(&s, 2100, &r);
	zassert_true(r.has_value && r.has_raw);
	zassert_equal(r.slot, 1);
	zassert_equal(r.value_x10, 500);
	mc_moisture_reading(&s, 4095, &r);
	zassert_false(r.has_value);
	zassert_equal(r.err, MC_SENSOR_NO_SIGNAL);
	zassert_equal(r.raw, 4095);
}

ZTEST_SUITE(sensor, NULL, NULL, NULL, NULL, NULL);

static struct mc_rtc rtc;

static void before(void *f)
{
	mc_rtc_init(&rtc);
}

static struct mc_tel tel(uint32_t seq)
{
	return (struct mc_tel){.seq = seq, .n = 0};
}

ZTEST(rtc, test_crc_detects_power_loss_and_corruption)
{
	zassert_false(mc_rtc_valid(&rtc)); /* not sealed yet */
	mc_rtc_seal(&rtc);
	zassert_true(mc_rtc_valid(&rtc));
	rtc.seq++;
	zassert_false(mc_rtc_valid(&rtc));
	mc_rtc_seal(&rtc);
	zassert_true(mc_rtc_valid(&rtc));

	struct mc_rtc garbage;

	memset(&garbage, 0xA5, sizeof(garbage));
	zassert_false(mc_rtc_valid(&garbage));
	memset(&garbage, 0, sizeof(garbage));
	zassert_false(mc_rtc_valid(&garbage));
}

ZTEST(rtc, test_fits_in_retained_ram)
{
	zassert_true(sizeof(struct mc_rtc) <= 4000, "%u bytes", (unsigned)sizeof(struct mc_rtc));
}

ZTEST(rtc, test_seq_is_monotonic)
{
	zassert_equal(mc_rtc_next_seq(&rtc), 1);
	zassert_equal(mc_rtc_next_seq(&rtc), 2);
}

ZTEST(rtc, test_buffer_keeps_order_and_drops_oldest)
{
	zassert_is_null(mc_tbuf_oldest(&rtc));
	for (uint32_t i = 1; i <= 9; i++) { /* 3 more than the 6 it holds */
		struct mc_tel t = tel(i);

		mc_tbuf_push(&rtc, &t);
	}
	zassert_equal(rtc.t_count, MC_TELEMETRY_BUFFER);
	for (uint32_t expect = 4; expect <= 9; expect++) {
		const struct mc_tel *t = mc_tbuf_oldest(&rtc);

		zassert_not_null(t);
		zassert_equal(t->seq, expect);
		mc_tbuf_drop_oldest(&rtc);
	}
	zassert_is_null(mc_tbuf_oldest(&rtc));
	mc_tbuf_drop_oldest(&rtc); /* harmless when empty */
}

ZTEST(rtc, test_next_wake_interval)
{
	struct mc_config cfg;

	mc_config_init(&cfg);
	cfg.wake_interval_s = 600;

	struct mc_ctx ctx = {.cfg = &cfg, .now = 1000, .time_synced = true, .hist = &rtc.hist};

	zassert_equal(mc_next_wake_s(&ctx, 3900), 600);
	zassert_equal(mc_next_wake_s(&ctx, 3200), 1800); /* low battery: less often */
	zassert_equal(mc_next_wake_s(&ctx, 0), 600);     /* no battery reading */
	cfg.wake_interval_s = 40000;
	zassert_equal(mc_next_wake_s(&ctx, 3200), MC_WAKE_INTERVAL_MAX_S);
	cfg.wake_interval_s = 600;
	/* a held pump run ends in 90 s: wake for that instead */
	mc_pump_begin_hold(&ctx.pump[2], "X", 1090);
	zassert_equal(mc_next_wake_s(&ctx, 3900), 90);
	ctx.now = 1095; /* overdue: wake right away */
	zassert_equal(mc_next_wake_s(&ctx, 3900), 1);
}

ZTEST_SUITE(rtc, NULL, NULL, before, NULL, NULL);

#include "mc_pins.h"

ZTEST(pins, test_adc_mapping_matches_the_esp32)
{
	int unit, ch;

	zassert_true(mc_pin_adc(34, &unit, &ch));
	zassert_equal(unit, 1);
	zassert_equal(ch, 6);
	zassert_true(mc_pin_adc(36, &unit, &ch));
	zassert_equal(ch, 0);
	zassert_true(mc_pin_adc(39, &unit, &ch));
	zassert_equal(ch, 3);
	zassert_true(mc_pin_adc(32, &unit, &ch));
	zassert_equal(ch, 4);
	zassert_true(mc_pin_adc(15, &unit, &ch));
	zassert_equal(unit, 2);
	zassert_equal(ch, 3); /* "D15 is ADC2 channel 3" */
	zassert_true(mc_pin_adc(25, &unit, &ch));
	zassert_equal(ch, 8);
	zassert_true(mc_pin_adc(27, &unit, &ch));
	zassert_equal(ch, 7);
	zassert_false(mc_pin_adc(5, &unit, &ch));
	zassert_false(mc_pin_adc(40, &unit, &ch));
	zassert_false(mc_pin_adc(-1, &unit, &ch));
}

ZTEST(pins, test_every_adc_pin_the_config_allows_is_mapped)
{
	/* the pins the config accepts for moisture sensors (mc_config.c adc_mask) */
	static const int allowed[] = {32, 33, 34, 35, 36, 39, 4, 12, 13, 14, 15, 25, 26, 27};
	int unit, ch;

	for (size_t i = 0; i < ARRAY_SIZE(allowed); i++) {
		zassert_true(mc_pin_adc(allowed[i], &unit, &ch), "GPIO %d", allowed[i]);
	}
}

ZTEST(pins, test_rtc_pins)
{
	zassert_true(mc_pin_rtc_capable(25));
	zassert_true(mc_pin_rtc_capable(32));
	zassert_false(mc_pin_rtc_capable(5));
	zassert_false(mc_pin_rtc_capable(18));
	zassert_false(mc_pin_rtc_capable(23));
}

ZTEST_SUITE(pins, NULL, NULL, NULL, NULL, NULL);
