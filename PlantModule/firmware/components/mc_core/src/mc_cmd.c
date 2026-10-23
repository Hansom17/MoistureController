/* Command machines (PlantModule/specs.md 7.5): one actuator machine per pump slot and one record per
 * command id, so a repeated id is acknowledged again and never executed twice. */
#include "mc_internal.h"

static mc_cmd_rec_t *rec_find(mc_core_t *c, uint32_t cmd_id)
{
    for (int i = 0; i < MC_MAX_CMD_RECORDS; i++) {
        if (c->recs[i].used && c->recs[i].cmd_id == cmd_id) {
            return &c->recs[i];
        }
    }
    return NULL;
}

/* A new record; the oldest one is reused when the table is full (but never the record of a running pump). */
static mc_cmd_rec_t *rec_new(mc_core_t *c, uint32_t cmd_id, uint8_t kind, int *index)
{
    for (int tries = 0; tries < MC_MAX_CMD_RECORDS; tries++) {
        int i = c->rec_next;
        c->rec_next = (uint8_t)((c->rec_next + 1) % MC_MAX_CMD_RECORDS);
        if (c->recs[i].used && c->recs[i].running) {
            continue;
        }
        memset(&c->recs[i], 0, sizeof c->recs[i]);
        c->recs[i].used = true;
        c->recs[i].cmd_id = cmd_id;
        c->recs[i].kind = kind;
        if (index) {
            *index = i;
        }
        return &c->recs[i];
    }
    return NULL;
}

static void rec_answer(mc_cmd_rec_t *r, uint8_t state, uint8_t reason, uint16_t ends_in_s)
{
    r->state = state;
    r->reason = reason;
    r->ends_in_s = ends_in_s;
}

/* Answer a command and remember the answer for repeats. */
static void answer(mc_core_t *c, mc_actions_t *out, mc_cmd_rec_t *r, uint32_t cmd_id, uint8_t state, uint8_t reason,
                   uint16_t ends_in_s)
{
    if (r) {
        rec_answer(r, state, reason, ends_in_s);
    }
    mc_msg_ack(c, out, cmd_id, state, reason, ends_in_s);
}

static void drive(mc_core_t *c, mc_actions_t *out, uint8_t slot, bool on)
{
    mc_action_t *a = mc_act(out, MC_ACT_DRIVE_PUMP);
    a->u.pump.slot = slot;
    a->u.pump.port = c->cfg.slots[slot].port;
    a->u.pump.active_high = c->cfg.slots[slot].active_high;
    a->u.pump.on = on;
}

/* The run of a pump ends (time up, stop, cancel): off at once, pause for the minimum pause. */
static void pump_finish(mc_core_t *c, mc_actions_t *out, uint8_t slot, uint8_t ack_state, uint8_t reason)
{
    mc_pump_t *p = &c->pump[slot];
    drive(c, out, slot, false);
    mc_cancel(out, MC_TIMER_PUMP_END, slot);
    mc_cmd_rec_t *r = &c->recs[p->rec];
    if (r->used && r->running) {
        r->running = false;
        answer(c, out, r, r->cmd_id, ack_state, reason, 0);
    }
    uint16_t pause = c->cfg.slots[slot].min_pause_s;
    if (pause > 0) {
        p->state = MC_PUMP_PAUSE;
        mc_arm(out, MC_TIMER_PUMP_PAUSE, slot, (uint32_t)pause * 1000u);
    } else {
        p->state = MC_PUMP_OFF;
    }
    c->have_pump_end = true;
    c->last_pump_end_ms = c->now_ms;
    mc_fast_maybe_leave(c, out);
    mc_readings_refresh_outputs(c);
    mc_act(out, MC_ACT_UPDATE_ATTRS);
    if (c->link_up) {
        mc_act(out, MC_ACT_REPORT_NOW);
    }
}

void mc_pumps_force_off(mc_core_t *c, mc_actions_t *out)
{
    for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) {
        mc_pump_t *p = &c->pump[i];
        if (p->state == MC_PUMP_ON) {
            c->have_pump_end = true;
            c->last_pump_end_ms = c->now_ms;
            drive(c, out, i, false);
            mc_cancel(out, MC_TIMER_PUMP_END, i);
            c->recs[p->rec].running = false;
            rec_answer(&c->recs[p->rec], MC_ACK_STATE_CANCELLED, MC_REASON_NONE, 0);
        } else if (p->state == MC_PUMP_PAUSE) {
            mc_cancel(out, MC_TIMER_PUMP_PAUSE, i);
        }
        p->state = MC_PUMP_OFF;
    }
}

