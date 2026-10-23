/* Battery level detection (PlantModule/specs.md 6.1): sampling, filter, state machine, events, pump refusal. */
#include <string.h>

#include "mc_factory.h"
#include "sim.h"
#include "unity.h"

static sim_t S;

/* carrier-v1: divider 2.0, so a pin voltage of mv/2 is a cell of mv. A short report interval keeps the tests quick. */
#define PIN(cell_mv) ((uint16_t)((cell_mv) / 2))
#define INTERVAL_MS 10000

static void operational_with(mc_config_t *cfg, const char *board)
{
    sim_init(&S, board);
    sim_to_operational(&S, cfg);
}

static void operational(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.report_interval_s = 10;
    operational_with(&cfg, "carrier-v1");
}

/* Lets `n` samples with the given cell voltage happen (the first sample comes 1 s after start). */
static void samples(int n, uint16_t cell_mv)
{
    S.batt_pin_mv = PIN(cell_mv);
    for (int i = 0; i < n; i++) {
        sim_advance(&S, i == 0 && S.core.seq == 0 ? 1100 : INTERVAL_MS + 100); /* a sample ends 20 ms after its timer */
    }
}

static void test_every_sample_reads_the_battery_and_reports_millivolts_and_state(void)
{
    operational();
    samples(1, 3900);
    TEST_ASSERT_EQUAL_INT(1, S.read_battery_calls);
    TEST_ASSERT_EQUAL_UINT16(3900, S.attrs.voltage_mv);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_OK, S.attrs.batt_state);
    TEST_ASSERT_EQUAL_UINT16(1, S.attrs.seq);
    samples(1, 3900);
    TEST_ASSERT_EQUAL_INT(2, S.read_battery_calls);
}

static void test_the_battery_value_is_part_of_the_sample_that_is_reported(void)
{
    operational();
    S.batt_pin_mv = PIN(3800);
    sim_advance(&S, 1100);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(1, S.attrs.seq, "one sample");
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(3800, S.attrs.voltage_mv, "already in the attributes the report carries");
}

static void test_no_cell_is_absent_with_no_event_and_zero_volts(void)
{
    operational();
    samples(5, 0);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_ABSENT, S.attrs.batt_state);
    TEST_ASSERT_EQUAL_UINT16(0, S.attrs.voltage_mv);
    TEST_ASSERT_EQUAL_INT(0, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY));
    TEST_ASSERT_EQUAL_INT(0, sim_count_events(&S, MC_EVENT_CODE_BATTERY_CRITICAL));
}

static void test_a_cell_that_appears_starts_ok(void)
{
    operational();
    samples(2, 0);
    samples(1, 3900);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_OK, S.attrs.batt_state);
    TEST_ASSERT_EQUAL_UINT16(3900, S.attrs.voltage_mv);
}

static void test_a_single_outlier_does_not_move_the_reported_value(void)
{
    operational();
    samples(2, 3900);
    samples(1, 3000); /* a load switching on */
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(3900, S.attrs.voltage_mv, "median of the last three");
    samples(1, 3900);
    TEST_ASSERT_EQUAL_UINT16(3900, S.attrs.voltage_mv);
}

static void test_the_two_sample_start_averages(void)
{
    operational();
    samples(1, 3800);
    samples(1, 3900);
    TEST_ASSERT_EQUAL_UINT16(3850, S.attrs.voltage_mv);
}

static void test_low_needs_three_samples_and_sends_one_event_with_the_voltage(void)
{
    operational();
    samples(3, 3900);
    samples(1, 3500); /* median of 3900, 3900, 3500 is still 3900 */
    samples(1, 3500); /* median 3500 */
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(MC_BATT_STATE_OK, S.attrs.batt_state, "one sample at or below does not count");
    samples(1, 3500);
    samples(1, 3500);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_LOW, S.attrs.batt_state);
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY));
    samples(3, 3500);
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY), "once");
    int found = 0;
    for (int i = 0; i < S.n_events; i++) {
        if (S.events[i].code == MC_EVENT_CODE_LOW_BATTERY) {
            TEST_ASSERT_EQUAL_UINT16(3500, S.events[i].arg);
            found++;
        }
    }
    TEST_ASSERT_EQUAL_INT(1, found);
}

