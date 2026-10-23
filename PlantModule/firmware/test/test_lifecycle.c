/* The device lifecycle machine (PlantModule/specs.md 7.3): one test per transition of the table. */
#include "sim.h"
#include "unity.h"

static sim_t S;

static void boot(const sim_boot_opts_t *o)
{
    sim_init(&S, "carrier-v1");
    sim_boot(&S, o);
}

/* A module that joined earlier: stack ready with a network, operational. */
static void operational(void)
{
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    sim_init(&S, "carrier-v1");
    sim_to_operational(&S, &cfg);
}

/* ---- Boot ---- */

static void test_boot_starts_the_stack_and_forces_outputs_off(void)
{
    boot(NULL);
    ASSERT_LC(&S, MC_LC_STACK_STARTING);
    TEST_ASSERT_TRUE(S.zigbee_started);
    TEST_ASSERT_EQUAL_INT(MC_ACT_ALL_OUTPUTS_OFF, S.kinds[1]); /* right after persisting the counters */
    TEST_ASSERT_TRUE(sim_timer_armed(&S, MC_TIMER_ZB_START, 0));
    TEST_ASSERT_TRUE(sim_timer_armed(&S, MC_TIMER_STABLE, 0));
    TEST_ASSERT_EQUAL_INT(1, S.persist_diag_calls);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.diag.reset_count);
}

static void test_invalid_factory_data_is_safe_mode(void)
{
    boot(&(sim_boot_opts_t){.factory_invalid = true});
    ASSERT_LC(&S, MC_LC_SAFE_MODE);
    TEST_ASSERT_EQUAL_UINT8(MC_SAFE_REASON_FACTORY_INVALID, S.core.safe_reason);
    TEST_ASSERT_TRUE_MESSAGE(S.zigbee_started, "it stays on the network if it can");
    TEST_ASSERT_EQUAL_INT(MC_LED_TRIPLE_BLINK, S.led);
}

static void test_unknown_board_is_safe_mode(void)
{
    sim_init(&S, "carrier-v9");
    sim_boot(&S, NULL);
    ASSERT_LC(&S, MC_LC_SAFE_MODE);
    TEST_ASSERT_EQUAL_UINT8(MC_SAFE_REASON_BOARD_UNKNOWN, S.core.safe_reason);
}

static void test_crash_loop_after_three_unexpected_resets(void)
{
    boot(&(sim_boot_opts_t){.reset_reason = MC_BOOT_REASON_PANIC, .crash_count_stored = 1});
    ASSERT_LC(&S, MC_LC_STACK_STARTING); /* the second one */
    TEST_ASSERT_EQUAL_UINT8(2, S.core.diag.crash_count);
    TEST_ASSERT_EQUAL_UINT8(2, S.persisted_diag.crash_count);

    boot(&(sim_boot_opts_t){.reset_reason = MC_BOOT_REASON_WATCHDOG, .crash_count_stored = 2});
    ASSERT_LC(&S, MC_LC_SAFE_MODE);
    TEST_ASSERT_EQUAL_UINT8(MC_SAFE_REASON_CRASH_LOOP, S.core.safe_reason);

    boot(&(sim_boot_opts_t){.reset_reason = MC_BOOT_REASON_BROWNOUT, .crash_count_stored = 2});
    ASSERT_LC(&S, MC_LC_SAFE_MODE);
}

static void test_other_resets_do_not_make_a_crash_loop(void)
{
    boot(&(sim_boot_opts_t){.reset_reason = MC_BOOT_REASON_SOFTWARE, .crash_count_stored = 2});
    ASSERT_LC(&S, MC_LC_STACK_STARTING); /* a software reset neither counts nor clears */
    TEST_ASSERT_EQUAL_UINT8(2, S.core.diag.crash_count);

    boot(&(sim_boot_opts_t){.reset_reason = MC_BOOT_REASON_POWER_ON, .crash_count_stored = 9});
    ASSERT_LC(&S, MC_LC_STACK_STARTING); /* a power-on reset clears the counter */
    TEST_ASSERT_EQUAL_UINT8(0, S.core.diag.crash_count);
}

