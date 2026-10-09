/* Sensing and report machine plus fast mode (PlantModule/specs.md 6, 7.4). */
#include "mc_internal.h"

#define SENSOR_FAULT_AFTER 3 /* consecutive bad samples before a sensor_fault event */
#define LOW_BATTERY_PRESENT_MV 500u /* below this no cell is connected (the divider reads ~0) */
#define LOW_BATTERY_HYSTERESIS_MV 100u

static uint32_t interval_ms(const mc_core_t *c)
{
    return (uint32_t)(c->fast ? c->cfg.fast_report_interval_s : c->cfg.report_interval_s) * 1000u;
}

static bool operational_container(const mc_core_t *c)
{
    return c->lc == MC_LC_INTERVIEWING || c->lc == MC_LC_OPERATIONAL || c->lc == MC_LC_REJOINING;
}

void mc_sense_start(mc_core_t *c, mc_actions_t *out)
{
    if (c->sn_active) {
        return;
    }
    c->sn_active = true;
    c->sn = MC_SN_IDLE;
    mc_arm(out, MC_TIMER_SAMPLE, 0, MC_FIRST_SAMPLE_MS);
}

void mc_sense_stop(mc_core_t *c, mc_actions_t *out)
{
    if (!c->sn_active) {
        return;
    }
    c->sn_active = false;
    c->sn = MC_SN_IDLE;
    c->fast = false;
    mc_cancel(out, MC_TIMER_SAMPLE, 0);
    mc_cancel(out, MC_TIMER_SLOT, 0);
    mc_cancel(out, MC_TIMER_SAMPLE_WINDOW, 0);
    mc_cancel(out, MC_TIMER_REPORT, 0);
    mc_cancel(out, MC_TIMER_FAST_HOLD, 0);
}

/* A changed interval or fast mode takes effect from now on. */
void mc_sense_rearm(mc_core_t *c, mc_actions_t *out)
{
    if (c->sn_active && c->sn != MC_SN_SAMPLING) {
        mc_arm(out, MC_TIMER_SAMPLE, 0, interval_ms(c));
    }
}

void mc_fast_enter(mc_core_t *c, mc_actions_t *out)
{
    mc_cancel(out, MC_TIMER_FAST_HOLD, 0);
    if (!c->fast) {
        c->fast = true;
        mc_sense_rearm(c, out);
    }
}

/* Called when a pump run ended: fast mode stays for the hold time after the last one. */
void mc_fast_maybe_leave(mc_core_t *c, mc_actions_t *out)
{
    if (!c->fast || mc_core_pump_running(c)) {
        return;
    }
    if (c->cfg.fast_report_hold_s == 0) {
        c->fast = false;
    } else {
        mc_arm(out, MC_TIMER_FAST_HOLD, 0, (uint32_t)c->cfg.fast_report_hold_s * 1000u);
    }
}

/* The output state of the pump slots, so an attribute update shows a pump that just started or stopped. */
void mc_readings_refresh_outputs(mc_core_t *c)
{
    for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) {
        if (c->cfg.slots[i].module == MC_MODULE_PUMP) {
            c->readings[i].type = MC_MODULE_PUMP;
            c->readings[i].error = MC_SENSOR_ERROR_OK;
            c->readings[i].value = c->pump[i].state == MC_PUMP_ON ? 10000 : 0;
            c->readings[i].raw = 0;
            c->readings[i].cfg_rev = c->cfg.rev;
        }
    }
}

static void finish_sample(mc_core_t *c, mc_actions_t *out)
{
    mc_cancel(out, MC_TIMER_SAMPLE_WINDOW, 0);
    mc_cancel(out, MC_TIMER_SLOT, 0);
    c->seq++;
    for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) {
        const mc_slot_cfg_t *s = &c->cfg.slots[i];
        mc_reading_t *r = &c->readings[i];
        r->type = s->module;
        r->cfg_rev = c->cfg.rev;
        if (s->module == MC_MODULE_MOISTURE) {
            r->error = c->sample[i].error;
            r->value = c->sample[i].error == MC_SENSOR_ERROR_OK ? c->sample[i].value : MC_VALUE_UNKNOWN;
            r->raw = c->sample[i].raw;
            if (r->error != MC_SENSOR_ERROR_OK) {
                if (c->err_streak[i] < 255) {
                    c->err_streak[i]++;
                }
                if (c->err_streak[i] >= SENSOR_FAULT_AFTER && !c->fault[i]) {
                    c->fault[i] = true;
                    mc_set_error(c, MC_ERR_SENSOR_FAULT);
                    mc_msg_event(c, out, MC_EVENT_CODE_SENSOR_FAULT, i, r->error);
                }
            } else {
                c->err_streak[i] = 0;
                if (c->fault[i]) {
                    c->fault[i] = false;
                    mc_msg_event(c, out, MC_EVENT_CODE_SENSOR_OK, i, 0);
                }
            }
        } else if (s->module == MC_MODULE_PUMP) {
            r->error = MC_SENSOR_ERROR_OK;
            r->value = c->pump[i].state == MC_PUMP_ON ? 10000 : 0; /* the output state */
            r->raw = 0;
        } else {
            r->error = MC_SENSOR_ERROR_OK;
            r->value = MC_VALUE_UNKNOWN;
            r->raw = 0;
            c->err_streak[i] = 0;
            c->fault[i] = false;
        }
    }
    mc_act(out, MC_ACT_UPDATE_ATTRS);
    mc_arm(out, MC_TIMER_SAMPLE, 0, interval_ms(c));
    if (c->fast && c->link_up) {
        mc_act(out, MC_ACT_REPORT_NOW);
        c->sn = MC_SN_REPORTING;
        mc_arm(out, MC_TIMER_REPORT, 0, MC_REPORT_TIMEOUT_MS);
    } else {
        c->sn = MC_SN_IDLE;
    }
}

