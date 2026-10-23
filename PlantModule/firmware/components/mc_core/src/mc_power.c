/* Which sleep the HAL may use right now (PlantModule/specs.md 18.4). Pure: it only reads the core's state. */
#include "mc_internal.h"

#define PUMP_STOP_POLL_MS 1000u /* poll interval cap while a pump runs: a stop must arrive quickly (L7) */

mc_sleep_t mc_core_sleep_allowed(const mc_core_t *c)
{
    if (c->cfg.power_mode == MC_POWER_MODE_ALWAYS_ON || !mc_board_supports_power_mode(c->board, c->cfg.power_mode)) {
        return MC_SLEEP_NONE;
    }
    if (c->lc != MC_LC_OPERATIONAL || c->sn != MC_SN_IDLE || c->bat_pending || c->stage.active || c->pending_n > 0 ||
        c->identify || c->cue) {
        return MC_SLEEP_NONE;
    }
    bool pump_busy = false;
    for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) {
        if (c->pump[i].state != MC_PUMP_OFF) {
            pump_busy = true;
        }
    }
    if (c->cfg.power_mode == MC_POWER_MODE_DEEP_SLEEP && !pump_busy && !c->fast) {
        return MC_SLEEP_DEEP;
    }
    return MC_SLEEP_LIGHT;
}

uint16_t mc_core_poll_ms(const mc_core_t *c)
{
    uint16_t ms = c->cfg.poll_interval_ms;
    if (mc_core_pump_running(c) && ms > PUMP_STOP_POLL_MS) {
        ms = PUMP_STOP_POLL_MS;
    }
    return ms;
}