static void test_five_minutes_of_stable_uptime_clear_the_crash_counter(void)
{
    boot(&(sim_boot_opts_t){.reset_reason = MC_BOOT_REASON_PANIC, .crash_count_stored = 1});
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, true));
    TEST_ASSERT_EQUAL_UINT8(2, S.core.diag.crash_count);
    sim_advance(&S, 299000);
    TEST_ASSERT_EQUAL_UINT8(2, S.core.diag.crash_count);
    sim_advance(&S, 1500);
    TEST_ASSERT_EQUAL_UINT8(0, S.core.diag.crash_count);
    TEST_ASSERT_EQUAL_UINT8(0, S.persisted_diag.crash_count);
}

static void test_a_corrupt_stored_config_falls_back_to_the_safe_default(void)
{
    boot(&(sim_boot_opts_t){.config_invalid = true});
    ASSERT_LC(&S, MC_LC_STACK_STARTING);
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        TEST_ASSERT_EQUAL_UINT8(MC_MODULE_EMPTY, S.core.cfg.slots[i].module);
    }
    TEST_ASSERT_EQUAL_UINT16(MC_ERR_CONFIG_STORED_INVALID, S.core.diag.last_error);
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, true)); /* the event goes out once the link is there */
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_CONFIG_REJECTED));
}

/* ---- StackStarting ---- */

static void test_stack_ready_with_a_network_is_operational(void)
{
    boot(NULL);
    sim_clear_logs(&S);
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, true));
    ASSERT_LC(&S, MC_LC_OPERATIONAL);
    TEST_ASSERT_EQUAL_INT(MC_LED_SOLID, S.led);
    TEST_ASSERT_FALSE(sim_timer_armed(&S, MC_TIMER_ZB_START, 0));
    TEST_ASSERT_TRUE(sim_timer_armed(&S, MC_TIMER_SAMPLE, 0));
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, sim_count_events(&S, MC_EVENT_CODE_BOOT), "the boot event is sent once the link is up");
    TEST_ASSERT_EQUAL_UINT8(MC_BOOT_REASON_POWER_ON, S.events[0].arg);
    TEST_ASSERT_EQUAL_INT(1, S.reports);
    TEST_ASSERT_EQUAL_UINT8(MC_STATUS_OPERATIONAL, S.attrs.status);
}

static void test_stack_ready_without_a_network(void)
{
    boot(&(sim_boot_opts_t){.first_boot = true});
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, false));
    ASSERT_LC(&S, MC_LC_STEERING); /* the very first boot goes straight to steering */
    TEST_ASSERT_TRUE(S.steering_started);

    boot(NULL);
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, false));
    ASSERT_LC(&S, MC_LC_UNPROVISIONED);
    TEST_ASSERT_FALSE(S.steering_started);
    TEST_ASSERT_EQUAL_INT(MC_LED_SLOW_BLINK, S.led);
}

static void test_a_stack_that_does_not_start_reboots(void)
{
    boot(NULL);
    sim_advance(&S, 9999);
    TEST_ASSERT_EQUAL_INT(0, S.reboots);
    sim_advance(&S, 2);
    TEST_ASSERT_EQUAL_INT(1, S.reboots);
    TEST_ASSERT_EQUAL_UINT16(MC_ERR_ZIGBEE_START, S.persisted_diag.last_error);
}

/* ---- Unprovisioned, Steering, Interviewing ---- */

static void unprovisioned(void)
{
    boot(NULL);
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, false));
    ASSERT_LC(&S, MC_LC_UNPROVISIONED);
    sim_clear_logs(&S);
}

static void test_a_three_second_hold_starts_steering_when_not_on_a_network(void)
{
    unprovisioned();
    sim_send(&S, ev_simple(MC_EV_BTN_HOLD_3S));
    ASSERT_LC(&S, MC_LC_STEERING);
    TEST_ASSERT_TRUE(S.steering_started);
    TEST_ASSERT_EQUAL_INT(MC_LED_FAST_BLINK, S.led);
}

