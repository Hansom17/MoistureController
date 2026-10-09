/* Sensing/report machine and fast mode (PlantModule/specs.md 6, 7.4). */
#include "sim.h"
#include "unity.h"

static sim_t S;

/* A sample runs 20 ms after its timer in the sim, so waiting for "the next one" needs a little slack. */
#define NEXT 300100
#define FAST_NEXT 30100

static void operational_with(mc_config_t *cfg, const char *board)
{
    sim_init(&S, board);
    sim_to_operational(&S, cfg);
}

static void operational(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    operational_with(&cfg, "carrier-v1");
}

/* ---- the sample cycle ---- */

static void test_the_first_sample_comes_one_second_after_start_and_reads_the_moisture_slot(void)
{
    operational();
    sim_advance(&S, 999);
    TEST_ASSERT_EQUAL_INT(0, S.read_slot_calls);
    sim_advance(&S, 2);
    TEST_ASSERT_EQUAL_INT(1, S.read_slot_calls);
    TEST_ASSERT_EQUAL_INT(MC_SN_SAMPLING, S.core.sn);
    sim_advance(&S, 30);
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SN_REPORTING, S.core.sn, "every sample is sent");
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_EQUAL_INT(MC_SN_IDLE, S.core.sn);
    TEST_ASSERT_EQUAL_UINT16(1, S.attrs.seq);
    TEST_ASSERT_EQUAL_UINT8(MC_MODULE_MOISTURE, S.attrs.readings[0].type);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OK, S.attrs.readings[0].error);
    TEST_ASSERT_EQUAL_INT16(5000, S.attrs.readings[0].value); /* raw 2100 between 3000 and 1200 */
    TEST_ASSERT_EQUAL_UINT16(2100, S.attrs.readings[0].raw);
    TEST_ASSERT_EQUAL_UINT16(2, S.attrs.readings[0].cfg_rev);
    TEST_ASSERT_EQUAL_UINT8(MC_MODULE_PUMP, S.attrs.readings[2].type);
    TEST_ASSERT_EQUAL_INT16(0, S.attrs.readings[2].value);
    TEST_ASSERT_EQUAL_UINT8(MC_MODULE_EMPTY, S.attrs.readings[1].type);
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, S.reports, "the sample is reported explicitly in normal mode too");
}

static void test_samples_repeat_at_the_report_interval_and_seq_counts(void)
{
    operational();
    sim_advance(&S, 1100);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.seq);
    sim_advance(&S, 299000);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.seq);
    sim_advance(&S, 2000);
    TEST_ASSERT_EQUAL_UINT16(2, S.core.seq);
    sim_advance(&S, NEXT);
    TEST_ASSERT_EQUAL_UINT16(3, S.core.seq);
}

static void test_sensor_errors_are_reported_and_never_become_a_value(void)
{
    operational();
    S.adc_raw[0] = 0;
    sim_advance(&S, 1100);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_NO_SIGNAL, S.attrs.readings[0].error);
    TEST_ASSERT_EQUAL_INT16(MC_VALUE_UNKNOWN, S.attrs.readings[0].value);
    S.adc_raw[0] = 100;
    sim_advance(&S, NEXT);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OUT_OF_RANGE, S.attrs.readings[0].error);
    TEST_ASSERT_EQUAL_INT16(MC_VALUE_UNKNOWN, S.attrs.readings[0].value);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(100, S.attrs.readings[0].raw, "the raw value is always reported");
    S.adc_ok[0] = false;
    sim_advance(&S, NEXT);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_HW_ERROR, S.attrs.readings[0].error);
}