void mc_cmd_reset_all(mc_core_t *c)
{
    memset(c->recs, 0, sizeof c->recs);
    memset(c->tombs, 0, sizeof c->tombs);
    c->rec_next = 0;
}

void mc_cmd_on_timer(mc_core_t *c, mc_actions_t *out, mc_timer_t id, uint8_t arg)
{
    if (arg >= MC_NUM_SLOTS) {
        return;
    }
    if (id == MC_TIMER_PUMP_END) {
        if (c->pump[arg].state == MC_PUMP_ON) {
            pump_finish(c, out, arg, MC_ACK_STATE_DONE, MC_REASON_NONE);
        }
    } else if (c->pump[arg].state == MC_PUMP_PAUSE) {
        c->pump[arg].state = MC_PUMP_OFF;
    }
}

/* ---- tombstones: a cancel that arrives before its target ---------------------------------------------- */

static bool tomb_take(mc_core_t *c, uint32_t cmd_id)
{
    bool hit = false;
    for (int i = 0; i < MC_MAX_TOMBSTONES; i++) {
        mc_tombstone_t *t = &c->tombs[i];
        if (t->used && (int32_t)(c->now_ms - t->expires_ms) >= 0) {
            t->used = false; /* expired after 10 minutes */
        }
        if (t->used && t->cmd_id == cmd_id) {
            t->used = false;
            hit = true;
        }
    }
    return hit;
}

static void tomb_add(mc_core_t *c, uint32_t cmd_id)
{
    int slot = 0;
    uint32_t oldest = 0;
    for (int i = 0; i < MC_MAX_TOMBSTONES; i++) {
        if (!c->tombs[i].used) {
            slot = i;
            break;
        }
        uint32_t age = c->now_ms - (c->tombs[i].expires_ms - MC_TOMBSTONE_MS);
        if (age >= oldest) {
            oldest = age;
            slot = i;
        }
    }
    c->tombs[slot] = (mc_tombstone_t){.used = true, .cmd_id = cmd_id, .expires_ms = c->now_ms + MC_TOMBSTONE_MS};
}

/* ---- the commands --------------------------------------------------------------------------------------- */

static bool accepts_commands(const mc_core_t *c)
{
    return c->lc == MC_LC_OPERATIONAL;
}

static void pump_run(mc_core_t *c, mc_actions_t *out, const mc_cmd_t *cmd)
{
    int ri = 0;
    mc_cmd_rec_t *r = rec_new(c, cmd->cmd_id, MC_CMD_PUMP_RUN, &ri);
    uint8_t slot = cmd->slot;

    if (tomb_take(c, cmd->cmd_id)) {
        answer(c, out, r, cmd->cmd_id, MC_ACK_STATE_CANCELLED, MC_REASON_NONE, 0);
        return;
    }
    uint8_t reason = MC_REASON_NONE;
    if (!accepts_commands(c)) {
        reason = MC_REASON_BUSY;
    } else if (cmd->ttl_s == 0) {
        reason = MC_REASON_EXPIRED;
    } else if (slot >= MC_NUM_SLOTS || c->cfg.slots[slot].module != MC_MODULE_PUMP) {
        reason = MC_REASON_SLOT_NOT_ACTUATOR;
    } else if (c->batt_state == MC_BATT_STATE_CRITICAL) {
        reason = MC_REASON_BATTERY_LOW; /* a pump start on a nearly flat cell can brown the module out */
    } else {
        uint16_t max = c->cfg.slots[slot].max_run_s;
        if (max > MC_PUMP_HARD_MAX_S) {
            max = MC_PUMP_HARD_MAX_S;
        }
        if (cmd->seconds == 0 || cmd->seconds > max) {
            reason = MC_REASON_LIMIT;
        } else if (c->pump[slot].state == MC_PUMP_PAUSE) {
            reason = MC_REASON_MIN_PAUSE;
        } else if (c->pump[slot].state == MC_PUMP_ON) {
            reason = MC_REASON_BUSY;
        }
    }
    if (reason != MC_REASON_NONE) {
        answer(c, out, r, cmd->cmd_id, MC_ACK_STATE_REJECTED, reason, 0);
        return;
    }
    if (!r) { /* no free record: every one belongs to a running pump, cannot happen with six slots and eight records */
        mc_msg_ack(c, out, cmd->cmd_id, MC_ACK_STATE_REJECTED, MC_REASON_BUSY, 0);
        return;
    }
    mc_pump_t *p = &c->pump[slot];
    p->state = MC_PUMP_ON;
    p->rec = (uint8_t)ri;
    r->running = true;
    drive(c, out, slot, true);
    mc_arm(out, MC_TIMER_PUMP_END, slot, (uint32_t)cmd->seconds * 1000u);
    mc_fast_enter(c, out);
    answer(c, out, r, cmd->cmd_id, MC_ACK_STATE_RUNNING, MC_REASON_NONE, cmd->seconds);
    mc_readings_refresh_outputs(c);
    mc_act(out, MC_ACT_UPDATE_ATTRS);
    if (c->link_up) {
        mc_act(out, MC_ACT_REPORT_NOW);
    }
}

