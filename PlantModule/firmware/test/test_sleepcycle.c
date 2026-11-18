/* The deep-sleep cycle and the power-mode changes (PlantModule/specs.md 18.4): wake, sample at once, report, the awake
 * window, the sleep time that keeps the wake-ups report_interval_s apart. */
#include "sim.h"
#include "unity.h"

static sim_t S;

#define INTERVAL_S 300
#define AWAKE_S 5

static mc_board_t sleepy(void)
{
    mc_board_t b = *mc_board_find("carrier-v1");
    b.name = "test-sleepy";
    b.power_modes = (1u << MC_POWER_MODE_LIGHT_SLEEP) | (1u << MC_POWER_MODE_DEEP_SLEEP);
    return b;
}

static mc_config_t deep_cfg(void)
{
    mc_config_t c;
    sim_cfg_default(&c);
    c.power_mode = MC_POWER_MODE_DEEP_SLEEP;
    c.report_interval_s = INTERVAL_S;
    c.awake_s = AWAKE_S;
    return c;
}

/* a wake from deep sleep: the module boots, restores the network, is operational */
static void deep_wake(const mc_board_t *b, uint16_t seq, uint16_t wakes)
{
    mc_config_t cfg = deep_cfg();
    sim_init_board(&S, b);
    sim_boot_opts_t o = {.config = &cfg, .reset_reason = MC_BOOT_REASON_DEEP_SLEEP_WAKE, .deep_sleep_wake = true,
                         .rtc_seq = seq, .rtc_wake_count = wakes, .rtc_sleep_total_s = 3000, .rtc_last_awake_ms = 3900,
                         .wake_reason = MC_WAKE_REASON_TIMER, .boot_id = 41};
    sim_boot(&S, &o);
    sim_send(&S, ev_bool(MC_EV_ZB_STACK_READY, true));
    TEST_ASSERT_EQUAL_INT(MC_LC_OPERATIONAL, S.core.lc);
}

static void test_a_deep_sleep_wake_is_not_a_restart(void)
{
    mc_board_t b = sleepy();
    sim_init_board(&S, &b);
    mc_config_t cfg = deep_cfg();
    sim_boot_opts_t o = {.config = &cfg, .reset_reason = MC_BOOT_REASON_DEEP_SLEEP_WAKE, .deep_sleep_wake = true,
                         .rtc_seq = 77, .rtc_wake_count = 12, .rtc_sleep_total_s = 3600, .rtc_last_awake_ms = 3900,
                         .wake_reason = MC_WAKE_REASON_TIMER, .boot_id = 41};
    sim_boot(&S, &o);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0, S.core.diag.reset_count, "no restart counted");
    TEST_ASSERT_EQUAL_INT_MESSAGE(0, S.persist_diag_calls, "nothing worth a flash write");
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0, S.core.event_n, "no boot event every cycle");
    TEST_ASSERT_EQUAL_UINT16(77, S.core.seq);
    TEST_ASSERT_EQUAL_UINT16(41, S.core.boot_id);
    TEST_ASSERT_FALSE_MESSAGE(S.core.grace_active, "the grace window is for normal boots only");
    TEST_ASSERT_FALSE(sim_timer_armed(&S, MC_TIMER_GRACE, 0));
    TEST_ASSERT_EQUAL_UINT8(MC_CRASH_LOOP_COUNT > 3 ? 0 : 0, S.core.diag.crash_count);
    mc_attrs_t a;
    mc_core_attrs(&S.core, &a);
    TEST_ASSERT_EQUAL_UINT8(MC_WAKE_REASON_TIMER, a.wake_reason);
    TEST_ASSERT_EQUAL_UINT16(12, a.wake_count);
    TEST_ASSERT_EQUAL_UINT32(3600, a.sleep_total_s);
    TEST_ASSERT_EQUAL_UINT16(3900, a.awake_ms);
}

static void test_a_normal_boot_still_counts_and_opens_the_grace_window(void)
{
    mc_board_t b = sleepy();
    mc_config_t cfg = deep_cfg();
    sim_init_board(&S, &b);
    sim_boot_opts_t o = {.config = &cfg};
    sim_boot(&S, &o);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.diag.reset_count);
    TEST_ASSERT_EQUAL_UINT16(1, S.core.event_n); /* the boot event */
    TEST_ASSERT_TRUE(S.core.grace_active);
    TEST_ASSERT_TRUE(sim_timer_armed(&S, MC_TIMER_GRACE, 0));
}