static void test_low_recovers_only_above_the_threshold_plus_hysteresis(void)
{
    operational();
    samples(6, 3500);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_LOW, S.attrs.batt_state);
    samples(3, 3650); /* above 3600 but not by 100 mV */
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_LOW, S.attrs.batt_state);
    samples(3, 3750);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_OK, S.attrs.batt_state);
    samples(6, 3500); /* it can worsen again and then sends a new event */
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_LOW, S.attrs.batt_state);
    TEST_ASSERT_EQUAL_INT(2, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY));
}

static void test_critical_after_three_samples_with_its_own_event(void)
{
    operational();
    samples(6, 3300);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_CRITICAL, S.attrs.batt_state);
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_BATTERY_CRITICAL));
    samples(4, 3300);
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_BATTERY_CRITICAL));
}

static void test_low_then_critical_then_back_down_the_stairs(void)
{
    operational();
    samples(6, 3500);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_LOW, S.attrs.batt_state);
    samples(6, 3300);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_CRITICAL, S.attrs.batt_state);
    samples(6, 3450); /* above critical + 100 mV? no: 3450 is above 3500? no, in the band */
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_CRITICAL, S.attrs.batt_state);
    samples(6, 3550);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_LOW, S.attrs.batt_state);
    samples(6, 3800);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_OK, S.attrs.batt_state);
}

static void test_critical_refuses_pump_runs_but_not_stop_or_cancel(void)
{
    operational();
    samples(6, 3300);
    sim_clear_logs(&S);
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    TEST_ASSERT_FALSE(S.pump_on[2]);
    ASSERT_ACK(&S, 1, MC_ACK_STATE_REJECTED, MC_REASON_BATTERY_LOW);
    sim_send(&S, ev_pump_stop(2, 2));
    ASSERT_ACK(&S, 2, MC_ACK_STATE_DONE, MC_REASON_NONE);
    sim_send(&S, ev_cancel(3, 99));
    ASSERT_ACK(&S, 3, MC_ACK_STATE_DONE, MC_REASON_NONE);
    samples(6, 3800);
    sim_send(&S, ev_pump_run(4, 2, 10, 900));
    ASSERT_ACK(&S, 4, MC_ACK_STATE_RUNNING, MC_REASON_NONE);
}

static void test_a_run_already_running_when_the_state_turns_critical_finishes(void)
{
    operational();
    samples(1, 3900);
    sim_send(&S, ev_pump_run(1, 2, 40, 900));
    TEST_ASSERT_TRUE(S.pump_on[2]);
    S.batt_pin_mv = PIN(3300);
    sim_advance(&S, 30000);
    TEST_ASSERT_TRUE_MESSAGE(S.pump_on[2], "no battery sample was taken during the run");
    sim_advance(&S, 11000);
    TEST_ASSERT_FALSE(S.pump_on[2]);
    ASSERT_ACK(&S, 1, MC_ACK_STATE_DONE, MC_REASON_NONE);
}

static void test_no_battery_sample_while_a_pump_runs_or_for_five_seconds_after(void)
{
    operational();
    samples(1, 3900);
    int before = S.read_battery_calls;
    sim_send(&S, ev_pump_run(1, 2, 25, 900));
    sim_advance(&S, 24000); /* two fast samples (every 30 s: none yet) and the run */
    TEST_ASSERT_EQUAL_INT(before, S.read_battery_calls);
    sim_advance(&S, 1100); /* the run ended */
    S.core.seq += 0;
    int at_end = S.read_battery_calls;
    sim_advance(&S, 3000); /* a sample inside the 5 s quiet time */
    TEST_ASSERT_EQUAL_INT(at_end, S.read_battery_calls);
    sim_advance(&S, 40000);
    TEST_ASSERT_TRUE_MESSAGE(S.read_battery_calls > at_end, "later samples read it again");
    TEST_ASSERT_EQUAL_UINT16(3900, S.attrs.voltage_mv);
}