static void test_steering_times_out_after_180_seconds(void)
{
    unprovisioned();
    sim_send(&S, ev_simple(MC_EV_BTN_HOLD_3S));
    sim_advance(&S, 179000);
    ASSERT_LC(&S, MC_LC_STEERING);
    sim_send(&S, ev_bool(MC_EV_ZB_STEERING_DONE, false)); /* a failed scan alone does not end it */
    ASSERT_LC(&S, MC_LC_STEERING);
    sim_advance(&S, 1500);
    ASSERT_LC(&S, MC_LC_UNPROVISIONED);
    TEST_ASSERT_EQUAL_INT(MC_LED_SLOW_BLINK, S.led);
}

static void joined_interviewing(void)
{
    unprovisioned();
    sim_send(&S, ev_simple(MC_EV_BTN_HOLD_3S));
    sim_send(&S, ev_simple(MC_EV_ZB_JOINED));
}

static void test_joining_leads_to_interviewing_with_sensing_and_busy_commands(void)
{
    joined_interviewing();
    ASSERT_LC(&S, MC_LC_INTERVIEWING);
    TEST_ASSERT_FALSE(sim_timer_armed(&S, MC_TIMER_STEERING, 0));
    TEST_ASSERT_TRUE(sim_timer_armed(&S, MC_TIMER_INTERVIEW, 0));
    TEST_ASSERT_TRUE_MESSAGE(sim_timer_armed(&S, MC_TIMER_SAMPLE, 0), "sensing runs while interviewing");
    TEST_ASSERT_EQUAL_UINT8(MC_STATUS_INTERVIEWING, S.attrs.status);
    sim_send(&S, ev_pump_run(1, 2, 5, 60));
    ASSERT_ACK(&S, 1, MC_ACK_STATE_REJECTED, MC_REASON_BUSY);
}

static void test_configured_ends_the_interview(void)
{
    joined_interviewing();
    sim_send(&S, ev_simple(MC_EV_ZB_CONFIGURED));
    ASSERT_LC(&S, MC_LC_OPERATIONAL);
    TEST_ASSERT_FALSE(sim_timer_armed(&S, MC_TIMER_INTERVIEW, 0));
    TEST_ASSERT_EQUAL_INT(MC_LED_SOLID, S.led);
}

static void test_the_interview_ends_after_120_seconds_anyway(void)
{
    joined_interviewing();
    sim_advance(&S, 119000);
    ASSERT_LC(&S, MC_LC_INTERVIEWING);
    sim_advance(&S, 1500);
    ASSERT_LC(&S, MC_LC_OPERATIONAL);
}

/* ---- Operational, Rejoining ---- */

static void test_parent_lost_rejoins_with_backoff_capped_at_five_minutes(void)
{
    operational();
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    ASSERT_LC(&S, MC_LC_REJOINING);
    TEST_ASSERT_EQUAL_INT(MC_LED_DOUBLE_BLINK, S.led);
    TEST_ASSERT_EQUAL_INT(1, S.rejoin_calls);
    const uint32_t gaps[] = {5000, 10000, 20000, 40000, 80000, 160000, 300000, 300000, 300000};
    int calls = 1;
    uint32_t last_attempt = S.now;
    for (size_t i = 0; i < sizeof gaps / sizeof gaps[0]; i++) {
        sim_advance(&S, last_attempt + gaps[i] - 1 - S.now);
        TEST_ASSERT_EQUAL_INT_MESSAGE(calls, S.rejoin_calls, "no attempt before its time");
        sim_advance(&S, 1);
        calls++;
        last_attempt = S.now;
        TEST_ASSERT_EQUAL_INT_MESSAGE(calls, S.rejoin_calls, "attempt on time");
        sim_send(&S, ev_bool(MC_EV_ZB_REJOIN_DONE, false)); /* a failed attempt changes nothing */
        ASSERT_LC(&S, MC_LC_REJOINING);
    }
}

static void test_rejoin_done_returns_to_operational_and_counts(void)
{
    operational();
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    sim_advance(&S, 6000);
    sim_send(&S, ev_bool(MC_EV_ZB_REJOIN_DONE, true));
    ASSERT_LC(&S, MC_LC_OPERATIONAL);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.diag.rejoin_count);
    TEST_ASSERT_EQUAL_UINT16(1, S.persisted_diag.rejoin_count);
    TEST_ASSERT_FALSE(sim_timer_armed(&S, MC_TIMER_REJOIN, 0));
    TEST_ASSERT_EQUAL_INT(MC_LED_SOLID, S.led);
    int before = S.rejoin_calls;
    sim_advance(&S, 400000);
    TEST_ASSERT_EQUAL_INT(before, S.rejoin_calls);
}

