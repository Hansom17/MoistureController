/* Configuration machine (PlantModule/specs.md 7.6): writes stage, commit validates and applies. */
#include "mc_internal.h"

static uint16_t rd16(const uint8_t *p)
{
    return (uint16_t)(p[0] | (p[1] << 8));
}

static bool accepting(const mc_core_t *c)
{
    return c->lc == MC_LC_INTERVIEWING || c->lc == MC_LC_OPERATIONAL;
}

static void begin_stage(mc_core_t *c)
{
    if (!c->stage.active) {
        c->stage.active = true;
        c->stage.bad = false;
        c->stage.cfg = c->cfg;
    }
}

static void mark_bad(mc_core_t *c, uint8_t code, uint8_t slot)
{
    if (!c->stage.bad) {
        c->stage.bad = true;
        c->stage.bad_err = (mc_cfg_err_t){.code = code, .slot = slot};
    }
}

void mc_cfg_drop_stage(mc_core_t *c, mc_actions_t *out)
{
    if (c->stage.active) {
        mc_cancel(out, MC_TIMER_CFG_TXN, 0);
    }
    memset(&c->stage, 0, sizeof c->stage);
}

void mc_cfg_on_timeout(mc_core_t *c, mc_actions_t *out)
{
    (void)out;
    memset(&c->stage, 0, sizeof c->stage); /* staged values are dropped */
}

void mc_cfg_on_write(mc_core_t *c, mc_actions_t *out, uint16_t attr, const uint8_t *data, uint8_t len)
{
    if (!accepting(c)) {
        return;
    }
    bool scalar = attr == MC_ATTR_REPORT_INTERVAL_S || attr == MC_ATTR_FAST_REPORT_INTERVAL_S ||
                  attr == MC_ATTR_FAST_REPORT_HOLD_S || attr == MC_ATTR_BATT_LOW_MV ||
                  attr == MC_ATTR_BATT_CRITICAL_MV || attr == MC_ATTR_BATT_CAL_PERMILLE ||
                  attr == MC_ATTR_POLL_INTERVAL_MS || attr == MC_ATTR_POWER_MODE || attr == MC_ATTR_AWAKE_S;
    bool byte_wide = attr == MC_ATTR_POWER_MODE || attr == MC_ATTR_AWAKE_S; /* enum8 and uint8 */
    bool slot = attr >= MC_ATTR_SLOT_CFG_0 && attr <= MC_ATTR_SLOT_CFG_5;
    if (!scalar && !slot) {
        return;
    }
    begin_stage(c);
    mc_arm(out, MC_TIMER_CFG_TXN, 0, MC_CFG_TXN_TIMEOUT_MS);
    if (scalar) {
        if (len < (byte_wide ? 1 : 2)) {
            mark_bad(c, MC_CFG_ERROR_OUT_OF_RANGE, MC_SLOT_NONE);
            return;
        }
        uint16_t v = byte_wide ? data[0] : rd16(data);
        switch (attr) {
        case MC_ATTR_REPORT_INTERVAL_S:
            c->stage.cfg.report_interval_s = v;
            break;
        case MC_ATTR_FAST_REPORT_INTERVAL_S:
            c->stage.cfg.fast_report_interval_s = v;
            break;
        case MC_ATTR_FAST_REPORT_HOLD_S:
            c->stage.cfg.fast_report_hold_s = v;
            break;
        case MC_ATTR_BATT_LOW_MV:
            c->stage.cfg.batt_low_mv = v;
            break;
        case MC_ATTR_BATT_CRITICAL_MV:
            c->stage.cfg.batt_critical_mv = v;
            break;
        case MC_ATTR_POWER_MODE:
            c->stage.cfg.power_mode = (uint8_t)(v > 255 ? 255 : v);
            break;
        case MC_ATTR_POLL_INTERVAL_MS:
            c->stage.cfg.poll_interval_ms = v;
            break;
        case MC_ATTR_AWAKE_S:
            c->stage.cfg.awake_s = (uint8_t)(v > 255 ? 255 : v);
            break;
        default:
            c->stage.cfg.batt_cal_permille = v;
            break;
        }
        return;
    }
    uint8_t idx = (uint8_t)(attr - MC_ATTR_SLOT_CFG_0);
    if (!mc_slot_cfg_parse(data, len, &c->stage.cfg.slots[idx])) {
        mark_bad(c, MC_CFG_ERROR_OUT_OF_RANGE, idx);
    }
}