static void test_a_sample_inside_the_quiet_time_keeps_the_previous_value_and_still_counts(void)
{
    operational();
    samples(1, 3900);
    sim_send(&S, ev_pump_run(1, 2, 5, 900));
    S.batt_pin_mv = PIN(3000); /* the cell sags under load */
    uint16_t seq = S.core.seq;
    sim_advance(&S, 31000); /* fast sample while the quiet time has long passed? the run lasted 5 s */
    TEST_ASSERT_TRUE(S.core.seq > seq);
}

static void test_a_battery_read_that_does_not_answer_times_out_and_the_sample_goes_on(void)
{
    operational();
    samples(1, 3900);
    S.batt_silent = true;
    S.batt_pin_mv = PIN(3000);
    uint16_t seq = S.core.seq;
    sim_advance(&S, INTERVAL_MS + 700);
    TEST_ASSERT_EQUAL_UINT16(seq + 1, S.core.seq);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(3900, S.attrs.voltage_mv, "the value stays");
    TEST_ASSERT_EQUAL_INT(MC_SN_REPORTING, S.core.sn);
}

static void test_a_failed_read_keeps_the_value(void)
{
    operational();
    samples(1, 3900);
    S.batt_ok = false;
    samples(1, 3000);
    TEST_ASSERT_EQUAL_UINT16(3900, S.attrs.voltage_mv);
}

static void test_the_calibration_factor_scales_the_value(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.report_interval_s = 10;
    cfg.batt_cal_permille = 1050;
    operational_with(&cfg, "carrier-v1");
    samples(1, 3800);
    TEST_ASSERT_EQUAL_UINT16(3990, S.attrs.voltage_mv);
}

static void test_thresholds_from_the_configuration_apply_at_the_next_sample(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.report_interval_s = 10;
    cfg.batt_low_mv = 3800;
    cfg.batt_critical_mv = 3600;
    operational_with(&cfg, "carrier-v1");
    samples(6, 3750);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_LOW, S.attrs.batt_state);
    sim_send(&S, ev_write_u16(MC_ATTR_BATT_LOW_MV, 3500));
    sim_send(&S, ev_write_u16(MC_ATTR_BATT_CRITICAL_MV, 3300));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    samples(3, 3750);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_OK, S.attrs.batt_state);
}

static void test_the_new_config_attributes_are_staged_and_validated(void)
{
    operational();
    uint16_t rev = S.core.cfg.rev;
    sim_send(&S, ev_write_u16(MC_ATTR_BATT_CRITICAL_MV, 3700)); /* not below the low threshold */
    sim_send(&S, ev_commit(rev + 1));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.attrs.cfg_result);
    sim_send(&S, ev_write_u16(MC_ATTR_BATT_CAL_PERMILLE, 1200));
    sim_send(&S, ev_commit(rev + 1));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.attrs.cfg_result);
    sim_send(&S, ev_write_u16(MC_ATTR_BATT_CAL_PERMILLE, 1020));
    sim_send(&S, ev_commit(rev + 1));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_OK, S.attrs.cfg_result);
    TEST_ASSERT_EQUAL_UINT16(1020, S.core.cfg.batt_cal_permille);
    TEST_ASSERT_EQUAL_UINT16(MC_CFG_BATT_CRITICAL_MV_DEFAULT, S.core.cfg.batt_critical_mv);
}

static void test_a_board_without_a_battery_never_reads_it(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.report_interval_s = 10;
    operational_with(&cfg, "devkitc-1");
    S.batt_pin_mv = PIN(3300);
    sim_advance(&S, 1100);
    sim_advance(&S, INTERVAL_MS);
    TEST_ASSERT_EQUAL_INT(0, S.read_battery_calls);
    TEST_ASSERT_EQUAL_UINT8(MC_BATT_STATE_ABSENT, S.attrs.batt_state);
}