static void test_sampling_and_a_pump_run_continue_while_the_radio_is_down(void)
{
    operational();
    sim_send(&S, ev_pump_run(10, 2, 30, 900));
    TEST_ASSERT_TRUE(S.pump_on[2]);
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    ASSERT_LC(&S, MC_LC_REJOINING);
    TEST_ASSERT_TRUE_MESSAGE(S.pump_on[2], "the run is not stopped by the link loss");
    sim_advance(&S, 31000);
    TEST_ASSERT_FALSE_MESSAGE(S.pump_on[2], "it finishes as planned");
    TEST_ASSERT_TRUE_MESSAGE(S.core.seq >= 1, "sensing continues");
    TEST_ASSERT_EQUAL_INT(0, S.acks_sent_while_down);
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, sim_count_acks(&S, 10), "only the running ack went out, the result waits");

    sim_send(&S, ev_bool(MC_EV_ZB_REJOIN_DONE, true));
    TEST_ASSERT_EQUAL_INT(2, sim_count_acks(&S, 10));
    ASSERT_ACK(&S, 10, MC_ACK_STATE_DONE, MC_REASON_NONE);
    TEST_ASSERT_EQUAL_INT(0, S.acks_sent_while_down);
}

static void test_pending_messages_are_kept_in_order_up_to_eight(void)
{
    operational();
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    for (uint32_t i = 1; i <= 10; i++) {
        sim_send(&S, ev_action(100 + i, MC_DEVICE_ACTION_IDENTIFY));
    }
    TEST_ASSERT_EQUAL_INT(0, S.n_acks);
    sim_send(&S, ev_bool(MC_EV_ZB_REJOIN_DONE, true));
    TEST_ASSERT_EQUAL_INT_MESSAGE(8, S.n_acks, "the queue holds eight");
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(103, S.acks[0].cmd_id, "the oldest were dropped");
    for (int i = 1; i < 8; i++) {
        TEST_ASSERT_TRUE_MESSAGE(S.acks[i].n > S.acks[i - 1].n, "in order");
    }
}

static void test_told_to_leave_erases_the_configuration_and_returns_to_unprovisioned(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 30, 900));
    sim_send(&S, ev_simple(MC_EV_ZB_LEFT));
    ASSERT_LC(&S, MC_LC_UNPROVISIONED);
    TEST_ASSERT_TRUE(S.erased);
    TEST_ASSERT_FALSE(S.pump_on[2]);
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        TEST_ASSERT_EQUAL_UINT8(MC_MODULE_EMPTY, S.core.cfg.slots[i].module);
    }
    TEST_ASSERT_EQUAL_UINT16(0, S.core.cfg.rev);
    TEST_ASSERT_EQUAL_INT(MC_LED_SLOW_BLINK, S.led);
    TEST_ASSERT_FALSE_MESSAGE(sim_timer_armed(&S, MC_TIMER_SAMPLE, 0), "no sensing reports when not on a network");
}

static void test_a_ten_second_hold_is_a_factory_reset_in_every_joined_state(void)
{
    operational();
    sim_send(&S, ev_simple(MC_EV_BTN_HOLD_3S));
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_LED_FAST_BLINK, S.led, "the keep-holding cue");
    ASSERT_LC(&S, MC_LC_OPERATIONAL);
    TEST_ASSERT_FALSE_MESSAGE(S.steering_started, "a 3 s hold on a network only gives the cue");
    sim_send(&S, ev_pump_run(1, 2, 30, 900));
    sim_send(&S, ev_simple(MC_EV_BTN_HOLD_10S));
    ASSERT_LC(&S, MC_LC_FACTORY_RESET);
    TEST_ASSERT_TRUE(S.left);
    TEST_ASSERT_TRUE(S.erased);
    TEST_ASSERT_EQUAL_INT(1, S.reboots);
    TEST_ASSERT_FALSE(S.pump_on[2]);

    operational();
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    sim_send(&S, ev_simple(MC_EV_BTN_HOLD_10S));
    ASSERT_LC(&S, MC_LC_FACTORY_RESET);

    unprovisioned();
    sim_send(&S, ev_simple(MC_EV_BTN_HOLD_10S));
    ASSERT_LC(&S, MC_LC_FACTORY_RESET);
}