static void test_three_bad_samples_raise_one_sensor_fault_and_a_good_one_clears_it(void)
{
    operational();
    S.adc_ok[0] = false;
    sim_advance(&S, 1100);
    sim_advance(&S, NEXT);
    TEST_ASSERT_EQUAL_INT(0, sim_count_events(&S, MC_EVENT_CODE_SENSOR_FAULT));
    sim_advance(&S, NEXT);
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_SENSOR_FAULT));
    TEST_ASSERT_EQUAL_UINT8(0, S.events[S.n_events - 1].slot);
    sim_advance(&S, NEXT);
    sim_advance(&S, NEXT);
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, sim_count_events(&S, MC_EVENT_CODE_SENSOR_FAULT), "raised once");
    S.adc_ok[0] = true;
    sim_advance(&S, NEXT);
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_SENSOR_OK));
    sim_advance(&S, NEXT);
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_SENSOR_OK));
    TEST_ASSERT_EQUAL_UINT16(MC_ERR_SENSOR_FAULT, S.core.diag.last_error);
}

static void test_two_bad_samples_in_between_good_ones_do_not_raise_a_fault(void)
{
    operational();
    for (int i = 0; i < 6; i++) {
        S.adc_ok[0] = (i % 3) == 2;
        sim_advance(&S, i == 0 ? 1100 : 300000);
    }
    TEST_ASSERT_EQUAL_INT(0, sim_count_events(&S, MC_EVENT_CODE_SENSOR_FAULT));
}

static void test_a_slot_that_does_not_answer_times_out_after_500_ms(void)
{
    operational();
    S.adc_silent[0] = true;
    sim_advance(&S, 1000);
    sim_advance(&S, 499);
    TEST_ASSERT_EQUAL_INT(MC_SN_SAMPLING, S.core.sn);
    sim_advance(&S, 2);
    TEST_ASSERT_EQUAL_INT(MC_SN_REPORTING, S.core.sn);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_HW_ERROR, S.attrs.readings[0].error);
    TEST_ASSERT_EQUAL_UINT16(1, S.attrs.seq);
}

static void test_a_late_answer_after_the_timeout_is_ignored(void)
{
    operational();
    S.adc_silent[0] = true;
    sim_advance(&S, 1600);
    mc_event_t late = {.kind = MC_EV_ADC_DONE};
    late.u.adc.slot = 0;
    late.u.adc.ok = true;
    late.u.adc.raw = 2100;
    sim_send(&S, late);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_HW_ERROR, S.attrs.readings[0].error);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.seq);
}

static void test_a_sample_never_takes_longer_than_two_seconds(void)
{
    mc_config_t cfg;
    mc_config_default(&cfg);
    cfg.rev = 3;
    for (int i = 0; i < 6; i++) {
        cfg.slots[i] = (mc_slot_cfg_t){.module = MC_MODULE_MOISTURE, .port = (uint8_t)i, .cal_dry = 3000, .cal_wet = 1200, .samples = 16};
        S.adc_silent[i] = true;
    }
    sim_init(&S, "devkitc-1");
    for (int i = 0; i < 6; i++) {
        S.adc_silent[i] = true;
    }
    sim_to_operational(&S, &cfg);
    sim_advance(&S, 1000);
    sim_advance(&S, 1999);
    TEST_ASSERT_EQUAL_INT(MC_SN_SAMPLING, S.core.sn);
    sim_advance(&S, 2);
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SN_REPORTING, S.core.sn, "cut off by the 2 s window, then reported");
    TEST_ASSERT_EQUAL_INT_MESSAGE(4, S.read_slot_calls, "four slots were tried, the rest were skipped");
    for (int i = 0; i < 6; i++) {
        TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_HW_ERROR, S.attrs.readings[i].error);
    }
}

static void test_without_sensor_slots_samples_still_count_for_the_pumps_and_diagnostics(void)
{
    mc_config_t cfg;
    mc_config_default(&cfg);
    operational_with(&cfg, "carrier-v1");
    sim_advance(&S, 1100);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.seq);
    TEST_ASSERT_EQUAL_INT(0, S.read_slot_calls);
}

/* ---- fast mode ---- */

