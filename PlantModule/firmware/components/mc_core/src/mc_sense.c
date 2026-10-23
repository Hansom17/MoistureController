/* Sensing and report machine plus fast mode (PlantModule/specs.md 6, 7.4). */
#include "mc_internal.h"

#define SENSOR_FAULT_AFTER 3 /* consecutive bad samples before a sensor_fault event */

static uint32_t interval_ms(const mc_core_t *c)
{
    return (uint32_t)(c->fast ? c->cfg.fast_report_interval_s : c->cfg.report_interval_s) * 1000u;
}

/* A sample is under way: settling or reading. */
static bool sampling_busy(const mc_core_t *c)
{
    return c->sn == MC_SN_SAMPLING || c->sn == MC_SN_SETTLING;
}

static void rail(mc_core_t *c, mc_actions_t *out, bool on)
{
    if (c->board == NULL || !c->board->sensor_power.present || c->sensor_rail_on == on) {
        return;
    }
    c->sensor_rail_on = on;
    mc_act(out, MC_ACT_SENSOR_POWER)->u.sensor_power.on = on;
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
    mc_cancel(out, MC_TIMER_BATTERY, 0);
    mc_cancel(out, MC_TIMER_SETTLE, 0);
    c->bat_pending = false;
    rail(c, out, false);
}

/* A changed interval or fast mode takes effect from now on. */
void mc_sense_rearm(mc_core_t *c, mc_actions_t *out)
{
    if (c->sn_active && !sampling_busy(c)) {
        mc_arm(out, MC_TIMER_SAMPLE, 0, interval_ms(c));
    }
}

/* device_action report_now: start a sample at once (it ends with an explicit report). A sample that is already running
 * ends with one anyway; the interval then continues from the end of this sample. */