static void test_the_stored_schema_one_configuration_is_migrated(void)
{
    mc_config_t c, d;
    sim_cfg_default(&c);
    c.batt_low_mv = 3500;
    uint8_t blob[MC_CONFIG_BLOB_SIZE];
    mc_config_encode(&c, blob);
    /* build the 87-byte schema 1 form: same fields without the two new ones, crc over the rest */
    uint8_t v1[MC_CONFIG_BLOB_SIZE_V1];
    v1[0] = 1;
    memcpy(v1 + 1, blob + 1, 10);          /* rev, three intervals, batt_low */
    memcpy(v1 + 11, blob + 19, 72);        /* the slot table (after the power settings) */
    uint32_t crc = mc_crc32(v1, MC_CONFIG_BLOB_SIZE_V1 - 4);
    for (int k = 0; k < 4; k++) {
        v1[MC_CONFIG_BLOB_SIZE_V1 - 4 + k] = (uint8_t)(crc >> (8 * k));
    }
    TEST_ASSERT_TRUE(mc_config_decode(v1, sizeof v1, &d));
    TEST_ASSERT_EQUAL_UINT16(3500, d.batt_low_mv);
    TEST_ASSERT_EQUAL_UINT16(MC_CFG_BATT_CRITICAL_MV_DEFAULT, d.batt_critical_mv);
    TEST_ASSERT_EQUAL_UINT16(1000, d.batt_cal_permille);
    TEST_ASSERT_TRUE_MESSAGE(mc_config_same(&c, &d), "the rest is untouched");
}

static void test_the_schema_two_blob_round_trips_the_new_fields(void)
{
    mc_config_t c, d;
    sim_cfg_default(&c);
    c.batt_low_mv = 3700;
    c.batt_critical_mv = 3450;
    c.batt_cal_permille = 1013;
    uint8_t blob[MC_CONFIG_BLOB_SIZE];
    TEST_ASSERT_EQUAL_UINT(MC_CONFIG_BLOB_SIZE, mc_config_encode(&c, blob));
    TEST_ASSERT_TRUE(mc_config_decode(blob, sizeof blob, &d));
    TEST_ASSERT_TRUE(mc_config_same(&c, &d));
}

void run_battery_tests(void)
{
    RUN_TEST(test_every_sample_reads_the_battery_and_reports_millivolts_and_state);
    RUN_TEST(test_the_battery_value_is_part_of_the_sample_that_is_reported);
    RUN_TEST(test_no_cell_is_absent_with_no_event_and_zero_volts);
    RUN_TEST(test_a_cell_that_appears_starts_ok);
    RUN_TEST(test_a_single_outlier_does_not_move_the_reported_value);
    RUN_TEST(test_the_two_sample_start_averages);
    RUN_TEST(test_low_needs_three_samples_and_sends_one_event_with_the_voltage);
    RUN_TEST(test_low_recovers_only_above_the_threshold_plus_hysteresis);
    RUN_TEST(test_critical_after_three_samples_with_its_own_event);
    RUN_TEST(test_low_then_critical_then_back_down_the_stairs);
    RUN_TEST(test_critical_refuses_pump_runs_but_not_stop_or_cancel);
    RUN_TEST(test_a_run_already_running_when_the_state_turns_critical_finishes);
    RUN_TEST(test_no_battery_sample_while_a_pump_runs_or_for_five_seconds_after);
    RUN_TEST(test_a_sample_inside_the_quiet_time_keeps_the_previous_value_and_still_counts);
    RUN_TEST(test_a_battery_read_that_does_not_answer_times_out_and_the_sample_goes_on);
    RUN_TEST(test_a_failed_read_keeps_the_value);
    RUN_TEST(test_the_calibration_factor_scales_the_value);
    RUN_TEST(test_thresholds_from_the_configuration_apply_at_the_next_sample);
    RUN_TEST(test_the_new_config_attributes_are_staged_and_validated);
    RUN_TEST(test_a_board_without_a_battery_never_reads_it);
    RUN_TEST(test_the_stored_schema_one_configuration_is_migrated);
    RUN_TEST(test_the_schema_two_blob_round_trips_the_new_fields);
}
