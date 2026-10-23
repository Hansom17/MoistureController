#include "mc_ui.h"

bool mc_led_level(mc_led_t pattern, uint32_t t)
{
    switch (pattern) {
    case MC_LED_SOLID:
        return true;
    case MC_LED_SLOW_BLINK: /* 1 Hz */
        return (t % 1000u) < 500u;
    case MC_LED_FAST_BLINK: /* 2.5 Hz */
        return (t % 400u) < 200u;
    case MC_LED_IDENTIFY: /* 5 Hz */
        return (t % 200u) < 100u;
    case MC_LED_DOUBLE_BLINK: { /* two flashes, pause, every 1.6 s */
        uint32_t p = t % 1600u;
        return p < 150u || (p >= 300u && p < 450u);
    }
    case MC_LED_TRIPLE_BLINK: { /* three flashes, pause, every 2 s */
        uint32_t p = t % 2000u;
        return p < 150u || (p >= 300u && p < 450u) || (p >= 600u && p < 750u);
    }
    default:
        return false;
    }
}

void mc_button_init(mc_button_t *b)
{
    *b = (mc_button_t){0};
}

bool mc_button_poll(mc_button_t *b, uint32_t now, bool pressed, mc_ev_kind_t *kind)
{
    if (pressed != b->raw) {
        b->raw = pressed;
        b->raw_since = now;
    }
    if (b->raw != b->stable && (uint32_t)(now - b->raw_since) >= MC_BTN_DEBOUNCE_MS) {
        b->stable = b->raw;
        if (b->stable) {
            b->pressed_at = b->raw_since;
            b->sent_3s = b->sent_10s = false;
            return false;
        }
        bool held = b->sent_3s || b->sent_10s;
        b->sent_3s = b->sent_10s = false;
        *kind = held ? MC_EV_BTN_RELEASE : MC_EV_BTN_SHORT;
        return true;
    }
    if (b->stable) {
        uint32_t held_ms = (uint32_t)(now - b->pressed_at);
        if (!b->sent_3s && held_ms >= MC_BTN_HOLD_3S_MS) {
            b->sent_3s = true;
            *kind = MC_EV_BTN_HOLD_3S;
            return true;
        }
        if (!b->sent_10s && held_ms >= MC_BTN_HOLD_10S_MS) {
            b->sent_10s = true;
            *kind = MC_EV_BTN_HOLD_10S;
            return true;
        }
    }
    return false;
}
