/* Low power groundwork (PlantModule/specs.md 18): the power settings of the configuration, the switched sensor supply
 * around a sample, and when the core allows the HAL to sleep. The HAL itself does not sleep yet. */
#include <string.h>

#include "mc_factory.h"
#include "sim.h"
#include "unity.h"

static sim_t S;

#define SETTLE_MS 200

/* carrier-v1 plus what carrier v2 is meant to have: a switched sensor rail and the sleep modes. */
static mc_board_t sleepy_board(void)
{
    mc_board_t b = *mc_board_find("carrier-v1");
    b.name = "test-sleepy";
    b.sensor_power.present = true;
    b.sensor_power.gpio = 10;
    b.sensor_power.active_high = true;
    b.sensor_power.settle_ms = SETTLE_MS;
    b.power_modes = (1u << MC_POWER_MODE_LIGHT_SLEEP) | (1u << MC_POWER_MODE_DEEP_SLEEP);
    return b;
}

static void operational_on(const mc_board_t *board, uint8_t mode)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.power_mode = mode;
    cfg.report_interval_s = 10;
    sim_init_board(&S, board);
    sim_to_operational(&S, &cfg);
}

static void operational_v1(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.report_interval_s = 10;
    sim_init(&S, "carrier-v1");
    sim_to_operational(&S, &cfg);
}

/* ---- configuration ---------------------------------------------------------------------------------------- */

static void test_defaults_are_always_on_with_a_three_second_poll_and_a_five_second_window(void)
{
    mc_config_t c;
    mc_config_default(&c);
    TEST_ASSERT_EQUAL_UINT8(MC_POWER_MODE_ALWAYS_ON, c.power_mode);
    TEST_ASSERT_EQUAL_UINT16(3000, c.poll_interval_ms);
    TEST_ASSERT_EQUAL_UINT8(5, c.awake_s);
}

static void test_the_schema_three_blob_round_trips_the_power_settings(void)
{
    mc_config_t c, d;
    sim_cfg_default(&c);
    c.power_mode = MC_POWER_MODE_DEEP_SLEEP;
    c.poll_interval_ms = 1500;
    c.awake_s = 12;
    uint8_t blob[MC_CONFIG_BLOB_SIZE];
    TEST_ASSERT_EQUAL_UINT(95, MC_CONFIG_BLOB_SIZE);
    TEST_ASSERT_EQUAL_UINT(MC_CONFIG_BLOB_SIZE, mc_config_encode(&c, blob));
    TEST_ASSERT_EQUAL_UINT8(3, blob[0]);
    TEST_ASSERT_TRUE(mc_config_decode(blob, sizeof blob, &d));
    TEST_ASSERT_TRUE(mc_config_same(&c, &d));
    TEST_ASSERT_EQUAL_UINT8(MC_POWER_MODE_DEEP_SLEEP, d.power_mode);
    TEST_ASSERT_EQUAL_UINT16(1500, d.poll_interval_ms);
    TEST_ASSERT_EQUAL_UINT8(12, d.awake_s);
    blob[17] ^= 1; /* any flipped bit is caught by the crc */
    TEST_ASSERT_FALSE(mc_config_decode(blob, sizeof blob, &d));
}

