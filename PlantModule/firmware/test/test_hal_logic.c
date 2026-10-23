/* The pure parts of the HAL: LED patterns, button decoder, stored configuration format. */
#include "mc_ui.h"
#include "sim.h"
#include "unity.h"

static void test_led_patterns(void)
{
    TEST_ASSERT_FALSE(mc_led_level(MC_LED_OFF, 0));
    TEST_ASSERT_TRUE(mc_led_level(MC_LED_SOLID, 12345));
    TEST_ASSERT_TRUE(mc_led_level(MC_LED_SLOW_BLINK, 100));
    TEST_ASSERT_FALSE(mc_led_level(MC_LED_SLOW_BLINK, 600));
    TEST_ASSERT_TRUE(mc_led_level(MC_LED_FAST_BLINK, 100));
    TEST_ASSERT_FALSE(mc_led_level(MC_LED_FAST_BLINK, 300));
    int edges = 0;
    bool last = false;
    for (uint32_t t = 0; t < 1600; t += 10) {
        bool l = mc_led_level(MC_LED_DOUBLE_BLINK, t);
        edges += l && !last;
        last = l;
    }
    TEST_ASSERT_EQUAL_INT_MESSAGE(2, edges, "double blink = two flashes per period");
    edges = 0;
    last = false;
    for (uint32_t t = 0; t < 2000; t += 10) {
        bool l = mc_led_level(MC_LED_TRIPLE_BLINK, t);
        edges += l && !last;
        last = l;
    }
    TEST_ASSERT_EQUAL_INT_MESSAGE(3, edges, "triple blink = three flashes per period");
}

/* Runs the button through a press of `hold_ms`, polling every 10 ms; returns the events in order. */
static int press(mc_button_t *b, uint32_t *t, uint32_t hold_ms, mc_ev_kind_t *out, int cap)
{
    int n = 0;
    mc_ev_kind_t k;
    for (uint32_t i = 0; i < hold_ms; i += 10, *t += 10) {
        if (mc_button_poll(b, *t, true, &k) && n < cap) {
            out[n++] = k;
        }
    }
    for (int i = 0; i < 10; i++, *t += 10) {
        if (mc_button_poll(b, *t, false, &k) && n < cap) {
            out[n++] = k;
        }
    }
    return n;
}

static void test_button_short_press(void)
{
    mc_button_t b;
    mc_button_init(&b);
    uint32_t t = 1000;
    mc_ev_kind_t ev[4];
    TEST_ASSERT_EQUAL_INT(1, press(&b, &t, 300, ev, 4));
    TEST_ASSERT_EQUAL_INT(MC_EV_BTN_SHORT, ev[0]);
}

static void test_button_bounce_is_ignored(void)
{
    mc_button_t b;
    mc_button_init(&b);
    mc_ev_kind_t k;
    for (uint32_t t = 1000; t < 1030; t += 10) {
        TEST_ASSERT_FALSE(mc_button_poll(&b, t, (t / 10) % 2, &k));
    }
    for (uint32_t t = 1030; t < 1200; t += 10) {
        TEST_ASSERT_FALSE(mc_button_poll(&b, t, false, &k));
    }
}

static void test_button_holds(void)
{
    mc_button_t b;
    mc_button_init(&b);
    uint32_t t = 1000;
    mc_ev_kind_t ev[4];
    TEST_ASSERT_EQUAL_INT(2, press(&b, &t, 5000, ev, 4));
    TEST_ASSERT_EQUAL_INT(MC_EV_BTN_HOLD_3S, ev[0]);
    TEST_ASSERT_EQUAL_INT(MC_EV_BTN_RELEASE, ev[1]);
    TEST_ASSERT_EQUAL_INT(3, press(&b, &t, 11000, ev, 4));
    TEST_ASSERT_EQUAL_INT(MC_EV_BTN_HOLD_3S, ev[0]);
    TEST_ASSERT_EQUAL_INT(MC_EV_BTN_HOLD_10S, ev[1]);
    TEST_ASSERT_EQUAL_INT(MC_EV_BTN_RELEASE, ev[2]);
    TEST_ASSERT_EQUAL_INT(1, press(&b, &t, 200, ev, 4));
}

static void test_config_blob_round_trip(void)
{
    mc_config_t c, d;
    sim_cfg_default(&c);
    c.rev = 513;
    c.slots[0].cal_dry = 3100;
    c.slots[2].max_run_s = 45;
    c.slots[2].min_pause_s = 65000;
    c.slots[2].active_high = false;
    uint8_t blob[MC_CONFIG_BLOB_SIZE];
    TEST_ASSERT_EQUAL_UINT(MC_CONFIG_BLOB_SIZE, mc_config_encode(&c, blob));
    TEST_ASSERT_TRUE(mc_config_decode(blob, sizeof blob, &d));
    TEST_ASSERT_EQUAL_UINT16(513, d.rev);
    TEST_ASSERT_TRUE(mc_config_same(&c, &d));
}

static void test_config_blob_rejects_damage(void)
{
    mc_config_t c, d;
    sim_cfg_default(&c);
    uint8_t blob[MC_CONFIG_BLOB_SIZE];
    mc_config_encode(&c, blob);
    TEST_ASSERT_FALSE(mc_config_decode(blob, sizeof blob - 1, &d));
    for (size_t i = 0; i < sizeof blob; i++) {
        uint8_t save = blob[i];
        blob[i] ^= 0x10;
        TEST_ASSERT_FALSE_MESSAGE(mc_config_decode(blob, sizeof blob, &d), "any flipped bit is detected");
        blob[i] = save;
    }
    blob[0] = 99; /* unknown schema */
    TEST_ASSERT_FALSE(mc_config_decode(blob, sizeof blob, &d));
}

void run_hal_logic_tests(void)
{
    RUN_TEST(test_led_patterns);
    RUN_TEST(test_button_short_press);
    RUN_TEST(test_button_bounce_is_ignored);
    RUN_TEST(test_button_holds);
    RUN_TEST(test_config_blob_round_trip);
    RUN_TEST(test_config_blob_rejects_damage);
}
