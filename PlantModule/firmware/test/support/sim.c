#include "sim.h"

#include <string.h>

/* ---- timers and the event queue of the fake world ---------------------------------------------------- */

static void pending_add(sim_t *s, uint32_t fire_ms, const mc_event_t *ev)
{
    for (int i = 0; i < SIM_MAX_TIMERS; i++) {
        if (!s->timers[i].used) {
            s->timers[i] = (sim_pending_t){.used = true, .fire_ms = fire_ms, .ev = *ev};
            return;
        }
    }
    TEST_FAIL_MESSAGE("too many timers armed");
}

static void timer_cancel(sim_t *s, mc_timer_t id, uint8_t arg)
{
    for (int i = 0; i < SIM_MAX_TIMERS; i++) {
        sim_pending_t *p = &s->timers[i];
        if (p->used && p->ev.kind == MC_EV_TIMER && p->ev.u.timer.id == id && p->ev.u.timer.arg == arg) {
            p->used = false;
        }
    }
}

bool sim_timer_armed(const sim_t *s, mc_timer_t id, uint8_t arg)
{
    for (int i = 0; i < SIM_MAX_TIMERS; i++) {
        const sim_pending_t *p = &s->timers[i];
        if (p->used && p->ev.kind == MC_EV_TIMER && p->ev.u.timer.id == id && p->ev.u.timer.arg == arg) {
            return true;
        }
    }
    return false;
}

/* ---- executing actions -------------------------------------------------------------------------------- */

static void set_pump(sim_t *s, uint8_t slot, bool on)
{
    TEST_ASSERT_TRUE_MESSAGE(slot < MC_NUM_SLOTS, "pump slot out of range");
    if (on && !s->pump_on[slot]) {
        s->pump_on_since[slot] = s->now;
        s->pump_edges[slot]++;
    }
    if (!on && s->pump_on[slot]) {
        uint32_t ran = s->now - s->pump_on_since[slot];
        if (ran > s->longest_pump_run_ms) {
            s->longest_pump_run_ms = ran;
        }
    }
    s->pump_on[slot] = on;
}