static void test_the_stored_schema_two_configuration_is_migrated_as_always_on(void)
{
    mc_config_t c, d;
    sim_cfg_default(&c);
    c.batt_low_mv = 3650;
    c.batt_cal_permille = 1020;
    uint8_t blob[MC_CONFIG_BLOB_SIZE];
    mc_config_encode(&c, blob);
    uint8_t v2[MC_CONFIG_BLOB_SIZE_V2];
    v2[0] = 2;
    memcpy(v2 + 1, blob + 1, 14);          /* rev, intervals, battery fields */
    memcpy(v2 + 15, blob + 19, 72);        /* the slot table, after the power settings */
    uint32_t crc = mc_crc32(v2, MC_CONFIG_BLOB_SIZE_V2 - 4);
    for (int k = 0; k < 4; k++) {
        v2[MC_CONFIG_BLOB_SIZE_V2 - 4 + k] = (uint8_t)(crc >> (8 * k));
    }
    TEST_ASSERT_TRUE(mc_config_decode(v2, sizeof v2, &d));
    TEST_ASSERT_EQUAL_UINT8(MC_POWER_MODE_ALWAYS_ON, d.power_mode);
    TEST_ASSERT_EQUAL_UINT16(3000, d.poll_interval_ms);
    TEST_ASSERT_EQUAL_UINT8(5, d.awake_s);
    TEST_ASSERT_EQUAL_UINT16(3650, d.batt_low_mv);
    TEST_ASSERT_EQUAL_UINT16(1020, d.batt_cal_permille);
    TEST_ASSERT_TRUE_MESSAGE(mc_config_same(&c, &d), "the rest is untouched");
    TEST_ASSERT_FALSE_MESSAGE(mc_config_decode(v2, sizeof v2 - 1, &d), "a truncated blob");
}

static void test_the_power_settings_are_range_checked(void)
{
    mc_board_t b = sleepy_board();
    mc_config_t c;
    mc_cfg_err_t e;
    sim_cfg_default(&c);
    TEST_ASSERT_TRUE(mc_config_validate(&c, &b, &e));
    c.power_mode = 3;
    TEST_ASSERT_FALSE(mc_config_validate(&c, &b, &e));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_ERROR_OUT_OF_RANGE, e.code);
    c.power_mode = 1;
    c.poll_interval_ms = 499;
    TEST_ASSERT_FALSE(mc_config_validate(&c, &b, &e));
    c.poll_interval_ms = 5001;
    TEST_ASSERT_FALSE(mc_config_validate(&c, &b, &e));
    c.poll_interval_ms = 500;
    c.awake_s = 1;
    TEST_ASSERT_FALSE(mc_config_validate(&c, &b, &e));
    c.awake_s = 31;
    TEST_ASSERT_FALSE(mc_config_validate(&c, &b, &e));
    c.awake_s = 30;
    TEST_ASSERT_TRUE(mc_config_validate(&c, &b, &e));
}

static void test_a_mode_the_board_cannot_run_is_refused_as_role_unsupported(void)
{
    mc_config_t c;
    mc_cfg_err_t e;
    sim_cfg_default(&c);
    c.power_mode = MC_POWER_MODE_LIGHT_SLEEP;
    TEST_ASSERT_FALSE(mc_config_validate(&c, mc_board_find("carrier-v1"), &e));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_ERROR_ROLE_UNSUPPORTED, e.code);
    TEST_ASSERT_EQUAL_UINT8(MC_SLOT_NONE, e.slot);
    c.power_mode = MC_POWER_MODE_ALWAYS_ON;
    TEST_ASSERT_TRUE(mc_config_validate(&c, mc_board_find("carrier-v1"), &e));
}

static void test_writes_stage_the_power_settings_and_the_commit_applies_them(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_ALWAYS_ON);
    uint8_t mode = MC_POWER_MODE_LIGHT_SLEEP, awake = 9;
    sim_send(&S, ev_write_bytes(MC_ATTR_POWER_MODE, &mode, 1));   /* enum8 */
    sim_send(&S, ev_write_u16(MC_ATTR_POLL_INTERVAL_MS, 2000));
    sim_send(&S, ev_write_bytes(MC_ATTR_AWAKE_S, &awake, 1));     /* uint8 */
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(MC_POWER_MODE_ALWAYS_ON, S.core.cfg.power_mode, "staged only");
    sim_send(&S, ev_commit((uint16_t)(S.core.cfg.rev + 1)));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_OK, S.core.cfg_result);
    TEST_ASSERT_EQUAL_UINT8(MC_POWER_MODE_LIGHT_SLEEP, S.core.cfg.power_mode);
    TEST_ASSERT_EQUAL_UINT16(2000, S.core.cfg.poll_interval_ms);
    TEST_ASSERT_EQUAL_UINT8(9, S.core.cfg.awake_s);
    TEST_ASSERT_EQUAL_INT(1, S.persist_config_calls);
}