static void pump_stop(mc_core_t *c, mc_actions_t *out, const mc_cmd_t *cmd)
{
    mc_cmd_rec_t *r = rec_new(c, cmd->cmd_id, MC_CMD_PUMP_STOP, NULL);
    if (cmd->slot < MC_NUM_SLOTS && c->pump[cmd->slot].state == MC_PUMP_ON) {
        pump_finish(c, out, cmd->slot, MC_ACK_STATE_CANCELLED, MC_REASON_NONE);
    }
    answer(c, out, r, cmd->cmd_id, MC_ACK_STATE_DONE, MC_REASON_NONE, 0); /* stopping is never refused */
}

static void cancel(mc_core_t *c, mc_actions_t *out, const mc_cmd_t *cmd)
{
    mc_cmd_rec_t *r = rec_new(c, cmd->cmd_id, MC_CMD_CANCEL, NULL);
    mc_cmd_rec_t *target = rec_find(c, cmd->target);
    if (target == NULL) {
        tomb_add(c, cmd->target); /* answered `cancelled` when it arrives */
    } else if (target->running) {
        for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) {
            if (c->pump[i].state == MC_PUMP_ON && &c->recs[c->pump[i].rec] == target) {
                pump_finish(c, out, i, MC_ACK_STATE_CANCELLED, MC_REASON_NONE);
                break;
            }
        }
    }
    answer(c, out, r, cmd->cmd_id, MC_ACK_STATE_DONE, MC_REASON_NONE, 0);
}

static void device_action(mc_core_t *c, mc_actions_t *out, const mc_cmd_t *cmd)
{
    mc_cmd_rec_t *r = rec_new(c, cmd->cmd_id, MC_CMD_DEVICE_ACTION, NULL);
    answer(c, out, r, cmd->cmd_id, MC_ACK_STATE_DONE, MC_REASON_NONE, 0);
    switch (cmd->action) {
    case MC_DEVICE_ACTION_IDENTIFY:
        c->identify = true;
        mc_arm(out, MC_TIMER_IDENTIFY, 0, MC_IDENTIFY_MS);
        mc_led_update(c, out);
        break;
    case MC_DEVICE_ACTION_REBOOT:
        mc_lifecycle_reboot(c, out, false);
        break;
    case MC_DEVICE_ACTION_CLEAR_SAFE_MODE:
        if (c->lc == MC_LC_SAFE_MODE) {
            mc_lifecycle_reboot(c, out, true);
        }
        break;
    default:
        break;
    }
}

void mc_cmd_on_zb(mc_core_t *c, mc_actions_t *out, const mc_cmd_t *cmd)
{
    if (cmd->kind == MC_CMD_COMMIT_CONFIG) {
        mc_cfg_commit(c, out, cmd->rev);
        return;
    }
    mc_cmd_rec_t *known = rec_find(c, cmd->cmd_id);
    if (known) { /* never executed twice: the stored answer again */
        mc_msg_ack(c, out, cmd->cmd_id, known->state, known->reason, known->ends_in_s);
        return;
    }
    switch (cmd->kind) {
    case MC_CMD_PUMP_RUN:
        pump_run(c, out, cmd);
        break;
    case MC_CMD_PUMP_STOP:
        pump_stop(c, out, cmd);
        break;
    case MC_CMD_CANCEL:
        cancel(c, out, cmd);
        break;
    case MC_CMD_DEVICE_ACTION:
        device_action(c, out, cmd);
        break;
    default:
        break;
    }
}
