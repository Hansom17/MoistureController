/* Configuration transaction machine (PlantModule/specs.md 7.6). */
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

static void test_writes_alone_change_nothing_until_commit(void)
{
    operational();
    uint16_t old = S.core.cfg.report_interval_s;
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 60));
    TEST_ASSERT_EQUAL_UINT16(old, S.core.cfg.report_interval_s);
    TEST_ASSERT_EQUAL_INT(0, S.persist_config_calls);
}

static void test_commit_applies_validates_persists_and_reports_ok(void)
{
    operational();
    uint16_t rev = S.core.cfg.rev;
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 60));
    sim_send(&S, ev_commit(rev + 1));
    TEST_ASSERT_EQUAL_UINT16(60, S.core.cfg.report_interval_s);
    TEST_ASSERT_EQUAL_UINT16(rev + 1, S.core.cfg.rev);
    TEST_ASSERT_EQUAL_INT(1, S.persist_config_calls);
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_OK, S.attrs.cfg_result);
    TEST_ASSERT_EQUAL_UINT16(rev + 1, S.attrs.cfg_rev);
    TEST_ASSERT_EQUAL_UINT16(60, S.persisted_config.report_interval_s);
    TEST_ASSERT_TRUE(S.reports >= 1);
}

static void test_a_new_report_interval_takes_effect_at_the_next_sample(void)
{
    operational();
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 20));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    uint16_t seq = S.core.seq;
    sim_advance(&S, 20200);
    TEST_ASSERT_EQUAL_UINT16(seq + 1, S.core.seq);
}

static void test_out_of_range_values_are_rejected_and_nothing_is_applied(void)
{
    operational();
    uint16_t rev = S.core.cfg.rev;
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 5));
    sim_send(&S, ev_commit(rev + 1));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.attrs.cfg_result);
    TEST_ASSERT_EQUAL_UINT16((MC_CFG_ERROR_OUT_OF_RANGE << 8) | MC_SLOT_NONE, S.attrs.cfg_error);
    TEST_ASSERT_EQUAL_UINT16(rev, S.core.cfg.rev);
    TEST_ASSERT_EQUAL_INT(0, S.persist_config_calls);
    TEST_ASSERT_EQUAL_INT(1, sim_count_events(&S, MC_EVENT_CODE_CONFIG_REJECTED));
}

static void test_a_port_conflict_names_the_later_slot(void)
{
    operational();
    mc_slot_cfg_t s = {.module = MC_MODULE_MOISTURE, .port = 2, .cal_dry = 3000, .cal_wet = 1200, .samples = 8};
    sim_send(&S, ev_write_slot(1, &s));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.attrs.cfg_result);
    TEST_ASSERT_EQUAL_UINT16((MC_CFG_ERROR_PORT_CONFLICT << 8) | 2, S.attrs.cfg_error);
}

static void test_a_port_that_does_not_exist_is_rejected(void)
{
    operational();
    mc_slot_cfg_t s = {.module = MC_MODULE_MOISTURE, .port = 40, .cal_dry = 3000, .cal_wet = 1200, .samples = 8};
    sim_send(&S, ev_write_slot(1, &s));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    TEST_ASSERT_EQUAL_UINT16((MC_CFG_ERROR_PORT_INVALID << 8) | 1, S.attrs.cfg_error);
}

static void test_a_pump_ceiling_above_the_hard_limit_is_rejected(void)
{
    operational();
    mc_slot_cfg_t s = S.core.cfg.slots[2];
    s.max_run_s = 301;
    sim_send(&S, ev_write_slot(2, &s));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    TEST_ASSERT_EQUAL_UINT16((MC_CFG_ERROR_OUT_OF_RANGE << 8) | 2, S.attrs.cfg_error);
}

static void test_a_stale_revision_is_rejected(void)
{
    operational();
    sim_send(&S, ev_commit(S.core.cfg.rev - 1));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.attrs.cfg_result);
    TEST_ASSERT_EQUAL_UINT16((MC_CFG_ERROR_STALE_REV << 8) | MC_SLOT_NONE, S.attrs.cfg_error);
}