static void test_the_commit_of_an_unsupported_mode_is_rejected_and_nothing_changes(void)
{
    operational_v1();
    uint8_t mode = MC_POWER_MODE_DEEP_SLEEP;
    uint16_t rev = S.core.cfg.rev;
    sim_send(&S, ev_write_bytes(MC_ATTR_POWER_MODE, &mode, 1));
    sim_send(&S, ev_commit((uint16_t)(rev + 1)));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.core.cfg_result);
    TEST_ASSERT_EQUAL_UINT16((uint16_t)(MC_CFG_ERROR_ROLE_UNSUPPORTED << 8 | MC_SLOT_NONE), S.core.cfg_error);
    TEST_ASSERT_EQUAL_UINT8(MC_POWER_MODE_ALWAYS_ON, S.core.cfg.power_mode);
    TEST_ASSERT_EQUAL_UINT16(rev, S.core.cfg.rev);
    TEST_ASSERT_EQUAL_INT(0, S.persist_config_calls);
}

static void test_a_write_that_is_too_short_for_its_attribute_is_rejected_at_the_commit(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_ALWAYS_ON);
    sim_send(&S, ev_write_bytes(MC_ATTR_POLL_INTERVAL_MS, (const uint8_t *)"\x10", 1)); /* needs two bytes */
    sim_send(&S, ev_commit((uint16_t)(S.core.cfg.rev + 1)));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.core.cfg_result);
}

/* ---- the switched sensor supply ------------------------------------------------------------------------------ */

static void test_the_rail_is_on_for_the_settle_time_before_the_first_read_and_off_after_the_sample(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_ALWAYS_ON);
    TEST_ASSERT_FALSE(S.rail_on);
    sim_advance(&S, 1000 + 10);                       /* the sample starts 1 s after the start */
    TEST_ASSERT_TRUE(S.rail_on);
    TEST_ASSERT_EQUAL_INT(MC_SN_SETTLING, S.core.sn);
    TEST_ASSERT_EQUAL_INT(0, S.read_slot_calls);      /* nothing is read while the sensors settle */
    sim_advance(&S, SETTLE_MS);
    TEST_ASSERT_EQUAL_INT(1, S.read_slot_calls);
    sim_advance(&S, 200);
    TEST_ASSERT_FALSE_MESSAGE(S.rail_on, "off as soon as the sample is complete");
    TEST_ASSERT_EQUAL_INT(1, S.rail_on_calls);
    TEST_ASSERT_EQUAL_INT(1, S.rail_off_calls);
    TEST_ASSERT_EQUAL_INT(0, S.reads_without_power);
    TEST_ASSERT_EQUAL_INT(0, S.reads_before_settled);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.seq);
    TEST_ASSERT_EQUAL_INT(1, S.reports);
}

static void test_every_sample_switches_the_rail_again(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_ALWAYS_ON);
    sim_advance(&S, 1000 + SETTLE_MS + 300);
    for (int i = 0; i < 3; i++) {
        sim_advance(&S, 10000);
    }
    TEST_ASSERT_TRUE(S.core.seq >= 3);
    TEST_ASSERT_EQUAL_INT(S.core.seq, S.rail_on_calls);
    TEST_ASSERT_EQUAL_INT_MESSAGE(S.core.seq, S.rail_off_calls, "as often on as off");
    TEST_ASSERT_EQUAL_INT(0, S.reads_without_power);
    TEST_ASSERT_EQUAL_INT(0, S.reads_before_settled);
}