static void test_the_first_sample_after_a_deep_wake_comes_at_once_and_goes_out_as_a_report(void)
{
    mc_board_t b = sleepy();
    deep_wake(&b, 10, 3);
    TEST_ASSERT_EQUAL_INT_MESSAGE(0, S.reports, "no report of the old values first");
    sim_advance(&S, 100); /* 50 ms + the read */
    TEST_ASSERT_EQUAL_UINT16(11, S.core.seq);
    TEST_ASSERT_EQUAL_INT(1, S.reports);
}

static void test_the_awake_window_opens_when_the_report_is_done_and_ends_in_deep_sleep(void)
{
    mc_board_t b = sleepy();
    deep_wake(&b, 10, 3);
    sim_advance(&S, 100);
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core), "the report is out");
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_TRUE(sim_timer_armed(&S, MC_TIMER_AWAKE, 0));
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core), "listening for commands: light sleep at most");
    TEST_ASSERT_EQUAL_UINT16(MC_ALWAYS_ON_POLL_MS, S.poll_ms);
    sim_advance(&S, AWAKE_S * 1000 - 100);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_LIGHT, mc_core_sleep_allowed(&S.core));
    sim_advance(&S, 200);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_DEEP, mc_core_sleep_allowed(&S.core));
}

static void test_the_window_without_an_answer_to_the_report_still_closes(void)
{
    mc_board_t b = sleepy();
    deep_wake(&b, 10, 3);
    sim_advance(&S, 100 + MC_REPORT_TIMEOUT_MS + 100);            /* the report is never answered: timeout */
    sim_advance(&S, AWAKE_S * 1000 + 100);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_DEEP, mc_core_sleep_allowed(&S.core));
}

static void test_traffic_keeps_the_window_open(void)
{
    mc_board_t b = sleepy();
    deep_wake(&b, 10, 3);
    sim_advance(&S, 100);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    sim_advance(&S, AWAKE_S * 1000 - 1000);
    sim_send(&S, ev_action(21, MC_DEVICE_ACTION_IDENTIFY));      /* a command from the hub inside the window */
    sim_advance(&S, 2000);
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core), "identify blinks: awake");
    sim_advance(&S, MC_IDENTIFY_MS);
    sim_advance(&S, AWAKE_S * 1000 + 100);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_DEEP, mc_core_sleep_allowed(&S.core));
    S.core.awake_over = false;
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 120));
    TEST_ASSERT_TRUE_MESSAGE(sim_timer_armed(&S, MC_TIMER_AWAKE, 0), "a configuration write reopens the window");
}

static void test_the_sleep_time_keeps_the_wake_ups_one_interval_apart(void)
{
    mc_board_t b = sleepy();
    deep_wake(&b, 10, 3);
    sim_advance(&S, 100);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    sim_advance(&S, AWAKE_S * 1000 + 100);
    uint32_t slept = mc_core_deep_sleep_ms(&S.core);
    /* awake time since the wake + the boot loader + the sleep = one interval */
    TEST_ASSERT_EQUAL_UINT32((uint32_t)INTERVAL_S * 1000u, S.core.now_ms + MC_BOOT_COMP_MS + slept);
    mc_attrs_t a;
    mc_core_attrs(&S.core, &a);
    TEST_ASSERT_EQUAL_UINT16((uint16_t)(slept / 1000u), a.next_wake_s);
}

static void test_a_cycle_that_overran_still_sleeps_a_little(void)
{
    mc_board_t b = sleepy();
    deep_wake(&b, 10, 3);
    S.core.cfg.report_interval_s = 40;
    S.core.now_ms = 39800;
    TEST_ASSERT_EQUAL_UINT32(MC_DEEP_MIN_SLEEP_MS, mc_core_deep_sleep_ms(&S.core));
}

static void test_a_cold_boot_in_deep_mode_sleeps_after_the_grace_window_and_the_awake_window(void)
{
    mc_board_t b = sleepy();
    mc_config_t cfg = deep_cfg();
    sim_init_board(&S, &b);
    sim_to_operational(&S, &cfg);
    sim_advance(&S, 1500);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    sim_advance(&S, AWAKE_S * 1000 + 100);
    TEST_ASSERT_TRUE(S.core.awake_over);
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core), "still inside the 60 s after the boot");
    sim_advance(&S, MC_GRACE_MS);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_DEEP, mc_core_sleep_allowed(&S.core));
}