static void test_the_same_revision_again_answers_ok_without_writing(void)
{
    operational();
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 60));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    uint16_t rev = S.core.cfg.rev;
    int persisted = S.persist_config_calls;
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 60));
    sim_send(&S, ev_commit(rev));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_OK, S.attrs.cfg_result);
    TEST_ASSERT_EQUAL_INT(persisted, S.persist_config_calls);
}

static void test_the_same_revision_with_other_content_is_rejected(void)
{
    operational();
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 99));
    sim_send(&S, ev_commit(S.core.cfg.rev));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.attrs.cfg_result);
    TEST_ASSERT_NOT_EQUAL(99, S.core.cfg.report_interval_s);
}

static void test_an_unfinished_transaction_is_dropped_after_the_timeout(void)
{
    operational();
    uint16_t old = S.core.cfg.report_interval_s;
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 99));
    sim_advance(&S, 31000);
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(old, S.core.cfg.report_interval_s, "the staged value was dropped");
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_OK, S.attrs.cfg_result);
}

static void test_a_running_pump_slot_cannot_change(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 30, 900));
    mc_slot_cfg_t s = S.core.cfg.slots[2];
    s.max_run_s = 20;
    sim_send(&S, ev_write_slot(2, &s));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    TEST_ASSERT_EQUAL_UINT16((MC_CFG_ERROR_BUSY << 8) | 2, S.attrs.cfg_error);
    TEST_ASSERT_TRUE(S.pump_on[2]);
}

static void test_changing_a_slot_ends_its_pause(void)
{
    operational();
    sim_send(&S, ev_pump_run(1, 2, 5, 900));
    sim_advance(&S, 5100);
    mc_slot_cfg_t s = S.core.cfg.slots[2];
    s.min_pause_s = 10;
    sim_send(&S, ev_write_slot(2, &s));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    sim_send(&S, ev_pump_run(2, 2, 5, 900));
    ASSERT_ACK(&S, 2, MC_ACK_STATE_RUNNING, MC_REASON_NONE);
}

static void test_a_bad_slot_blob_is_rejected_at_commit(void)
{
    operational();
    uint8_t tiny[2] = {1, 2};
    sim_send(&S, ev_write_bytes(MC_ATTR_SLOT_CFG_1, tiny, 2));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_REJECTED, S.attrs.cfg_result);
}

static void test_a_rejected_commit_is_not_sticky(void)
{
    operational();
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 5));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, 60));
    sim_send(&S, ev_commit(S.core.cfg.rev + 1));
    TEST_ASSERT_EQUAL_UINT8(MC_CFG_RESULT_OK, S.attrs.cfg_result);
    TEST_ASSERT_EQUAL_UINT16(60, S.core.cfg.report_interval_s);
}

void run_config_tests(void)
{
    RUN_TEST(test_writes_alone_change_nothing_until_commit);
    RUN_TEST(test_commit_applies_validates_persists_and_reports_ok);
    RUN_TEST(test_a_new_report_interval_takes_effect_at_the_next_sample);
    RUN_TEST(test_out_of_range_values_are_rejected_and_nothing_is_applied);
    RUN_TEST(test_a_port_conflict_names_the_later_slot);
    RUN_TEST(test_a_port_that_does_not_exist_is_rejected);
    RUN_TEST(test_a_pump_ceiling_above_the_hard_limit_is_rejected);
    RUN_TEST(test_a_stale_revision_is_rejected);
    RUN_TEST(test_the_same_revision_again_answers_ok_without_writing);
    RUN_TEST(test_the_same_revision_with_other_content_is_rejected);
    RUN_TEST(test_an_unfinished_transaction_is_dropped_after_the_timeout);
    RUN_TEST(test_a_running_pump_slot_cannot_change);
    RUN_TEST(test_changing_a_slot_ends_its_pause);
    RUN_TEST(test_a_bad_slot_blob_is_rejected_at_commit);
    RUN_TEST(test_a_rejected_commit_is_not_sticky);
}