static void test_the_rail_goes_off_also_when_a_sensor_does_not_answer(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_ALWAYS_ON);
    S.adc_silent[0] = true;
    sim_advance(&S, 1000 + SETTLE_MS + MC_SAMPLE_WINDOW_MS + 100);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.seq);
    TEST_ASSERT_FALSE(S.rail_on);
}

static void test_leaving_the_network_in_the_middle_of_a_sample_switches_the_rail_off(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_ALWAYS_ON);
    sim_advance(&S, 1000 + 50);
    TEST_ASSERT_TRUE(S.rail_on);
    sim_send(&S, ev_simple(MC_EV_ZB_LEFT));
    TEST_ASSERT_FALSE(S.rail_on);
    sim_advance(&S, 5000);
    TEST_ASSERT_EQUAL_INT_MESSAGE(0, S.read_slot_calls, "the settle timer of the dead sample does nothing");
}

static void test_report_now_during_settling_does_not_start_a_second_sample(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_ALWAYS_ON);
    sim_advance(&S, 1000 + 50);
    sim_send(&S, ev_action(77, MC_DEVICE_ACTION_REPORT_NOW));
    sim_advance(&S, SETTLE_MS + 300);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.seq);
    TEST_ASSERT_EQUAL_INT(1, S.rail_on_calls);
}

static void test_a_board_without_a_switched_rail_never_switches_one(void)
{
    operational_v1();
    sim_advance(&S, 1000 + 500);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.seq);
    TEST_ASSERT_EQUAL_INT(0, S.rail_on_calls);
    TEST_ASSERT_EQUAL_INT(0, S.rail_off_calls);
}

/* ---- when the HAL may sleep ---------------------------------------------------------------------------------- */

static void idle(void)
{
    sim_advance(&S, 1000 + SETTLE_MS + 300); /* the first sample is done */
}

static void test_always_on_never_sleeps(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_ALWAYS_ON);
    idle();
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
}

static void test_light_sleep_is_allowed_when_idle_and_not_while_sampling(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_LIGHT_SLEEP);
    sim_advance(&S, 500);
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core), "waiting for the first sample");
    sim_advance(&S, 600);                                   /* settling */
    TEST_ASSERT_EQUAL_INT(MC_SN_SETTLING, S.core.sn);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
    sim_advance(&S, SETTLE_MS - 10);                        /* reading */
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
    sim_advance(&S, 200);
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SN_REPORTING, S.core.sn, "the report is out");
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
    sim_advance(&S, MC_REPORT_TIMEOUT_MS + 100);              /* no answer: the timeout ends it */
    TEST_ASSERT_EQUAL_INT(MC_SN_IDLE, S.core.sn);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core));
}

static void test_a_report_in_flight_keeps_the_module_awake_until_it_is_answered_or_times_out(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_LIGHT_SLEEP);
    sim_advance(&S, 1000 + SETTLE_MS + 100);
    TEST_ASSERT_EQUAL_INT(MC_SN_REPORTING, S.core.sn);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core));
}

static void test_deep_sleep_is_only_light_while_a_pump_runs_and_after_it_in_fast_mode(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_DEEP_SLEEP);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    idle();
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_DEEP, mc_core_sleep_allowed(&S.core));
    sim_send(&S, ev_pump_run(500, 2, 20, 60));
    TEST_ASSERT_TRUE(mc_core_pump_running(&S.core));
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core), "L7: never deep during a run");
    sim_advance(&S, 21000);
    TEST_ASSERT_FALSE(mc_core_pump_running(&S.core));
    TEST_ASSERT_TRUE(S.core.fast);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core), "fast reporting after a run");
    sim_advance(&S, (uint32_t)S.core.cfg.fast_report_hold_s * 1000 + 2000);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_FALSE(S.core.fast);
}

