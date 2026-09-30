#include <zephyr/ztest.h>
#include <string.h>

#include "contract_examples.h"
#include "mc_config.h"

static bool parse(const char *json, struct mc_config *c, struct mc_error *e)
{
	char buf[1024];

	strncpy(buf, json, sizeof(buf) - 1);
	buf[sizeof(buf) - 1] = '\0';
	return mc_config_parse(buf, strlen(buf), c, e);
}

/* Parses and validates; returns the error code or NULL if the config is valid. */
static const char *verdict(const char *json, struct mc_error *e)
{
	struct mc_config c;

	if (!parse(json, &c, e)) {
		return e->code;
	}
	return mc_config_validate(&c, e) ? NULL : e->code;
}

ZTEST(config, test_contract_example_parses_and_is_valid)
{
	struct mc_config c;
	struct mc_error e;

	zassert_true(EXAMPLE_DESIRED_N >= 1);
	for (int i = 0; i < EXAMPLE_DESIRED_N; i++) {
		zassert_true(parse(example_desired[i], &c, &e), "parse: %s", e.detail);
		zassert_true(mc_config_validate(&c, &e), "%s: %s", e.code, e.detail);
	}
	zassert_true(parse(example_desired[0], &c, &e));
	zassert_equal(c.rev, 8);
	zassert_equal(c.wake_interval_s, 600);
	zassert_equal(c.n, 4);
	zassert_equal(c.slots[0].module, MC_MOD_MOISTURE_CAPACITIVE);
	zassert_equal(c.slots[0].pin, 34);
	zassert_equal(c.slots[1].cal_dry, 3050);
	zassert_equal(c.slots[2].module, MC_MOD_PUMP_RELAY);
	zassert_true(c.slots[2].active_high);
	zassert_equal(c.slots[2].max_run_s, 60);
	zassert_equal(c.slots[2].min_pause_s, 600);
	zassert_equal(c.slots[3].module, MC_MOD_DS18B20);
}

ZTEST(config, test_defaults_for_optional_fields)
{
	struct mc_config c;
	struct mc_error e;

	zassert_true(parse("{\"rev\":1,\"wake_interval_s\":900,\"slots\":["
			   "{\"slot\":0,\"module\":\"moisture_capacitive\",\"pin\":34},"
			   "{\"slot\":2,\"module\":\"pump_relay\",\"pin\":25,\"max_run_s\":10}]}",
			   &c, &e));
	zassert_equal(c.slots[0].cal_dry, MC_CAL_DRY_DEFAULT);
	zassert_equal(c.slots[0].cal_wet, MC_CAL_WET_DEFAULT);
	zassert_equal(c.slots[1].min_pause_s, 0);
	zassert_true(c.slots[1].active_high);
	zassert_true(mc_config_validate(&c, &e));
}

ZTEST(config, test_unknown_fields_are_ignored)
{
	struct mc_error e;

	zassert_is_null(verdict("{\"rev\":1,\"wake_interval_s\":600,\"future\":[1,2,{\"a\":1}],"
				"\"slots\":[{\"slot\":0,\"module\":\"moisture_capacitive\","
				"\"pin\":34,\"color\":\"red\"}]}", &e));
}

#define SLOT(module, pin, extra) "{\"slot\":0,\"module\":\"" module "\",\"pin\":" #pin extra "}"
#define DOC(slots) "{\"rev\":2,\"wake_interval_s\":600,\"slots\":[" slots "]}"

ZTEST(config, test_pin_rules)
{
	struct mc_error e;

	/* outputs on input-only pins */
	zassert_str_equal(verdict(DOC(SLOT("pump_relay", 34, ",\"max_run_s\":10")), &e),
			  "pin_not_output");
	zassert_equal(e.slot, 0);
	zassert_not_null(strstr(e.detail, "GPIO 34"));
	/* reserved: flash, UART, LED, BOOT */
	for (int pin = 0; pin < 40; pin++) {
		bool reserved = pin <= 3 || (pin >= 6 && pin <= 11);
		char doc[160];

		snprintk(doc, sizeof(doc), DOC("{\"slot\":0,\"module\":\"moisture_capacitive\","
					       "\"pin\":%d}"), pin);
		const char *v = verdict(doc, &e);

		if (reserved) {
			zassert_str_equal(v, "pin_reserved", "pin %d", pin);
		}
	}
	/* a moisture sensor on a pin without ADC */
	zassert_str_equal(verdict(DOC(SLOT("moisture_capacitive", 5, "")), &e), "out_of_range");
	/* pin beyond the GPIO range */
	zassert_str_equal(verdict(DOC(SLOT("moisture_capacitive", 99, "")), &e), "out_of_range");
	/* ADC1 and ADC2 pins are fine for sensors */
	zassert_is_null(verdict(DOC(SLOT("moisture_capacitive", 32, "")), &e));
	zassert_is_null(verdict(DOC(SLOT("moisture_capacitive", 15, "")), &e));
}