static void exec(sim_t *s, const mc_action_t *a)
{
    if (s->n_kinds < (int)(sizeof s->kinds / sizeof s->kinds[0])) {
        s->kinds[s->n_kinds++] = a->kind;
    }
    switch (a->kind) {
    case MC_ACT_START_ZIGBEE:
        s->zigbee_started = true;
        break;
    case MC_ACT_START_STEERING:
        s->steering_started = true;
        break;
    case MC_ACT_REJOIN:
        s->rejoin_calls++;
        break;
    case MC_ACT_LEAVE_NETWORK:
        s->left = true;
        break;
    case MC_ACT_ERASE_STATE:
        s->erased = true;
        break;
    case MC_ACT_UPDATE_ATTRS:
        s->attr_updates++;
        mc_core_attrs(&s->core, &s->attrs);
        break;
    case MC_ACT_REPORT_NOW:
        s->reports++;
        s->last_report_ms = s->now;
        break;
    case MC_ACT_SEND_CMD_ACK:
        if (!s->core.link_up) {
            s->acks_sent_while_down++;
        }
        if (s->n_acks < SIM_MAX_LOG) {
            s->acks[s->n_acks++] = (sim_ack_t){.t = s->now, .n = a->u.ack.n, .cmd_id = a->u.ack.cmd_id,
                                               .state = a->u.ack.state, .reason = a->u.ack.reason,
                                               .ends_in_s = a->u.ack.ends_in_s};
        }
        break;
    case MC_ACT_SEND_EVENT:
        if (!s->core.link_up) {
            s->acks_sent_while_down++;
        }
        if (s->n_events < SIM_MAX_LOG) {
            s->events[s->n_events++] = (sim_event_t){.t = s->now, .n = a->u.event.n, .code = a->u.event.code,
                                                     .slot = a->u.event.slot, .arg = a->u.event.arg};
        }
        break;
    case MC_ACT_DRIVE_PUMP:
        set_pump(s, a->u.pump.slot, a->u.pump.on);
        break;
    case MC_ACT_ALL_OUTPUTS_OFF:
        for (uint8_t i = 0; i < MC_NUM_SLOTS; i++) {
            set_pump(s, i, false);
        }
        break;
    case MC_ACT_READ_SLOT:
        s->read_slot_calls++;
        if (!s->adc_silent[a->u.read.slot]) {
            mc_event_t ev = {.kind = MC_EV_ADC_DONE};
            ev.u.adc.slot = a->u.read.slot;
            ev.u.adc.ok = s->adc_ok[a->u.read.slot];
            ev.u.adc.raw = s->adc_raw[a->u.read.slot];
            ev.now_ms = s->now + s->adc_delay_ms;
            pending_add(s, s->now + s->adc_delay_ms, &ev);
        }
        break;
    case MC_ACT_READ_BATTERY:
        s->read_battery_calls++;
        if (!s->batt_silent) {
            mc_event_t ev = {.kind = MC_EV_BATT_SAMPLE};
            ev.u.batt.mv = s->batt_pin_mv;
            ev.u.batt.ok = s->batt_ok;
            ev.now_ms = s->now + s->adc_delay_ms;
            pending_add(s, s->now + s->adc_delay_ms, &ev);
        }
        break;
    case MC_ACT_PERSIST_CONFIG:
        s->persist_config_calls++;
        s->persisted_config = s->core.cfg;
        break;
    case MC_ACT_PERSIST_DIAG:
        s->persist_diag_calls++;
        s->persisted_diag = s->core.diag;
        break;
    case MC_ACT_SET_LED:
        s->led = a->u.led;
        if (s->n_led < 16) {
            s->led_history[s->n_led++] = a->u.led;
        }
        break;
    case MC_ACT_ARM_TIMER: {
        timer_cancel(s, a->u.timer.id, a->u.timer.arg);
        mc_event_t ev = {.kind = MC_EV_TIMER};
        ev.u.timer.id = a->u.timer.id;
        ev.u.timer.arg = a->u.timer.arg;
        pending_add(s, s->now + a->u.timer.delay_ms, &ev);
        break;
    }
    case MC_ACT_CANCEL_TIMER:
        timer_cancel(s, a->u.timer.id, a->u.timer.arg);
        break;
    case MC_ACT_REBOOT:
        s->reboots++;
        break;
    }
}

void sim_send(sim_t *s, mc_event_t ev)
{
    ev.now_ms = s->now;
    mc_core_step(&s->core, &ev, &s->last);
    if (s->last.overflow) {
        s->overflow_seen = true;
    }
    TEST_ASSERT_FALSE_MESSAGE(s->last.overflow, "the core returned more actions than fit");
    for (size_t i = 0; i < s->last.n; i++) {
        exec(s, &s->last.a[i]);
    }
}

void sim_advance(sim_t *s, uint32_t ms)
{
    uint32_t end = s->now + ms;
    for (;;) {
        int best = -1;
        for (int i = 0; i < SIM_MAX_TIMERS; i++) {
            if (s->timers[i].used && s->timers[i].fire_ms <= end &&
                (best < 0 || s->timers[i].fire_ms < s->timers[best].fire_ms)) {
                best = i;
            }
        }
        if (best < 0) {
            break;
        }
        mc_event_t ev = s->timers[best].ev;
        s->now = s->timers[best].fire_ms;
        s->timers[best].used = false;
        sim_send(s, ev);
    }
    s->now = end;
}

/* ---- setup ---------------------------------------------------------------------------------------------- */

void sim_init(sim_t *s, const char *board_name)
{
    memset(s, 0, sizeof *s);
    s->now = 1000;
    mc_core_init(&s->core, board_name ? mc_board_find(board_name) : NULL, 4095);
    s->batt_pin_mv = 1950; /* 3.9 V through the 2.0 divider of carrier-v1 */
    s->batt_ok = true;
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        s->adc_ok[i] = true;
        s->adc_raw[i] = 2100;
    }
    s->adc_delay_ms = 20;
}