static void test_an_open_configuration_transaction_or_the_identify_blink_keeps_it_awake(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_LIGHT_SLEEP);
    idle();
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core));
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 60));
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
    sim_send(&S, ev_commit((uint16_t)(S.core.cfg.rev + 1)));
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core));
    sim_send(&S, ev_action(9, MC_DEVICE_ACTION_IDENTIFY));
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
    sim_advance(&S, MC_IDENTIFY_MS + 100);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core));
}

static void test_only_an_operational_module_sleeps(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_LIGHT_SLEEP);
    idle();
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core));
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    TEST_ASSERT_EQUAL_INT(MC_LC_REJOINING, S.core.lc);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
}

static void test_a_stored_mode_the_board_cannot_run_does_not_sleep(void)
{
    mc_board_t b = sleepy_board();
    b.power_modes = 0;
    operational_on(&b, MC_POWER_MODE_ALWAYS_ON);
    S.core.cfg.power_mode = MC_POWER_MODE_LIGHT_SLEEP; /* e.g. a configuration carried over from another board */
    idle();
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
}

static void test_the_poll_interval_is_capped_at_one_second_while_a_pump_runs(void)
{
    mc_board_t b = sleepy_board();
    operational_on(&b, MC_POWER_MODE_LIGHT_SLEEP);
    idle();
    TEST_ASSERT_EQUAL_UINT16(3000, mc_core_poll_ms(&S.core));
    sim_send(&S, ev_pump_run(501, 2, 10, 60));
    TEST_ASSERT_EQUAL_UINT16(1000, mc_core_poll_ms(&S.core));
    sim_advance(&S, 11000);
    TEST_ASSERT_EQUAL_UINT16(3000, mc_core_poll_ms(&S.core));
    S.core.cfg.poll_interval_ms = 500;
    sim_send(&S, ev_pump_run(502, 2, 10, 60));
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(500, mc_core_poll_ms(&S.core), "a shorter configured interval stays");
}

void run_power_tests(void)
{
    RUN_TEST(test_defaults_are_always_on_with_a_three_second_poll_and_a_five_second_window);
    RUN_TEST(test_the_schema_three_blob_round_trips_the_power_settings);
    RUN_TEST(test_the_stored_schema_two_configuration_is_migrated_as_always_on);
    RUN_TEST(test_the_power_settings_are_range_checked);
    RUN_TEST(test_a_mode_the_board_cannot_run_is_refused_as_role_unsupported);
    RUN_TEST(test_writes_stage_the_power_settings_and_the_commit_applies_them);
    RUN_TEST(test_the_commit_of_an_unsupported_mode_is_rejected_and_nothing_changes);
    RUN_TEST(test_a_write_that_is_too_short_for_its_attribute_is_rejected_at_the_commit);
    RUN_TEST(test_the_rail_is_on_for_the_settle_time_before_the_first_read_and_off_after_the_sample);
    RUN_TEST(test_every_sample_switches_the_rail_again);
    RUN_TEST(test_the_rail_goes_off_also_when_a_sensor_does_not_answer);
    RUN_TEST(test_leaving_the_network_in_the_middle_of_a_sample_switches_the_rail_off);
    RUN_TEST(test_report_now_during_settling_does_not_start_a_second_sample);
    RUN_TEST(test_a_board_without_a_switched_rail_never_switches_one);
    RUN_TEST(test_always_on_never_sleeps);
    RUN_TEST(test_light_sleep_is_allowed_when_idle_and_not_while_sampling);
    RUN_TEST(test_a_report_in_flight_keeps_the_module_awake_until_it_is_answered_or_times_out);
    RUN_TEST(test_deep_sleep_is_only_light_while_a_pump_runs_and_after_it_in_fast_mode);
    RUN_TEST(test_an_open_configuration_transaction_or_the_identify_blink_keeps_it_awake);
    RUN_TEST(test_only_an_operational_module_sleeps);
    RUN_TEST(test_a_stored_mode_the_board_cannot_run_does_not_sleep);
    RUN_TEST(test_the_poll_interval_is_capped_at_one_second_while_a_pump_runs);
}
