/* Random event sequences: invariants that must hold whatever the radio and the user do. */
#include "sim.h"
#include "unity.h"

static sim_t S;

static uint32_t rng_state;
static uint32_t rnd(void)
{
    rng_state = rng_state * 1664525u + 1013904223u;
    return rng_state >> 8;
}

static void random_event(void)
{
    switch (rnd() % 16) {
    case 0: sim_send(&S, ev_pump_run(rnd() % 40, rnd() % 7, rnd() % 400, rnd() % 3 ? 900 : 0)); break;
    case 1: sim_send(&S, ev_pump_stop(rnd() % 40, rnd() % 7)); break;
    case 2: sim_send(&S, ev_cancel(rnd() % 40, rnd() % 40)); break;
    case 3: sim_send(&S, ev_simple(MC_EV_ZB_PARENT_LOST)); break;
    case 4: sim_send(&S, ev_bool(MC_EV_ZB_REJOIN_DONE, rnd() % 2)); break;
    case 5: sim_send(&S, ev_write_u16(MC_ATTR_REPORT_INTERVAL_S, (uint16_t)(rnd() % 4000))); break;
    case 6: sim_send(&S, ev_commit((uint16_t)(S.core.cfg.rev + rnd() % 3))); break;
    case 7: sim_send(&S, ev_bool(MC_EV_ZB_REPORT_RESULT, rnd() % 2)); break;
    case 8: sim_send(&S, ev_simple(MC_EV_BTN_SHORT)); break;
    case 9: sim_send(&S, ev_battery((uint16_t)(rnd() % 5000))); break;
    case 10: sim_send(&S, ev_action(rnd() % 40, (uint8_t)(rnd() % 4))); break;
    default: sim_advance(&S, rnd() % 20000); break;
    }
}

static void check_invariants(void)
{
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        if (S.core.cfg.slots[i].module != MC_MODULE_PUMP) {
            TEST_ASSERT_FALSE_MESSAGE(S.pump_on[i], "only pump slots drive outputs");
        }
        TEST_ASSERT_EQUAL_INT_MESSAGE(S.core.pump[i].state == MC_PUMP_ON, S.pump_on[i], "pin follows the state");
    }
    TEST_ASSERT_FALSE_MESSAGE(S.overflow_seen, "action list overflow");
    TEST_ASSERT_EQUAL_INT_MESSAGE(0, S.acks_sent_while_down, "ack sent while the link is down");
    TEST_ASSERT_TRUE_MESSAGE(S.longest_pump_run_ms <= (MC_PUMP_HARD_MAX_S * 1000u) + 100u, "pump ran too long");
}

static void test_random_events_keep_the_invariants(void)
{
    for (uint32_t seed = 1; seed <= 60; seed++) {
        rng_state = seed * 7919u;
        mc_config_t cfg;
        sim_cfg_default(&cfg);
        sim_init(&S, "carrier-v1");
        sim_to_operational(&S, &cfg);
        for (int i = 0; i < 400; i++) {
            random_event();
            check_invariants();
        }
    }
}

void run_fuzz_tests(void)
{
    RUN_TEST(test_random_events_keep_the_invariants);
}