void sim_cfg_default(mc_config_t *c)
{
    mc_config_default(c);
    c->rev = 2;
    c->slots[0] = (mc_slot_cfg_t){.module = MC_MODULE_MOISTURE, .port = 0, .cal_dry = 3000, .cal_wet = 1200, .samples = 16};
    c->slots[2] = (mc_slot_cfg_t){.module = MC_MODULE_PUMP, .port = 2, .active_high = true, .max_run_s = 60, .min_pause_s = 600};
}

void sim_boot(sim_t *s, const sim_boot_opts_t *o)
{
    mc_event_t ev = {.kind = MC_EV_BOOT};
    mc_boot_t *b = &ev.u.boot;
    sim_boot_opts_t none = {0};
    if (!o) {
        o = &none;
    }
    b->factory_valid = !o->factory_invalid;
    b->first_boot = o->first_boot;
    b->reset_reason = o->reset_reason;
    b->crash_count_stored = o->crash_count_stored;
    b->boot_id = o->boot_id ? o->boot_id : 7;
    b->config_valid = !o->config_invalid;
    if (o->config) {
        b->config = *o->config;
    } else {
        mc_config_default(&b->config);
    }
    sim_send(s, ev);
}

void sim_to_operational(sim_t *s, const mc_config_t *cfg)
{
    sim_boot_opts_t o = {.config = cfg};
    sim_boot(s, &o);
    sim_send(s, ev_bool(MC_EV_ZB_STACK_READY, true));
    TEST_ASSERT_EQUAL_INT(MC_LC_OPERATIONAL, s->core.lc);
    sim_clear_logs(s);
}

/* ---- event builders --------------------------------------------------------------------------------------- */

mc_event_t ev_simple(mc_ev_kind_t kind)
{
    return (mc_event_t){.kind = kind};
}

mc_event_t ev_bool(mc_ev_kind_t kind, bool v)
{
    mc_event_t e = {.kind = kind};
    e.u.ok = v;
    return e;
}

static mc_event_t ev_cmd(mc_cmd_kind_t kind, uint32_t id)
{
    mc_event_t e = {.kind = MC_EV_ZB_CMD};
    e.u.cmd.kind = kind;
    e.u.cmd.cmd_id = id;
    return e;
}

mc_event_t ev_pump_run(uint32_t id, uint8_t slot, uint16_t seconds, uint16_t ttl_s)
{
    mc_event_t e = ev_cmd(MC_CMD_PUMP_RUN, id);
    e.u.cmd.slot = slot;
    e.u.cmd.seconds = seconds;
    e.u.cmd.ttl_s = ttl_s;
    return e;
}

mc_event_t ev_pump_stop(uint32_t id, uint8_t slot)
{
    mc_event_t e = ev_cmd(MC_CMD_PUMP_STOP, id);
    e.u.cmd.slot = slot;
    return e;
}

mc_event_t ev_cancel(uint32_t id, uint32_t target)
{
    mc_event_t e = ev_cmd(MC_CMD_CANCEL, id);
    e.u.cmd.target = target;
    return e;
}

mc_event_t ev_action(uint32_t id, uint8_t action)
{
    mc_event_t e = ev_cmd(MC_CMD_DEVICE_ACTION, id);
    e.u.cmd.action = action;
    return e;
}

mc_event_t ev_commit(uint16_t rev)
{
    mc_event_t e = ev_cmd(MC_CMD_COMMIT_CONFIG, 0);
    e.u.cmd.rev = rev;
    return e;
}

mc_event_t ev_write_bytes(uint16_t attr, const uint8_t *b, uint8_t n)
{
    mc_event_t e = {.kind = MC_EV_ZB_ATTR_WRITE};
    e.u.write.attr = attr;
    memcpy(e.u.write.data, b, n);
    e.u.write.len = n;
    return e;
}

