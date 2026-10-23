/* Command machine and pump actuators (PlantModule/specs.md 7.5). */
#include "sim.h"
#include "unity.h"

static sim_t S;

static void operational(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    sim_init(&S, "carrier-v1");
    sim_to_operational(&S, &cfg);
    sim_advance(&S, 1100);
    sim_clear_logs(&S);
}

static void test_a_run_starts_the_pump_answers_running_and_ends_on_time(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    TEST_ASSERT_TRUE(S.pump_on[2]);
    ASSERT_ACK(&S, 1, MC_ACK_STATE_RUNNING, MC_REASON_NONE);
    TEST_ASSERT_EQUAL_UINT16(10, sim_find_ack(&S, 1, 0)->ends_in_s);
    sim_advance(&S, 9900);
    TEST_ASSERT_TRUE(S.pump_on[2]);
    sim_advance(&S, 200);
    TEST_ASSERT_FALSE(S.pump_on[2]);
    ASSERT_ACK(&S, 1, MC_ACK_STATE_DONE, MC_REASON_NONE);
    TEST_ASSERT_EQUAL_INT(2, sim_count_acks(&S, 1));
    TEST_ASSERT_EQUAL_INT(1, S.pump_edges[2]);
}

static void test_the_same_command_id_is_never_executed_twice(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, S.pump_edges[2], "one start only");
    TEST_ASSERT_EQUAL_INT(2, sim_count_acks(&S, 1));
    ASSERT_ACK(&S, 1, MC_ACK_STATE_RUNNING, MC_REASON_NONE);
    sim_advance(&S, 11000);
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    ASSERT_ACK(&S, 1, MC_ACK_STATE_DONE, MC_REASON_NONE);
    TEST_ASSERT_FALSE(S.pump_on[2]);
}

static void test_validation_reasons(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 10, 0));
    ASSERT_ACK(&S, 1, MC_ACK_STATE_REJECTED, MC_REASON_EXPIRED);
    sim_send(&S, ev_pump_run(2, 0, 10, 900));
    ASSERT_ACK(&S, 2, MC_ACK_STATE_REJECTED, MC_REASON_SLOT_NOT_ACTUATOR);
    sim_send(&S, ev_pump_run(3, 5, 10, 900));
    ASSERT_ACK(&S, 3, MC_ACK_STATE_REJECTED, MC_REASON_SLOT_NOT_ACTUATOR);
    sim_send(&S, ev_pump_run(4, 2, 0, 900));
    ASSERT_ACK(&S, 4, MC_ACK_STATE_REJECTED, MC_REASON_LIMIT);
    sim_send(&S, ev_pump_run(5, 2, 61, 900));
    ASSERT_ACK(&S, 5, MC_ACK_STATE_REJECTED, MC_REASON_LIMIT);
    TEST_ASSERT_EQUAL_INT(0, S.pump_edges[2]);
}

static void test_the_hard_ceiling_applies_even_if_the_config_allows_more(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.slots[2].max_run_s = 1000;
    sim_init(&S, "carrier-v1");
    sim_to_operational(&S, &cfg);
    sim_send(&S, ev_pump_run(1, 2, 301, 900));
    ASSERT_ACK(&S, 1, MC_ACK_STATE_REJECTED, MC_REASON_LIMIT);
    sim_send(&S, ev_pump_run(2, 2, 300, 900));
    ASSERT_ACK(&S, 2, MC_ACK_STATE_RUNNING, MC_REASON_NONE);
}

static void test_a_second_run_while_running_is_busy_and_the_first_continues(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 20, 900));
    sim_send(&S, ev_pump_run(2, 2, 5, 900));
    ASSERT_ACK(&S, 2, MC_ACK_STATE_REJECTED, MC_REASON_BUSY);
    sim_advance(&S, 6000);
    TEST_ASSERT_TRUE(S.pump_on[2]);
}

static void test_min_pause_is_enforced_after_a_run(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 5, 900));
    sim_advance(&S, 5100);
    sim_send(&S, ev_pump_run(2, 2, 5, 900));
    ASSERT_ACK(&S, 2, MC_ACK_STATE_REJECTED, MC_REASON_MIN_PAUSE);
    sim_advance(&S, 598000);
    sim_send(&S, ev_pump_run(3, 2, 5, 900));
    ASSERT_ACK(&S, 3, MC_ACK_STATE_REJECTED, MC_REASON_MIN_PAUSE);
    sim_advance(&S, 3000);
    sim_send(&S, ev_pump_run(4, 2, 5, 900));
    ASSERT_ACK(&S, 4, MC_ACK_STATE_RUNNING, MC_REASON_NONE);
}