static void reject(mc_core_t *c, mc_actions_t *out, mc_cfg_err_t e)
{
    c->cfg_result = MC_CFG_RESULT_REJECTED;
    c->cfg_error = mc_cfg_err_wire(e);
    mc_set_error(c, MC_ERR_CONFIG_REJECTED);
    mc_msg_event(c, out, MC_EVENT_CODE_CONFIG_REJECTED, e.slot, e.code);
    mc_cfg_drop_stage(c, out);
    mc_act(out, MC_ACT_PERSIST_DIAG);
    mc_attrs_changed(out, c->link_up);
}

void mc_cfg_commit(mc_core_t *c, mc_actions_t *out, uint16_t rev)
{
    if (!accepting(c)) {
        reject(c, out, (mc_cfg_err_t){.code = MC_CFG_ERROR_BUSY, .slot = MC_SLOT_NONE});
        return;
    }
    if (rev < c->cfg.rev) {
        reject(c, out, (mc_cfg_err_t){.code = MC_CFG_ERROR_STALE_REV, .slot = MC_SLOT_NONE});
        return;
    }
    begin_stage(c);
    if (c->stage.bad) {
        reject(c, out, c->stage.bad_err);
        return;
    }
    c->stage.cfg.rev = rev;
    if (rev == c->cfg.rev) {
        if (mc_config_same(&c->stage.cfg, &c->cfg)) { /* the same revision again: answer ok again */
            c->cfg_result = MC_CFG_RESULT_OK;
            c->cfg_error = 0;
            mc_cfg_drop_stage(c, out);
            mc_attrs_changed(out, true);
        } else {
            reject(c, out, (mc_cfg_err_t){.code = MC_CFG_ERROR_STALE_REV, .slot = MC_SLOT_NONE});
        }
        return;
    }
    mc_cfg_err_t err;
    if (!mc_config_validate(&c->stage.cfg, c->board, &err)) {
        reject(c, out, err);
        return;
    }
    for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) { /* a slot whose pump is running cannot change */
        if (c->pump[i].state == MC_PUMP_ON && !mc_slot_cfg_same(&c->stage.cfg.slots[i], &c->cfg.slots[i])) {
            reject(c, out, (mc_cfg_err_t){.code = MC_CFG_ERROR_BUSY, .slot = i});
            return;
        }
    }

    /* apply to the running machines, then persist */
    bool intervals_changed = c->stage.cfg.report_interval_s != c->cfg.report_interval_s ||
                             c->stage.cfg.fast_report_interval_s != c->cfg.fast_report_interval_s;
    for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) {
        if (!mc_slot_cfg_same(&c->stage.cfg.slots[i], &c->cfg.slots[i])) {
            if (c->pump[i].state == MC_PUMP_PAUSE) {
                mc_cancel(out, MC_TIMER_PUMP_PAUSE, i);
                c->pump[i].state = MC_PUMP_OFF;
            }
            c->err_streak[i] = 0;
            c->fault[i] = false;
        }
    }
    c->cfg = c->stage.cfg;
    c->cfg_result = MC_CFG_RESULT_OK;
    c->cfg_error = 0;
    mc_cfg_drop_stage(c, out);
    mc_act(out, MC_ACT_PERSIST_CONFIG);
    if (intervals_changed) {
        mc_sense_rearm(c, out);
    }
    mc_attrs_changed(out, true);
}