mc_event_t ev_write_u16(uint16_t attr, uint16_t v)
{
    uint8_t b[2] = {(uint8_t)(v & 0xFF), (uint8_t)(v >> 8)};
    return ev_write_bytes(attr, b, 2);
}

uint8_t sim_encode_slot(const mc_slot_cfg_t *c, uint8_t out[8])
{
    memset(out, 0, 8);
    out[0] = c->module;
    out[1] = c->port;
    if (c->module == MC_MODULE_MOISTURE) {
        out[3] = (uint8_t)(c->cal_dry & 0xFF);
        out[4] = (uint8_t)(c->cal_dry >> 8);
        out[5] = (uint8_t)(c->cal_wet & 0xFF);
        out[6] = (uint8_t)(c->cal_wet >> 8);
        out[7] = c->samples;
        return 8;
    }
    if (c->module == MC_MODULE_PUMP) {
        out[2] = c->active_high ? 1 : 0;
        out[3] = (uint8_t)(c->max_run_s & 0xFF);
        out[4] = (uint8_t)(c->max_run_s >> 8);
        out[5] = (uint8_t)(c->min_pause_s & 0xFF);
        out[6] = (uint8_t)(c->min_pause_s >> 8);
        return 7;
    }
    return 3;
}

mc_event_t ev_write_slot(uint8_t idx, const mc_slot_cfg_t *cfg)
{
    uint8_t b[8];
    uint8_t n = sim_encode_slot(cfg, b);
    return ev_write_bytes((uint16_t)(MC_ATTR_SLOT_CFG_0 + idx), b, n);
}

mc_event_t ev_timer(mc_timer_t id, uint8_t arg)
{
    mc_event_t e = {.kind = MC_EV_TIMER};
    e.u.timer.id = id;
    e.u.timer.arg = arg;
    return e;
}

mc_event_t ev_battery(uint16_t mv)
{
    mc_event_t e = {.kind = MC_EV_BATT_SAMPLE};
    e.u.batt.mv = mv;
    e.u.batt.ok = true;
    return e;
}

/* ---- inspection -------------------------------------------------------------------------------------------- */

const sim_ack_t *sim_last_ack(const sim_t *s)
{
    return s->n_acks ? &s->acks[s->n_acks - 1] : NULL;
}

const sim_ack_t *sim_find_ack(const sim_t *s, uint32_t cmd_id, int nth)
{
    const sim_ack_t *found = NULL;
    int seen = 0;
    for (int i = 0; i < s->n_acks; i++) {
        if (s->acks[i].cmd_id == cmd_id) {
            if (nth >= 0 && seen == nth) {
                return &s->acks[i];
            }
            seen++;
            found = &s->acks[i];
        }
    }
    return nth < 0 ? found : NULL;
}

int sim_count_acks(const sim_t *s, uint32_t cmd_id)
{
    int n = 0;
    for (int i = 0; i < s->n_acks; i++) {
        n += s->acks[i].cmd_id == cmd_id;
    }
    return n;
}

int sim_count_events(const sim_t *s, uint8_t code)
{
    int n = 0;
    for (int i = 0; i < s->n_events; i++) {
        n += s->events[i].code == code;
    }
    return n;
}

int sim_count_kind(const sim_t *s, mc_act_kind_t kind)
{
    int n = 0;
    for (int i = 0; i < s->n_kinds; i++) {
        n += s->kinds[i] == kind;
    }
    return n;
}

void sim_clear_logs(sim_t *s)
{
    s->n_acks = 0;
    s->n_events = 0;
    s->n_kinds = 0;
    s->reports = 0;
    s->attr_updates = 0;
    s->n_led = 0;
    s->persist_config_calls = 0;
    s->persist_diag_calls = 0;
    s->read_slot_calls = 0;
    s->rejoin_calls = 0;
    s->reboots = 0;
}