static void test_fast_mode_samples_every_30_seconds_with_an_explicit_report(void)
{
    operational();
    sim_advance(&S, 1100);
    S.reports = 0;
    sim_send(&S, ev_pump_run(1, 2, 50, 900));
    TEST_ASSERT_TRUE(S.core.fast);
    TEST_ASSERT_TRUE(S.attrs.fast_mode);
    int base_reports = S.reports; /* the pump start itself reports */
    sim_advance(&S, FAST_NEXT);
    TEST_ASSERT_EQUAL_UINT16(2, S.core.seq);
    TEST_ASSERT_EQUAL_INT_MESSAGE(base_reports + 1, S.reports, "an explicit report after the sample");
    sim_advance(&S, FAST_NEXT);
    TEST_ASSERT_EQUAL_UINT16(3, S.core.seq);
    TEST_ASSERT_EQUAL_INT_MESSAGE(base_reports + 3, S.reports, "two samples and the pump end");
}

static void test_fast_mode_lasts_120_seconds_after_the_last_run_then_normal_again(void)
{
    operational();
    sim_advance(&S, 1100);
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    sim_advance(&S, 10000); /* the run ends */
    TEST_ASSERT_FALSE(S.pump_on[2]);
    TEST_ASSERT_TRUE(S.core.fast);
    sim_advance(&S, 119000);
    TEST_ASSERT_TRUE(S.core.fast);
    sim_advance(&S, 2000);
    TEST_ASSERT_FALSE(S.core.fast);
    TEST_ASSERT_FALSE(S.attrs.fast_mode);
    uint16_t seq = S.core.seq;
    sim_advance(&S, 20000);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(seq + 1, S.core.seq, "the already armed fast sample still happens, then 300 s");
    sim_advance(&S, 290000);
    TEST_ASSERT_EQUAL_UINT16(seq + 1, S.core.seq);
    sim_advance(&S, 12000);
    TEST_ASSERT_EQUAL_UINT16(seq + 2, S.core.seq);
}

static void test_a_zero_hold_time_leaves_fast_mode_at_once(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.fast_report_hold_s = 0;
    operational_with(&cfg, "carrier-v1");
    sim_send(&S, ev_pump_run(1, 2, 5, 900));
    TEST_ASSERT_TRUE(S.core.fast);
    sim_advance(&S, 5000);
    TEST_ASSERT_FALSE(S.core.fast);
}

static void test_fast_mode_holds_while_another_pump_still_runs(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.slots[3] = (mc_slot_cfg_t){.module = MC_MODULE_PUMP, .port = 3, .active_high = true, .max_run_s = 60, .min_pause_s = 0};
    operational_with(&cfg, "carrier-v1");
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    sim_send(&S, ev_pump_run(2, 3, 50, 900));
    sim_advance(&S, 10500);
    TEST_ASSERT_FALSE(S.pump_on[2]);
    TEST_ASSERT_TRUE(S.pump_on[3]);
    TEST_ASSERT_FALSE_MESSAGE(sim_timer_armed(&S, MC_TIMER_FAST_HOLD, 0), "the hold starts when the last run ended");
    sim_advance(&S, 40000);
    TEST_ASSERT_TRUE(sim_timer_armed(&S, MC_TIMER_FAST_HOLD, 0));
}

static void test_a_failed_report_is_not_repeated(void)
{
    operational();
    sim_advance(&S, 1100);
    sim_send(&S, ev_pump_run(1, 2, 50, 900));
    sim_advance(&S, FAST_NEXT);
    TEST_ASSERT_EQUAL_INT(MC_SN_REPORTING, S.core.sn);
    int reports = S.reports;
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, false));
    TEST_ASSERT_EQUAL_INT(MC_SN_IDLE, S.core.sn);
    TEST_ASSERT_EQUAL_INT(reports, S.reports);
}