ZTEST(config, test_conflicts_and_slot_indexes)
{
	struct mc_error e;

	zassert_str_equal(verdict(DOC("{\"slot\":0,\"module\":\"moisture_capacitive\",\"pin\":34},"
				      "{\"slot\":1,\"module\":\"moisture_capacitive\",\"pin\":34}"),
				  &e), "pin_conflict");
	zassert_equal(e.slot, 1);
	zassert_not_null(strstr(e.detail, "slot 0"));
	zassert_str_equal(verdict(DOC("{\"slot\":0,\"module\":\"moisture_capacitive\",\"pin\":34},"
				      "{\"slot\":0,\"module\":\"moisture_capacitive\",\"pin\":35}"),
				  &e), "out_of_range");
	zassert_str_equal(verdict(DOC("{\"slot\":6,\"module\":\"moisture_capacitive\",\"pin\":34}"),
				  &e), "out_of_range");
}

ZTEST(config, test_modules_and_actuator_limits)
{
	struct mc_error e;

	zassert_str_equal(verdict(DOC(SLOT("laser", 25, "")), &e), "unknown_module");
	zassert_str_equal(verdict(DOC(SLOT("pump_relay", 25, "")), &e), "out_of_range"); /* no max_run_s */
	zassert_str_equal(verdict(DOC(SLOT("pump_relay", 25, ",\"max_run_s\":301")), &e),
			  "out_of_range");
	zassert_is_null(verdict(DOC(SLOT("pump_relay", 25, ",\"max_run_s\":300")), &e));
	zassert_str_equal(verdict(DOC(SLOT("moisture_capacitive", 34,
					   ",\"cal\":{\"dry\":1000,\"wet\":1000}")), &e),
			  "out_of_range");
	zassert_str_equal(verdict(DOC("{\"slot\":0,\"module\":\"sht3x\"}"), &e), "out_of_range");
	zassert_is_null(verdict(DOC("{\"slot\":0,\"module\":\"sht3x\",\"addr\":68}"), &e));
	zassert_str_equal(verdict(DOC("{\"slot\":0,\"module\":\"sht3x\",\"addr\":2}"), &e),
			  "out_of_range");
}

ZTEST(config, test_document_level_limits)
{
	struct mc_error e;

	zassert_str_equal(verdict("{\"rev\":1,\"wake_interval_s\":59,\"slots\":[]}", &e),
			  "out_of_range");
	zassert_str_equal(verdict("{\"rev\":1,\"wake_interval_s\":86401,\"slots\":[]}", &e),
			  "out_of_range");
	zassert_is_null(verdict("{\"rev\":1,\"wake_interval_s\":60,\"slots\":[]}", &e));
	zassert_str_equal(verdict("{\"wake_interval_s\":600,\"slots\":[]}", &e), "out_of_range");
	zassert_str_equal(verdict("{\"rev\":1,\"slots\":[]}", &e), "out_of_range");
	zassert_str_equal(verdict("{not json", &e), "out_of_range");
	zassert_str_equal(verdict("", &e), "out_of_range");
	/* seven slots do not fit the table */
	zassert_str_equal(verdict(DOC("{\"slot\":0},{\"slot\":1},{\"slot\":2},{\"slot\":3},"
				      "{\"slot\":4},{\"slot\":5},{\"slot\":6}"), &e), "out_of_range");
	zassert_not_null(strstr(e.detail, "at most 6"));
}

ZTEST(config, test_write_roundtrip)
{
	struct mc_config a, b;
	struct mc_error e;
	char out[768];
	struct mc_jw w;

	zassert_true(parse(example_desired[0], &a, &e));
	mc_jw_init(&w, out, sizeof(out));
	mc_jw_obj(&w);
	mc_config_write(&w, &a);
	mc_jw_end_obj(&w);
	zassert_true(mc_jw_finish(&w) > 0);
	zassert_true(parse(out, &b, &e), "%s", out);
	zassert_equal(b.rev, 8);
	zassert_true(mc_config_same(&a, &b));
	b.slots[2].max_run_s = 61;
	zassert_false(mc_config_same(&a, &b));
}

ZTEST_SUITE(config, NULL, NULL, NULL, NULL, NULL);