void mc_sense_sample_now(mc_core_t *c, mc_actions_t *out)
{
    if (c->sn_active && !sampling_busy(c)) {
        mc_arm(out, MC_TIMER_SAMPLE, 0, 1);
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

/* ---- battery (PlantModule/specs.md 6.1) ------------------------------------------------------------------ */

/* A battery sample is taken with every sensor sample, but never while a pump loads the cell. */
static bool battery_due(const mc_core_t *c)
{
    if (c->board == NULL || c->board->battery_gpio < 0) {
        return false;
    }
    if (mc_core_pump_running(c)) {
        return false;
    }
    return !c->have_pump_end || (int32_t)(c->now_ms - c->last_pump_end_ms) >= (int32_t)MC_BATT_QUIET_MS;
}

/* Median of the n samples in the history (the mean of the two middle ones for an even count). */
static uint16_t median_of(const uint16_t *h, uint8_t n)
{
    uint16_t v[MC_BATT_FILTER_SAMPLES];
    for (uint8_t i = 0; i < n; i++) {
        uint16_t x = h[i];
        uint8_t j = i;
        while (j > 0 && v[j - 1] > x) {
            v[j] = v[j - 1];
            j--;
        }
        v[j] = x;
    }
    return n % 2 ? v[n / 2] : (uint16_t)(((uint32_t)v[n / 2 - 1] + v[n / 2]) / 2);
}

static void battery_evaluate(mc_core_t *c, mc_actions_t *out)
{
    uint16_t mv = c->voltage_mv;
    uint16_t low = c->cfg.batt_low_mv, crit = c->cfg.batt_critical_mv;
    uint8_t st = c->batt_state;
    if (st == MC_BATT_STATE_ABSENT) {
        st = MC_BATT_STATE_OK; /* a cell appeared: start from ok, the debounce below worsens it */
        c->bat_bad_streak = 0;
    }
    /* recovery is immediate, with hysteresis */
    if (st == MC_BATT_STATE_CRITICAL && mv > crit + MC_BATT_HYSTERESIS_MV) {
        st = MC_BATT_STATE_LOW;
        c->bat_bad_streak = 0;
    }
    if (st == MC_BATT_STATE_LOW && mv > low + MC_BATT_HYSTERESIS_MV) {
        st = MC_BATT_STATE_OK;
        c->bat_bad_streak = 0;
    }
    /* worsening needs MC_BATT_DEBOUNCE consecutive samples at or below the next threshold */
    uint8_t next = st;
    if (mv <= crit) {
        next = MC_BATT_STATE_CRITICAL;
    } else if (mv <= low && st == MC_BATT_STATE_OK) {
        next = MC_BATT_STATE_LOW;
    }
    if (next > st) {
        if (++c->bat_bad_streak >= MC_BATT_DEBOUNCE) {
            st = next;
            c->bat_bad_streak = 0;
            if (st == MC_BATT_STATE_CRITICAL) {
                mc_msg_event(c, out, MC_EVENT_CODE_BATTERY_CRITICAL, MC_SLOT_NONE, mv);
            } else {
                mc_msg_event(c, out, MC_EVENT_CODE_LOW_BATTERY, MC_SLOT_NONE, mv);
            }
        }
    } else {
        c->bat_bad_streak = 0;
    }
    c->batt_state = st;
}

static void finish_sample(mc_core_t *c, mc_actions_t *out)
{
    c->bat_pending = false;
    mc_cancel(out, MC_TIMER_BATTERY, 0);
    mc_cancel(out, MC_TIMER_SAMPLE_WINDOW, 0);
    mc_cancel(out, MC_TIMER_SLOT, 0);
    mc_cancel(out, MC_TIMER_SETTLE, 0);
    rail(c, out, false); /* the sensors are off again before anything else happens, also after a timeout */
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
    if (c->link_up) { /* every sample is sent: the slot attributes are octet strings, which the stack cannot report by itself */
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
        if (battery_due(c)) {
            c->bat_pending = true;
            mc_act(out, MC_ACT_READ_BATTERY);
            mc_arm(out, MC_TIMER_BATTERY, 0, MC_BATT_READ_TIMEOUT_MS);
            return;
        }
        finish_sample(c, out);
        return;
    }
    c->sn_cur = c->sn_next++;
    mc_action_t *a = mc_act(out, MC_ACT_READ_SLOT);
    a->u.read.slot = c->sn_cur;
    a->u.read.port = c->cfg.slots[c->sn_cur].port;
    mc_arm(out, MC_TIMER_SLOT, c->sn_cur, MC_SLOT_READ_TIMEOUT_MS);
}

/* The sensors are powered and settled (or never switched): read them one after the other. */
static void begin_reading(mc_core_t *c, mc_actions_t *out)
{
    c->sn = MC_SN_SAMPLING;
    c->sn_next = 0;
    mc_arm(out, MC_TIMER_SAMPLE_WINDOW, 0, MC_SAMPLE_WINDOW_MS);
    read_next(c, out);
}

static void start_sample(mc_core_t *c, mc_actions_t *out)
{
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        c->sample[i] = (mc_sample_t){.error = MC_SENSOR_ERROR_HW_ERROR, .value = 0, .raw = 0};
    }
    if (c->board != NULL && c->board->sensor_power.present) {
        c->sn = MC_SN_SETTLING;
        rail(c, out, true);
        mc_arm(out, MC_TIMER_SETTLE, 0, c->board->sensor_power.settle_ms > 0 ? c->board->sensor_power.settle_ms : 1u);
        return;
    }
    begin_reading(c, out);
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
        if (c->sn_active && !sampling_busy(c) && operational_container(c)) {
            start_sample(c, out);
        }
        break;
    case MC_TIMER_SETTLE:
        if (c->sn == MC_SN_SETTLING) {
            begin_reading(c, out);
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
    case MC_TIMER_BATTERY:
        if (c->bat_pending) {
            mc_sense_on_battery(c, out, false, 0); /* no answer: the value stays, the sample goes on */
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

void mc_sense_on_battery(mc_core_t *c, mc_actions_t *out, bool ok, uint16_t pin_mv)
{
    bool waiting = c->bat_pending;
    if (waiting) {
        c->bat_pending = false;
        mc_cancel(out, MC_TIMER_BATTERY, 0);
    }
    if (ok && c->board != NULL && c->board->battery_gpio >= 0) {
        uint32_t cell = (uint32_t)pin_mv * c->board->battery_divider_x100 / 100u;
        if (cell < MC_BATT_PRESENT_MV) { /* no cell: the divider reads about 0 */
            c->batt_state = MC_BATT_STATE_ABSENT;
            c->voltage_mv = 0;
            c->bat_n = 0;
            c->bat_bad_streak = 0;
        } else {
            cell = cell * c->cfg.batt_cal_permille / 1000u;
            if (cell > 65535u) {
                cell = 65535u;
            }
            if (c->bat_n < MC_BATT_FILTER_SAMPLES) {
                c->bat_hist[c->bat_n++] = (uint16_t)cell;
            } else {
                memmove(c->bat_hist, c->bat_hist + 1, (MC_BATT_FILTER_SAMPLES - 1) * sizeof c->bat_hist[0]);
                c->bat_hist[MC_BATT_FILTER_SAMPLES - 1] = (uint16_t)cell;
            }
            c->voltage_mv = median_of(c->bat_hist, c->bat_n);
            battery_evaluate(c, out);
        }
    }
    if (waiting && c->sn == MC_SN_SAMPLING) {
        finish_sample(c, out); /* the battery was the last step of the sample */
    } else {
        mc_act(out, MC_ACT_UPDATE_ATTRS);
    }
}