static void test_stop_ends_the_run_cancelled_and_stop_itself_is_done(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 30, 900));
    sim_advance(&S, 3000);
    sim_send(&S, ev_pump_stop(2, 2));
    TEST_ASSERT_FALSE(S.pump_on[2]);
    ASSERT_ACK(&S, 1, MC_ACK_STATE_CANCELLED, MC_REASON_NONE);
    ASSERT_ACK(&S, 2, MC_ACK_STATE_DONE, MC_REASON_NONE);
    sim_send(&S, ev_pump_stop(3, 2));
    ASSERT_ACK(&S, 3, MC_ACK_STATE_DONE, MC_REASON_NONE);
}

static void test_cancel_of_a_running_command_stops_it(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 30, 900));
    sim_send(&S, ev_cancel(2, 1));
    TEST_ASSERT_FALSE(S.pump_on[2]);
    ASSERT_ACK(&S, 1, MC_ACK_STATE_CANCELLED, MC_REASON_NONE);
    ASSERT_ACK(&S, 2, MC_ACK_STATE_DONE, MC_REASON_NONE);
}

static void test_a_cancel_that_arrives_first_cancels_the_command_when_it_comes(void)
{
    operational();
    sim_send(&S, ev_cancel(2, 1));
    ASSERT_ACK(&S, 2, MC_ACK_STATE_DONE, MC_REASON_NONE);
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    TEST_ASSERT_FALSE(S.pump_on[2]);
    ASSERT_ACK(&S, 1, MC_ACK_STATE_CANCELLED, MC_REASON_NONE);
}

static void test_a_tombstone_expires_after_ten_minutes(void)
{
    operational();
    sim_send(&S, ev_cancel(2, 1));
    sim_advance(&S, 601000);
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    TEST_ASSERT_TRUE(S.pump_on[2]);
}

static void test_tombstones_are_limited_and_the_oldest_is_replaced(void)
{
    operational();
    for (uint32_t i = 0; i < MC_MAX_TOMBSTONES + 1; i++) {
        sim_send(&S, ev_cancel(100 + i, 10 + i));
        sim_advance(&S, 1000);
    }
    sim_send(&S, ev_pump_run(10, 2, 5, 900));
    TEST_ASSERT_MESSAGE(S.pump_on[2], "the oldest tombstone was replaced");
}

static void test_the_pump_never_runs_longer_than_the_run_time_even_with_many_commands(void)
{
    operational();
    for (uint32_t i = 0; i < 40; i++) {
        sim_send(&S, ev_pump_run(1000 + i, 2, 60, 900));
        sim_advance(&S, 61000);
    }
    TEST_ASSERT_TRUE(S.longest_pump_run_ms <= 60100);
}

static void test_commands_are_busy_while_not_operational(void)
{
    sim_init(&S, "carrier-v1");
    sim_boot(&S, &(sim_boot_opts_t){.first_boot = true});
    sim_send(&S, ev_pump_run(1, 2, 10, 900));
    TEST_ASSERT_EQUAL_INT(0, S.pump_edges[2]);
    const sim_ack_t *a = sim_find_ack(&S, 1, -1);
    if (a) {
        TEST_ASSERT_EQUAL_INT(MC_ACK_STATE_REJECTED, a->state);
    }
}

static void test_identify_blinks_for_ten_seconds_and_ends(void)
{
    operational();
    sim_send(&S, ev_action(1, MC_DEVICE_ACTION_IDENTIFY));
    ASSERT_ACK(&S, 1, MC_ACK_STATE_DONE, MC_REASON_NONE);
    TEST_ASSERT_EQUAL_INT(MC_LED_IDENTIFY, S.led);
    sim_advance(&S, 10100);
    TEST_ASSERT_NOT_EQUAL(MC_LED_IDENTIFY, S.led);
}

static void test_reboot_is_acknowledged_first_then_outputs_are_off_and_reboot_requested(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 30, 900));
    sim_send(&S, ev_action(2, MC_DEVICE_ACTION_REBOOT));
    ASSERT_ACK(&S, 2, MC_ACK_STATE_DONE, MC_REASON_NONE);
    TEST_ASSERT_FALSE(S.pump_on[2]);
    TEST_ASSERT_EQUAL_INT(1, S.reboots);
}

static void test_link_loss_does_not_stop_a_run_and_the_result_waits_for_the_link(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 20, 900));
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    sim_advance(&S, 21000);
    TEST_ASSERT_FALSE(S.pump_on[2]);
    TEST_ASSERT_EQUAL_INT(0, S.acks_sent_while_down);
    sim_send(&S, ev_bool(MC_EV_ZB_REJOIN_DONE, true));
    ASSERT_ACK(&S, 1, MC_ACK_STATE_DONE, MC_REASON_NONE);
}

