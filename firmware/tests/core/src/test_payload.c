#include <zephyr/ztest.h>
#include <string.h>

#include "mc_payload.h"

#define CAP 600

ZTEST(payload, test_status_messages)
{
	char b[128];

	zassert_true(mc_enc_status_online(b, sizeof(b), 5521) > 0);
	zassert_str_equal(b, "{\"state\":\"online\",\"fw\":\"" MC_FW_VERSION "\",\"boot\":5521}");
	zassert_true(mc_enc_status_sleeping(b, sizeof(b), 600) > 0);
	zassert_str_equal(b, "{\"state\":\"sleeping\",\"next_wake_s\":600}");
	zassert_true(mc_enc_status_offline(b, sizeof(b)) > 0);
	zassert_str_equal(b, "{\"state\":\"offline\"}");
	zassert_true(mc_enc_status_service(b, sizeof(b), 900) > 0);
	zassert_str_equal(b, "{\"state\":\"service\",\"until_s\":900}");
}

ZTEST(payload, test_telemetry_matches_contract_example)
{
	/* mqtt.md §4.2: two soil sensors (one without signal) and a temperature. */
	struct mc_tel t = {
		.seq = 18422, .ts = 1790412305, .cfg_rev = 8, .n = 3,
		.r = {
			{.slot = 0, .type = MC_TYPE_SOIL_MOISTURE, .has_value = true,
			 .value_x10 = 415, .has_raw = true, .raw = 2143},
			{.slot = 1, .type = MC_TYPE_SOIL_MOISTURE, .err = MC_SENSOR_NO_SIGNAL,
			 .has_raw = true, .raw = 4095},
			{.slot = 3, .type = MC_TYPE_TEMPERATURE, .has_value = true, .value_x10 = 213},
		},
		.h = {.batt_mv = 3910, .rssi = -67, .wake = MC_WAKE_TIMER, .cycle_ms = 2140,
		      .wifi_ms = 1450},
	};
	char b[CAP];

	zassert_true(mc_enc_telemetry(b, sizeof(b), &t) > 0);
	zassert_str_equal(b,
		"{\"seq\":18422,\"ts\":1790412305,\"cfg_rev\":8,\"readings\":["
		"{\"slot\":0,\"type\":\"soil_moisture\",\"value\":41.5,\"unit\":\"%\",\"raw\":2143},"
		"{\"slot\":1,\"type\":\"soil_moisture\",\"error\":\"no_signal\",\"raw\":4095},"
		"{\"slot\":3,\"type\":\"temperature\",\"value\":21.3,\"unit\":\"\xC2\xB0" "C\"}],"
		"\"health\":{\"batt_mv\":3910,\"rssi\":-67,\"wake\":\"timer\",\"cycle_ms\":2140,"
		"\"wifi_ms\":1450}}");
}

ZTEST(payload, test_telemetry_omits_unknown_fields)
{
	struct mc_tel t = {.seq = 1, .ts = 0, .cfg_rev = 0, .n = 0,
			   .h = {.batt_mv = 3700, .rssi = -80, .wake = MC_WAKE_POWER_ON,
				 .cycle_ms = -1, .wifi_ms = -1}};
	char b[CAP];

	zassert_true(mc_enc_telemetry(b, sizeof(b), &t) > 0);
	zassert_str_equal(b, "{\"seq\":1,\"cfg_rev\":0,\"readings\":[],"
			     "\"health\":{\"batt_mv\":3700,\"rssi\":-80,\"wake\":\"power_on\"}}");
}

ZTEST(payload, test_events)
{
	struct mc_event e = {.seq = 18423, .ts = 1790412306, .kind = MC_EV_SAFETY_STOP, .slot = 2,
			     .detail = "max_run_s reached"};
	char b[CAP];

	zassert_true(mc_enc_event(b, sizeof(b), &e) > 0);
	zassert_str_equal(b, "{\"seq\":18423,\"ts\":1790412306,\"kind\":\"safety_stop\",\"slot\":2,"
			     "\"detail\":\"max_run_s reached\"}");
	e = (struct mc_event){.seq = 9, .kind = MC_EV_BOOT, .slot = -1};
	zassert_true(mc_enc_event(b, sizeof(b), &e) > 0);
	zassert_str_equal(b, "{\"seq\":9,\"kind\":\"boot\"}");
}