static void test_releasing_the_button_ends_the_cue(void)
{
    operational();
    sim_send(&S, ev_simple(MC_EV_BTN_HOLD_3S));
    TEST_ASSERT_EQUAL_INT(MC_LED_FAST_BLINK, S.led);
    sim_send(&S, ev_simple(MC_EV_BTN_RELEASE));
    TEST_ASSERT_EQUAL_INT(MC_LED_SOLID, S.led);
}

static void test_a_short_press_identifies_for_ten_seconds_and_reports(void)
{
    operational();
    sim_send(&S, ev_simple(MC_EV_BTN_SHORT));
    TEST_ASSERT_EQUAL_INT(MC_LED_IDENTIFY, S.led);
    TEST_ASSERT_EQUAL_INT(1, S.reports);
    sim_advance(&S, 9900);
    TEST_ASSERT_EQUAL_INT(MC_LED_IDENTIFY, S.led);
    sim_advance(&S, 200);
    TEST_ASSERT_EQUAL_INT(MC_LED_SOLID, S.led);
}

/* ---- Safe mode ---- */

static void test_a_crash_loop_event_stops_everything(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 30, 900));
    sim_send(&S, ev_simple(MC_EV_CRASH_LOOP));
    ASSERT_LC(&S, MC_LC_SAFE_MODE);
    TEST_ASSERT_FALSE(S.pump_on[2]);
    TEST_ASSERT_EQUAL_UINT8(MC_STATUS_SAFE_MODE, S.attrs.status);
    TEST_ASSERT_EQUAL_UINT8(MC_SAFE_REASON_CRASH_LOOP, S.attrs.safe_reason);
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_SAFE_MODE));
    TEST_ASSERT_FALSE_MESSAGE(sim_timer_armed(&S, MC_TIMER_SAMPLE, 0), "no sensing in safe mode");
}

static void safe_mode(void)
{
    boot(&(sim_boot_opts_t){.factory_invalid = true});
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, true));
    sim_clear_logs(&S);
}

static void test_safe_mode_reports_and_refuses_pump_commands_and_configuration(void)
{
    safe_mode();
    ASSERT_LC(&S, MC_LC_SAFE_MODE);
    sim_send(&S, ev_pump_run(1, 2, 5, 60));
    ASSERT_ACK(&S, 1, MC_ACK_STATE_REJECTED, MC_REASON_BUSY);
    TEST_ASSERT_FALSE(S.pump_on[2]);
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 60));
    sim_send(&S, ev_commit(5));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.core.cfg_result);
    TEST_ASSERT_EQUAL_UINT16(0x04FF, S.core.cfg_error); /* busy */
    TEST_ASSERT_EQUAL_UINT16(0, S.core.cfg.rev);
}

static void test_safe_mode_delivers_its_event_when_the_link_is_up(void)
{
    boot(&(sim_boot_opts_t){.factory_invalid = true});
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, true));
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_SAFE_MODE));
    TEST_ASSERT_EQUAL_UINT8(MC_SAFE_REASON_FACTORY_INVALID, S.events[sim_count_events(&S, MC_EVENT_CODE_BOOT)].arg);
    TEST_ASSERT_EQUAL_UINT8(MC_STATUS_SAFE_MODE, S.attrs.status);
}

static void test_clear_safe_mode_reboots_with_a_cleared_crash_counter(void)
{
    boot(&(sim_boot_opts_t){.reset_reason = MC_BOOT_REASON_PANIC, .crash_count_stored = 2});
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, true));
    ASSERT_LC(&S, MC_LC_SAFE_MODE);
    sim_send(&S, ev_action(5, MC_DEVICE_ACTION_CLEAR_SAFE_MODE));
    ASSERT_ACK(&S, 5, MC_ACK_STATE_DONE, MC_REASON_NONE);
    TEST_ASSERT_EQUAL_INT(1, S.reboots);
    TEST_ASSERT_EQUAL_UINT8(0, S.persisted_diag.crash_count);
    boot(&(sim_boot_opts_t){.reset_reason = MC_BOOT_REASON_SOFTWARE, .crash_count_stored = S.persisted_diag.crash_count});
    ASSERT_LC(&S, MC_LC_STACK_STARTING);
}