static void test_reporting_does_not_wait_forever_for_a_result(void)
{
    operational();
    sim_advance(&S, 1100);
    sim_send(&S, ev_pump_run(1, 2, 50, 900));
    sim_advance(&S, FAST_NEXT);
    TEST_ASSERT_EQUAL_INT(MC_SN_REPORTING, S.core.sn);
    sim_advance(&S, 5100);
    TEST_ASSERT_EQUAL_INT(MC_SN_IDLE, S.core.sn);
}

static void test_no_explicit_report_while_the_link_is_down(void)
{
    operational();
    sim_advance(&S, 1100);
    sim_send(&S, ev_pump_run(1, 2, 50, 900));
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    int reports = S.reports;
    sim_advance(&S, 62000);
    TEST_ASSERT_EQUAL_INT(reports, S.reports);
    TEST_ASSERT_TRUE(S.core.seq >= 3);
}

static void test_the_pump_reading_shows_the_output_at_once_and_after_the_run(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 20, 900));
    TEST_ASSERT_EQUAL_UINT8(MC_MODULE_PUMP, S.attrs.readings[2].type);
    TEST_ASSERT_EQUAL_INT16_MESSAGE(10000, S.attrs.readings[2].value, "on right when it starts");
    sim_advance(&S, 21000);
    TEST_ASSERT_EQUAL_INT16_MESSAGE(0, S.attrs.readings[2].value, "off right when it ends");
}

/* ---- battery ---- */

static void test_low_battery_event_once_with_hysteresis(void)
{
    operational();
    sim_send(&S, ev_battery(0)); /* externally powered: the divider reads nothing */
    TEST_ASSERT_EQUAL_INT(0, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY));
    sim_send(&S, ev_battery(3900));
    TEST_ASSERT_EQUAL_INT(0, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY));
    sim_send(&S, ev_battery(3400));
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY));
    sim_send(&S, ev_battery(3300));
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY));
    sim_send(&S, ev_battery(3550)); /* above the threshold but not by 100 mV */
    sim_send(&S, ev_battery(3300));
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY));
    sim_send(&S, ev_battery(3700));
    sim_send(&S, ev_battery(3300));
    TEST_ASSERT_EQUAL_INT(2, sim_count_events(&S, MC_EVENT_CODE_LOW_BATTERY));
    TEST_ASSERT_EQUAL_UINT16(3300, S.core.voltage_mv);
}

void run_sensing_tests(void)
{
    RUN_TEST(test_the_first_sample_comes_one_second_after_start_and_reads_the_moisture_slot);
    RUN_TEST(test_samples_repeat_at_the_report_interval_and_seq_counts);
    RUN_TEST(test_sensor_errors_are_reported_and_never_become_a_value);
    RUN_TEST(test_three_bad_samples_raise_one_sensor_fault_and_a_good_one_clears_it);
    RUN_TEST(test_two_bad_samples_in_between_good_ones_do_not_raise_a_fault);
    RUN_TEST(test_a_slot_that_does_not_answer_times_out_after_500_ms);
    RUN_TEST(test_a_late_answer_after_the_timeout_is_ignored);
    RUN_TEST(test_a_sample_never_takes_longer_than_two_seconds);
    RUN_TEST(test_without_sensor_slots_samples_still_count_for_the_pumps_and_diagnostics);
    RUN_TEST(test_fast_mode_samples_every_30_seconds_with_an_explicit_report);
    RUN_TEST(test_fast_mode_lasts_120_seconds_after_the_last_run_then_normal_again);
    RUN_TEST(test_a_zero_hold_time_leaves_fast_mode_at_once);
    RUN_TEST(test_fast_mode_holds_while_another_pump_still_runs);
    RUN_TEST(test_a_failed_report_is_not_repeated);
    RUN_TEST(test_reporting_does_not_wait_forever_for_a_result);
    RUN_TEST(test_no_explicit_report_while_the_link_is_down);
    RUN_TEST(test_the_pump_reading_shows_the_output_at_once_and_after_the_run);
    RUN_TEST(test_low_battery_event_once_with_hysteresis);
}