ZTEST(payload, test_acks_match_contract_examples)
{
	char b[CAP];
	struct mc_ack a = {.id = "01J8ZQ6H7K2M4N5P6Q7R8S9T0V", .status = MC_ACK_DONE,
			   .ts = 1790412318};

	zassert_true(mc_enc_ack(b, sizeof(b), &a) > 0);
	zassert_str_equal(b, "{\"id\":\"01J8ZQ6H7K2M4N5P6Q7R8S9T0V\",\"status\":\"done\","
			     "\"ts\":1790412318}");
	a = (struct mc_ack){.id = "01J8ZQ6H7K2M4N5P6Q7R8S9T0V", .status = MC_ACK_RUNNING,
			    .ends_at = 1790413500};
	zassert_true(mc_enc_ack(b, sizeof(b), &a) > 0);
	zassert_str_equal(b, "{\"id\":\"01J8ZQ6H7K2M4N5P6Q7R8S9T0V\",\"status\":\"running\","
			     "\"ends_at\":1790413500}");
	a = (struct mc_ack){.id = "01J8ZQ6H7K2M4N5P6Q7R8S9T0V", .status = MC_ACK_REJECTED,
			    .reason = "expired"};
	zassert_true(mc_enc_ack(b, sizeof(b), &a) > 0);
	zassert_str_equal(b, "{\"id\":\"01J8ZQ6H7K2M4N5P6Q7R8S9T0V\",\"status\":\"rejected\","
			     "\"reason\":\"expired\"}");
}

ZTEST(payload, test_config_state_applied_and_rejected)
{
	struct mc_config c;
	struct mc_error err = {.slot = 2, .code = "pin_not_output"};
	char b[CAP];

	mc_config_init(&c);
	c.rev = 7;
	c.n = 2;
	c.slots[0] = (struct mc_slot){.slot = 0, .module = MC_MOD_MOISTURE_CAPACITIVE, .pin = 34,
				      .cal_dry = 3000, .cal_wet = 1200};
	c.slots[1] = (struct mc_slot){.slot = 2, .module = MC_MOD_PUMP_RELAY, .pin = 25,
				      .active_high = true, .max_run_s = 60, .min_pause_s = 600};
	strcpy(err.detail, "GPIO 34 is input-only");

	zassert_true(mc_enc_config_state(b, sizeof(b), &c, MC_CFG_REJECTED, 8, &err) > 0);
	zassert_str_equal(b,
		"{\"rev\":7,\"result\":\"rejected\",\"rejected_rev\":8,\"error\":{\"slot\":2,"
		"\"code\":\"pin_not_output\",\"detail\":\"GPIO 34 is input-only\"},"
		"\"wake_interval_s\":600,\"slots\":["
		"{\"slot\":0,\"module\":\"moisture_capacitive\",\"pin\":34,"
		"\"cal\":{\"dry\":3000,\"wet\":1200}},"
		"{\"slot\":2,\"module\":\"pump_relay\",\"pin\":25,\"active_high\":true,"
		"\"max_run_s\":60,\"min_pause_s\":600}],\"detected\":[],"
		"\"limits\":{\"max_run_s_hard\":300,\"slots_max\":6}}");
	zassert_true(mc_enc_config_state(b, sizeof(b), &c, MC_CFG_BOOT, 0, NULL) > 0);
	zassert_not_null(strstr(b, "\"result\":\"boot\""));
	zassert_is_null(strstr(b, "rejected_rev"));
}

ZTEST(payload, test_too_small_buffer_fails)
{
	char b[10];

	zassert_equal(mc_enc_status_online(b, sizeof(b), 1), -1);
}

ZTEST_SUITE(payload, NULL, NULL, NULL, NULL, NULL);