static void read_next(mc_core_t *c, mc_actions_t *out)
{
    while (c->sn_next < MC_NUM_SLOTS && c->cfg.slots[c->sn_next].module != MC_MODULE_MOISTURE) {
        c->sn_next++;
    }
    if (c->sn_next >= MC_NUM_SLOTS) {
        finish_sample(c, out);
        return;
    }
    c->sn_cur = c->sn_next++;
    mc_action_t *a = mc_act(out, MC_ACT_READ_SLOT);
    a->u.read.slot = c->sn_cur;
    a->u.read.port = c->cfg.slots[c->sn_cur].port;
    mc_arm(out, MC_TIMER_SLOT, c->sn_cur, MC_SLOT_READ_TIMEOUT_MS);
}

static void start_sample(mc_core_t *c, mc_actions_t *out)
{
    c->sn = MC_SN_SAMPLING;
    c->sn_next = 0;
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        c->sample[i] = (mc_sample_t){.error = MC_SENSOR_ERROR_HW_ERROR, .value = 0, .raw = 0};
    }
    mc_arm(out, MC_TIMER_SAMPLE_WINDOW, 0, MC_SAMPLE_WINDOW_MS);
    read_next(c, out);
}

static void slot_result(mc_core_t *c, mc_actions_t *out, uint8_t slot, bool ok, uint16_t raw)
{
    if (c->sn != MC_SN_SAMPLING || slot != c->sn_cur) {
        return; /* a late answer of a slot that already timed out */
    }
    mc_cancel(out, MC_TIMER_SLOT, slot);
    const mc_slot_cfg_t *s = &c->cfg.slots[slot];
    c->sample[slot].raw = raw;
    if (!ok) {
        c->sample[slot].error = MC_SENSOR_ERROR_HW_ERROR;
    } else {
        int16_t v = 0;
        c->sample[slot].error = mc_moisture_convert(raw, s->cal_dry, s->cal_wet, c->adc_max, &v);
        c->sample[slot].value = v;
    }
    read_next(c, out);
}

void mc_sense_on_adc(mc_core_t *c, mc_actions_t *out, uint8_t slot, bool ok, uint16_t raw)
{
    slot_result(c, out, slot, ok, raw);
}

void mc_sense_on_timer(mc_core_t *c, mc_actions_t *out, mc_timer_t id, uint8_t arg)
{
    switch (id) {
    case MC_TIMER_SAMPLE:
        if (c->sn_active && c->sn != MC_SN_SAMPLING && operational_container(c)) {
            start_sample(c, out);
        }
        break;
    case MC_TIMER_SLOT:
        slot_result(c, out, arg, false, 0);
        break;
    case MC_TIMER_SAMPLE_WINDOW:
        if (c->sn == MC_SN_SAMPLING) { /* the remaining slots keep their hw_error */
            finish_sample(c, out);
        }
        break;
    case MC_TIMER_REPORT:
        if (c->sn == MC_SN_REPORTING) {
            c->sn = MC_SN_IDLE;
        }
        break;
    case MC_TIMER_FAST_HOLD:
        c->fast = false;
        mc_act(out, MC_ACT_UPDATE_ATTRS); /* fast_mode is an attribute */
        break;
    default:
        break;
    }
}

void mc_sense_on_report_result(mc_core_t *c, mc_actions_t *out)
{
    if (c->sn == MC_SN_REPORTING) {
        mc_cancel(out, MC_TIMER_REPORT, 0);
        c->sn = MC_SN_IDLE; /* a failed report is not repeated: the next sample follows */
    }
}

void mc_sense_on_battery(mc_core_t *c, mc_actions_t *out, uint16_t mv)
{
    c->voltage_mv = mv;
    if (mv < LOW_BATTERY_PRESENT_MV) {
        c->low_battery = false;
        return;
    }
    if (!c->low_battery && mv < c->cfg.batt_low_mv) {
        c->low_battery = true;
        mc_msg_event(c, out, MC_EVENT_CODE_LOW_BATTERY, MC_SLOT_NONE, mv);
    } else if (c->low_battery && mv >= c->cfg.batt_low_mv + LOW_BATTERY_HYSTERESIS_MV) {
        c->low_battery = false;
    }
}