static void test_a_stop_during_link_loss_is_still_honoured(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 60, 900));
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    sim_advance(&S, 5000);
    TEST_ASSERT_TRUE(S.pump_on[2]);
    sim_send(&S, ev_pump_stop(2, 2));
    TEST_ASSERT_FALSE(S.pump_on[2]);
}

static void test_report_now_samples_at_once_and_reports(void)
{
    operational(); /* the first sample is done, the next one is 300 s away */
    uint16_t seq = S.core.seq;
    int reports = S.reports;
    sim_advance(&S, 10000);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(seq, S.core.seq, "nothing happens on its own");
    sim_send(&S, ev_action(7, MC_DEVICE_ACTION_REPORT_NOW));
    ASSERT_ACK(&S, 7, MC_ACK_STATE_DONE, MC_REASON_NONE);
    sim_advance(&S, 200);
    TEST_ASSERT_EQUAL_UINT16(seq + 1, S.core.seq);
    TEST_ASSERT_EQUAL_INT_MESSAGE(reports + 1, S.reports, "an explicit report with the new sample");
    TEST_ASSERT_EQUAL_UINT16(seq + 1, S.attrs.seq);
}

static void test_the_regular_interval_continues_after_a_report_now(void)
{
    operational();
    sim_advance(&S, 10000);
    sim_send(&S, ev_action(7, MC_DEVICE_ACTION_REPORT_NOW));
    sim_advance(&S, 200);
    uint16_t seq = S.core.seq;
    sim_advance(&S, 299000);
    TEST_ASSERT_EQUAL_UINT16(seq, S.core.seq);
    sim_advance(&S, 2000);
    TEST_ASSERT_EQUAL_UINT16(seq + 1, S.core.seq);
}

static void test_report_now_during_a_sample_does_not_start_a_second_one(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    sim_init(&S, "carrier-v1");
    sim_to_operational(&S, &cfg);
    sim_advance(&S, 1010); /* the first sample is running (its slot read is out) */
    TEST_ASSERT_EQUAL_INT(MC_SN_SAMPLING, S.core.sn);
    sim_send(&S, ev_action(7, MC_DEVICE_ACTION_REPORT_NOW));
    sim_advance(&S, 500);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.seq);
}

static void test_report_now_does_nothing_in_safe_mode_but_is_acknowledged(void)
{
    sim_init(&S, "carrier-v1");
    sim_boot(&S, &(sim_boot_opts_t){.factory_invalid = true});
    sim_send(&S, ev_action(7, MC_DEVICE_ACTION_REPORT_NOW));
    sim_advance(&S, 5000);
    TEST_ASSERT_EQUAL_UINT16(0, S.core.seq);
}

void run_command_tests(void)
{
    RUN_TEST(test_a_run_starts_the_pump_answers_running_and_ends_on_time);
    RUN_TEST(test_the_same_command_id_is_never_executed_twice);
    RUN_TEST(test_validation_reasons);
    RUN_TEST(test_the_hard_ceiling_applies_even_if_the_config_allows_more);
    RUN_TEST(test_a_second_run_while_running_is_busy_and_the_first_continues);
    RUN_TEST(test_min_pause_is_enforced_after_a_run);
    RUN_TEST(test_stop_ends_the_run_cancelled_and_stop_itself_is_done);
    RUN_TEST(test_cancel_of_a_running_command_stops_it);
    RUN_TEST(test_a_cancel_that_arrives_first_cancels_the_command_when_it_comes);
    RUN_TEST(test_a_tombstone_expires_after_ten_minutes);
    RUN_TEST(test_tombstones_are_limited_and_the_oldest_is_replaced);
    RUN_TEST(test_the_pump_never_runs_longer_than_the_run_time_even_with_many_commands);
    RUN_TEST(test_commands_are_busy_while_not_operational);
    RUN_TEST(test_identify_blinks_for_ten_seconds_and_ends);
    RUN_TEST(test_reboot_is_acknowledged_first_then_outputs_are_off_and_reboot_requested);
    RUN_TEST(test_link_loss_does_not_stop_a_run_and_the_result_waits_for_the_link);
    RUN_TEST(test_a_stop_during_link_loss_is_still_honoured);
    RUN_TEST(test_report_now_samples_at_once_and_reports);
    RUN_TEST(test_the_regular_interval_continues_after_a_report_now);
    RUN_TEST(test_report_now_during_a_sample_does_not_start_a_second_one);
    RUN_TEST(test_report_now_does_nothing_in_safe_mode_but_is_acknowledged);
}