static void test_clear_safe_mode_outside_safe_mode_does_nothing(void)
{
    operational();
    sim_send(&S, ev_action(5, MC_DEVICE_ACTION_CLEAR_SAFE_MODE));
    ASSERT_ACK(&S, 5, MC_ACK_STATE_DONE, MC_REASON_NONE);
    TEST_ASSERT_EQUAL_INT(0, S.reboots);
}

static void test_a_factory_reset_leaves_safe_mode(void)
{
    safe_mode();
    sim_send(&S, ev_simple(MC_EV_BTN_HOLD_10S));
    ASSERT_LC(&S, MC_LC_FACTORY_RESET);
    TEST_ASSERT_EQUAL_INT(1, S.reboots);
}

static void test_the_status_attribute_follows_the_lifecycle(void)
{
    joined_interviewing();
    TEST_ASSERT_EQUAL_UINT8(MC_STATUS_INTERVIEWING, S.attrs.status);
    sim_send(&S, ev_simple(MC_EV_ZB_CONFIGURED));
    TEST_ASSERT_EQUAL_UINT8(MC_STATUS_OPERATIONAL, S.attrs.status);
}

void run_lifecycle_tests(void)
{
    RUN_TEST(test_boot_starts_the_stack_and_forces_outputs_off);
    RUN_TEST(test_invalid_factory_data_is_safe_mode);
    RUN_TEST(test_unknown_board_is_safe_mode);
    RUN_TEST(test_crash_loop_after_three_unexpected_resets);
    RUN_TEST(test_other_resets_do_not_make_a_crash_loop);
    RUN_TEST(test_five_minutes_of_stable_uptime_clear_the_crash_counter);
    RUN_TEST(test_a_corrupt_stored_config_falls_back_to_the_safe_default);
    RUN_TEST(test_stack_ready_with_a_network_is_operational);
    RUN_TEST(test_stack_ready_without_a_network);
    RUN_TEST(test_a_stack_that_does_not_start_reboots);
    RUN_TEST(test_a_three_second_hold_starts_steering_when_not_on_a_network);
    RUN_TEST(test_steering_times_out_after_180_seconds);
    RUN_TEST(test_joining_leads_to_interviewing_with_sensing_and_busy_commands);
    RUN_TEST(test_configured_ends_the_interview);
    RUN_TEST(test_the_interview_ends_after_120_seconds_anyway);
    RUN_TEST(test_parent_lost_rejoins_with_backoff_capped_at_five_minutes);
    RUN_TEST(test_rejoin_done_returns_to_operational_and_counts);
    RUN_TEST(test_sampling_and_a_pump_run_continue_while_the_radio_is_down);
    RUN_TEST(test_pending_messages_are_kept_in_order_up_to_eight);
    RUN_TEST(test_told_to_leave_erases_the_configuration_and_returns_to_unprovisioned);
    RUN_TEST(test_a_ten_second_hold_is_a_factory_reset_in_every_joined_state);
    RUN_TEST(test_releasing_the_button_ends_the_cue);
    RUN_TEST(test_a_short_press_identifies_for_ten_seconds_and_reports);
    RUN_TEST(test_a_crash_loop_event_stops_everything);
    RUN_TEST(test_safe_mode_reports_and_refuses_pump_commands_and_configuration);
    RUN_TEST(test_safe_mode_delivers_its_event_when_the_link_is_up);
    RUN_TEST(test_clear_safe_mode_reboots_with_a_cleared_crash_counter);
    RUN_TEST(test_clear_safe_mode_outside_safe_mode_does_nothing);
    RUN_TEST(test_a_factory_reset_leaves_safe_mode);
    RUN_TEST(test_the_status_attribute_follows_the_lifecycle);
}
