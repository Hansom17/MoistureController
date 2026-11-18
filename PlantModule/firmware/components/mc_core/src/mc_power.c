/* Power modes (PlantModule/specs.md 18): when the HAL may sleep, how fast the parent is polled, the deep-sleep cycle.
 * Pure: the core never sleeps itself, the HAL asks after every step. */
#include "mc_internal.h"

static bool pump_busy(const mc_core_t *c)
{
    for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) {
        if (c->pump[i].state != MC_PUMP_OFF) {
            return true;
        }
    }
    return false;
}

static bool mode_runs(const mc_core_t *c)
{
    return c->cfg.power_mode != MC_POWER_MODE_ALWAYS_ON && mc_board_supports_power_mode(c->board, c->cfg.power_mode);
}

mc_sleep_t mc_core_sleep_allowed(const mc_core_t *c)
{
    if (!mode_runs(c) || c->grace_active) {
        return MC_SLEEP_NONE;
    }
    if (c->lc != MC_LC_OPERATIONAL || c->sn != MC_SN_IDLE || c->bat_pending || c->stage.active || c->pending_n > 0 ||
        c->identify || c->cue || pump_busy(c)) {
        return MC_SLEEP_NONE;
    }
    if (c->cfg.power_mode == MC_POWER_MODE_DEEP_SLEEP && c->awake_over && !c->fast) {
        return MC_SLEEP_DEEP;
    }
    return MC_SLEEP_LIGHT; /* light sleep, or deep sleep inside its awake window and after a watering */
}

uint16_t mc_core_poll_ms(const mc_core_t *c)
{
    bool quick = c->lc != MC_LC_OPERATIONAL || c->cfg.power_mode != MC_POWER_MODE_LIGHT_SLEEP || pump_busy(c) ||
                 c->fast || c->grace_active || !mode_runs(c);
    return quick ? (uint16_t)MC_ALWAYS_ON_POLL_MS : c->cfg.poll_interval_ms;
}

uint32_t mc_core_deep_sleep_ms(const mc_core_t *c)
{
    uint32_t cycle = (uint32_t)c->cfg.report_interval_s * 1000u;
    uint32_t used = c->now_ms + MC_BOOT_COMP_MS;
    return used + MC_DEEP_MIN_SLEEP_MS >= cycle ? MC_DEEP_MIN_SLEEP_MS : cycle - used;
}

/* The deep-sleep window after a report opens (or traffic keeps it open). */
static void arm_window(mc_core_t *c, mc_actions_t *out)
{
    c->awake_over = false;
    mc_arm(out, MC_TIMER_AWAKE, 0, (uint32_t)c->cfg.awake_s * 1000u);
}

/* A sample's report is finished (answered or timed out). */
void mc_power_report_done(mc_core_t *c, mc_actions_t *out)
{
    if (mode_runs(c) && c->cfg.power_mode == MC_POWER_MODE_DEEP_SLEEP) {
        arm_window(c, out);
    }
}

/* A command, a configuration write or anything else the module has to answer: stay reachable a little longer. */
void mc_power_traffic(mc_core_t *c, mc_actions_t *out)
{
    if (!mode_runs(c)) {
        return;
    }
    if (c->cfg.power_mode == MC_POWER_MODE_DEEP_SLEEP) {
        if (!c->awake_over || c->sn == MC_SN_IDLE) {
            arm_window(c, out);
        }
    } else {
        c->poll_fast_request = true;
    }
}

/* A new configuration was applied. */
void mc_power_config_applied(mc_core_t *c, mc_actions_t *out, uint8_t old_mode)
{
    if (c->cfg.power_mode != old_mode) {
        mc_cancel(out, MC_TIMER_AWAKE, 0);
        c->awake_over = false;
        if (mode_runs(c) && c->cfg.power_mode == MC_POWER_MODE_DEEP_SLEEP && c->sn == MC_SN_IDLE) {
            arm_window(c, out);
        }
        mc_led_update(c, out);
    }
    c->poll_fast_request = true;
}

void mc_power_on_timer(mc_core_t *c, mc_timer_t id)
{
    if (id == MC_TIMER_AWAKE) {
        c->awake_over = true;
    } else if (id == MC_TIMER_GRACE) {
        c->grace_active = false;
    }
}

/* The last thing of every step: tell the Zigbee layer when the poll interval it should use changed. */
void mc_power_after_step(mc_core_t *c, mc_actions_t *out)
{
    uint16_t want = mc_core_poll_ms(c);
    uint16_t fast = 0;
    if (c->poll_fast_request) {
        c->poll_fast_request = false;
        if (want > MC_ALWAYS_ON_POLL_MS) {
            fast = (uint16_t)MC_FAST_POLL_MS;
        }
    }
    if (want != c->last_poll_ms || fast != 0) {
        c->last_poll_ms = want;
        mc_action_t *a = mc_act(out, MC_ACT_POLL);
        a->u.poll.ms = want;
        a->u.poll.fast_ms = fast;
    }
}