static void test_fast_reporting_after_a_watering_keeps_deep_sleep_off(void)
{
    mc_board_t b = sleepy();
    deep_wake(&b, 10, 3);
    sim_advance(&S, 100);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    sim_send(&S, ev_pump_run(88, 2, 5, 60));
    sim_advance(&S, 6000);                       /* the run is over, the 120 s of fast reporting follow */
    TEST_ASSERT_TRUE(S.core.fast);
    sim_advance(&S, AWAKE_S * 1000 + 100);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_NOT_EQUAL(MC_SLEEP_DEEP, mc_core_sleep_allowed(&S.core));
}

static void test_changing_the_mode_at_the_commit_takes_effect_at_once(void)
{
    mc_board_t b = sleepy();
    mc_config_t cfg;
    sim_cfg_default(&cfg);
    cfg.report_interval_s = INTERVAL_S;
    sim_init_board(&S, &b);
    sim_to_operational(&S, &cfg);
    sim_send(&S, ev_timer(MC_TIMER_GRACE, 0));
    sim_advance(&S, 1500);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    TEST_ASSERT_EQUAL_INT(MC_LED_SOLID, S.core.led);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));

    uint8_t mode = MC_POWER_MODE_DEEP_SLEEP;
    sim_send(&S, ev_write_bytes(MC_ATTR_POWER_MODE, &mode, 1));
    sim_send(&S, ev_commit((uint16_t)(S.core.cfg.rev + 1)));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_OK, S.core.cfg_result);
    TEST_ASSERT_EQUAL_INT_MESSAGE(MC_LED_OFF, S.core.led, "no LED all day on a sleeper");
    TEST_ASSERT_TRUE_MESSAGE(sim_timer_armed(&S, MC_TIMER_AWAKE, 0), "the window starts at the commit");
    sim_advance(&S, AWAKE_S * 1000 + 100);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_DEEP, mc_core_sleep_allowed(&S.core));

    mode = MC_POWER_MODE_ALWAYS_ON;
    S.core.awake_over = true;
    sim_send(&S, ev_write_bytes(MC_ATTR_POWER_MODE, &mode, 1));
    sim_send(&S, ev_commit((uint16_t)(S.core.cfg.rev + 1)));
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
    TEST_ASSERT_EQUAL_INT(MC_LED_SOLID, S.core.led);
    TEST_ASSERT_FALSE(S.core.awake_over);
    TEST_ASSERT_EQUAL_UINT16(MC_ALWAYS_ON_POLL_MS, S.poll_ms);
}

static void test_safe_mode_and_a_lost_parent_never_sleep(void)
{
    mc_board_t b = sleepy();
    deep_wake(&b, 10, 3);
    sim_advance(&S, 100);
    sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, true));
    sim_advance(&S, AWAKE_S * 1000 + 100);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_DEEP, mc_core_sleep_allowed(&S.core));
    sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST));
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
    sim_send(&S, ev_simple(MC_EV_CRASH_LOOP));
    TEST_ASSERT_EQUAL_INT(MC_LC_SAFE_MODE, S.core.lc);
    TEST_ASSERT_EQUAL_INT(MC_SLEEP_NONE, mc_core_sleep_allowed(&S.core));
}

void run_sleepcycle_tests(void)
{
    RUN_TEST(test_a_deep_sleep_wake_is_not_a_restart);
    RUN_TEST(test_a_normal_boot_still_counts_and_opens_the_grace_window);
    RUN_TEST(test_the_first_sample_after_a_deep_wake_comes_at_once_and_goes_out_as_a_report);
    RUN_TEST(test_the_awake_window_opens_when_the_report_is_done_and_ends_in_deep_sleep);
    RUN_TEST(test_the_window_without_an_answer_to_the_report_still_closes);
    RUN_TEST(test_traffic_keeps_the_window_open);
    RUN_TEST(test_the_sleep_time_keeps_the_wake_ups_one_interval_apart);
    RUN_TEST(test_a_cycle_that_overran_still_sleeps_a_little);
    RUN_TEST(test_a_cold_boot_in_deep_mode_sleeps_after_the_grace_window_and_the_awake_window);
    RUN_TEST(test_fast_reporting_after_a_watering_keeps_deep_sleep_off);
    RUN_TEST(test_changing_the_mode_at_the_commit_takes_effect_at_once);
    RUN_TEST(test_safe_mode_and_a_lost_parent_never_sleep);
}
