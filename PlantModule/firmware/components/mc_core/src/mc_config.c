#include "mc_config.h"

#include <string.h>

void mc_config_default(mc_config_t *c)
{
    memset(c, 0, sizeof *c);
    c->report_interval_s = MC_CFG_REPORT_INTERVAL_S_DEFAULT;
    c->fast_report_interval_s = MC_CFG_FAST_REPORT_INTERVAL_S_DEFAULT;
    c->fast_report_hold_s = MC_CFG_FAST_REPORT_HOLD_S_DEFAULT;
    c->batt_low_mv = MC_CFG_BATT_LOW_MV_DEFAULT;
}

static uint16_t le16(const uint8_t *p)
{
    return (uint16_t)(p[0] | (p[1] << 8));
}

bool mc_slot_cfg_parse(const uint8_t *b, size_t len, mc_slot_cfg_t *out)
{
    memset(out, 0, sizeof *out);
    if (len < 3) {
        return false;
    }
    out->module = b[0];
    out->port = b[1];
    out->active_high = (b[2] & 1u) != 0;
    switch (b[0]) {
    case MC_MODULE_MOISTURE:
        if (len < 8) {
            return false;
        }
        out->cal_dry = le16(b + 3);
        out->cal_wet = le16(b + 5);
        out->samples = b[7];
        out->active_high = false;
        return true;
    case MC_MODULE_PUMP:
        if (len < 7) {
            return false;
        }
        out->max_run_s = le16(b + 3);
        out->min_pause_s = le16(b + 5);
        return true;
    case MC_MODULE_EMPTY:
        memset(out, 0, sizeof *out);
        return true;
    default:
        return true; /* an unknown module is a validation error, not a malformed value */
    }
}

static bool port_exists(const mc_board_t *board, uint8_t port, uint8_t *role_mask)
{
    if (port & MC_PORT_RAW_FLAG) {
        *role_mask = MC_ROLE_MOISTURE | MC_ROLE_PUMP;
        return board->allow_raw_gpio;
    }
    if (port >= board->port_count) {
        return false;
    }
    *role_mask = board->ports[port].roles;
    return true;
}

static bool fail(mc_cfg_err_t *err, uint8_t code, uint8_t slot)
{
    if (err) {
        err->code = code;
        err->slot = slot;
    }
    return false;
}

bool mc_config_validate(const mc_config_t *c, const mc_board_t *board, mc_cfg_err_t *err)
{
    if (c->report_interval_s < MC_CFG_REPORT_INTERVAL_S_MIN || c->report_interval_s > MC_CFG_REPORT_INTERVAL_S_MAX ||
        c->fast_report_interval_s < MC_CFG_FAST_REPORT_INTERVAL_S_MIN ||
        c->fast_report_interval_s > MC_CFG_FAST_REPORT_INTERVAL_S_MAX ||
        c->fast_report_hold_s > MC_CFG_FAST_REPORT_HOLD_S_MAX) {
        return fail(err, MC_CFG_ERROR_OUT_OF_RANGE, MC_SLOT_NONE);
    }
    bool used[MC_MAX_PORTS + 1] = {false};
    bool raw_used[256] = {false};
    for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) {
        const mc_slot_cfg_t *s = &c->slots[i];
        if (s->module == MC_MODULE_EMPTY) {
            continue;
        }
        uint8_t role = 0;
        if (s->module == MC_MODULE_MOISTURE) {
            role = MC_ROLE_MOISTURE;
        } else if (s->module == MC_MODULE_PUMP) {
            role = MC_ROLE_PUMP;
        } else {
            return fail(err, MC_CFG_ERROR_ROLE_UNSUPPORTED, i);
        }
        uint8_t supported = 0;
        if (!port_exists(board, s->port, &supported)) {
            return fail(err, MC_CFG_ERROR_PORT_INVALID, i);
        }
        if (!(supported & role)) {
            return fail(err, MC_CFG_ERROR_ROLE_UNSUPPORTED, i);
        }
        bool *seen = (s->port & MC_PORT_RAW_FLAG) ? &raw_used[s->port] : &used[s->port];
        if (*seen) {
            return fail(err, MC_CFG_ERROR_PORT_CONFLICT, i);
        }
        *seen = true;
        if (s->module == MC_MODULE_MOISTURE) {
            if (s->cal_dry == s->cal_wet || s->samples < 1 || s->samples > MC_SAMPLES_MAX) {
                return fail(err, MC_CFG_ERROR_OUT_OF_RANGE, i);
            }
        } else if (s->max_run_s < 1 || s->max_run_s > MC_PUMP_HARD_MAX_S) {
            return fail(err, MC_CFG_ERROR_OUT_OF_RANGE, i);
        }
    }
    return true;
}

bool mc_slot_cfg_same(const mc_slot_cfg_t *a, const mc_slot_cfg_t *b)
{
    return memcmp(a, b, sizeof *a) == 0;
}

bool mc_config_same(const mc_config_t *a, const mc_config_t *b)
{
    if (a->report_interval_s != b->report_interval_s || a->fast_report_interval_s != b->fast_report_interval_s ||
        a->fast_report_hold_s != b->fast_report_hold_s || a->batt_low_mv != b->batt_low_mv) {
        return false;
    }
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        if (!mc_slot_cfg_same(&a->slots[i], &b->slots[i])) {
            return false;
        }
    }
    return true;
}
