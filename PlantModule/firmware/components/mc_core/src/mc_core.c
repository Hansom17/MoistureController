/* Dispatcher and the device lifecycle machine (PlantModule/specs.md 7.3), the outgoing message queue,
 * the LED and the attribute view. The other machines are in mc_sense.c, mc_cmd.c and mc_cfg.c. */
#include "mc_internal.h"

/* ---- actions ----------------------------------------------------------------------------------------- */

mc_action_t *mc_act(mc_actions_t *out, mc_act_kind_t kind)
{
    if (out->n >= MC_MAX_ACTIONS) {
        out->overflow = true;
        return &out->a[MC_MAX_ACTIONS - 1]; /* overwritten: the flag tells the tests */
    }
    mc_action_t *a = &out->a[out->n++];
    memset(a, 0, sizeof *a);
    a->kind = kind;
    return a;
}

void mc_arm(mc_actions_t *out, mc_timer_t id, uint8_t arg, uint32_t delay_ms)
{
    mc_action_t *a = mc_act(out, MC_ACT_ARM_TIMER);
    a->u.timer.id = id;
    a->u.timer.arg = arg;
    a->u.timer.delay_ms = delay_ms;
}

void mc_cancel(mc_actions_t *out, mc_timer_t id, uint8_t arg)
{
    mc_action_t *a = mc_act(out, MC_ACT_CANCEL_TIMER);
    a->u.timer.id = id;
    a->u.timer.arg = arg;
}

void mc_attrs_changed(mc_actions_t *out, bool report_now)
{
    mc_act(out, MC_ACT_UPDATE_ATTRS);
    if (report_now) {
        mc_act(out, MC_ACT_REPORT_NOW);
    }
}

/* ---- messages to the hub ----------------------------------------------------------------------------- */

static void msg_send(mc_actions_t *out, const mc_msg_t *m)
{
    if (m->is_event) {
        mc_action_t *a = mc_act(out, MC_ACT_SEND_EVENT);
        a->u.event.n = m->n;
        a->u.event.code = m->code;
        a->u.event.slot = m->slot;
        a->u.event.arg = m->value;
    } else {
        mc_action_t *a = mc_act(out, MC_ACT_SEND_CMD_ACK);
        a->u.ack.n = m->n;
        a->u.ack.cmd_id = m->cmd_id;
        a->u.ack.state = m->state;
        a->u.ack.reason = m->reason;
        a->u.ack.ends_in_s = m->value;
    }
}

/* Sent at once when the link is up, otherwise kept in RAM (up to 8, the oldest is dropped). */
static void msg_put(mc_core_t *c, mc_actions_t *out, const mc_msg_t *m)
{
    if (c->link_up) {
        msg_send(out, m);
        return;
    }
    if (c->pending_n == MC_MAX_PENDING_MSGS) {
        memmove(&c->pending[0], &c->pending[1], sizeof c->pending[0] * (MC_MAX_PENDING_MSGS - 1));
        c->pending_n--;
    }
    c->pending[c->pending_n++] = *m;
}

void mc_msg_ack(mc_core_t *c, mc_actions_t *out, uint32_t cmd_id, uint8_t state, uint8_t reason, uint16_t ends_in_s)
{
    mc_msg_t m = {.is_event = false, .n = ++c->ack_n, .cmd_id = cmd_id, .state = state, .reason = reason,
                  .value = ends_in_s};
    msg_put(c, out, &m);
}

void mc_msg_event(mc_core_t *c, mc_actions_t *out, uint8_t code, uint8_t slot, uint16_t arg)
{
    mc_msg_t m = {.is_event = true, .n = ++c->event_n, .code = code, .slot = slot, .value = arg};
    msg_put(c, out, &m);
}

void mc_msg_flush(mc_core_t *c, mc_actions_t *out)
{
    for (uint8_t i = 0; i < c->pending_n; i++) {
        msg_send(out, &c->pending[i]);
    }
    c->pending_n = 0;
}

void mc_set_error(mc_core_t *c, uint16_t code)
{
    c->diag.last_error = code;
}

/* ---- LED --------------------------------------------------------------------------------------------- */

static mc_led_t base_led(const mc_core_t *c)
{
    switch (c->lc) {
    case MC_LC_UNPROVISIONED:
        return MC_LED_SLOW_BLINK;
    case MC_LC_STEERING:
    case MC_LC_INTERVIEWING:
        return MC_LED_FAST_BLINK;
    case MC_LC_OPERATIONAL:
        return MC_LED_SOLID;
    case MC_LC_REJOINING:
        return MC_LED_DOUBLE_BLINK;
    case MC_LC_SAFE_MODE:
        return MC_LED_TRIPLE_BLINK;
    default:
        return MC_LED_OFF;
    }
}

void mc_led_update(mc_core_t *c, mc_actions_t *out)
{
    mc_led_t want = c->identify ? MC_LED_IDENTIFY : c->cue ? MC_LED_FAST_BLINK : base_led(c);
    if (want != c->led) {
        c->led = want;
        mc_act(out, MC_ACT_SET_LED)->u.led = want;
    }
}

/* ---- attribute view ---------------------------------------------------------------------------------- */

void mc_core_attrs(const mc_core_t *c, mc_attrs_t *a)
{
    memset(a, 0, sizeof *a);
    a->seq = c->seq;
    a->boot_id = c->boot_id;
    memcpy(a->readings, c->readings, sizeof a->readings);
    a->status = c->lc == MC_LC_SAFE_MODE ? MC_STATUS_SAFE_MODE
                : c->lc == MC_LC_INTERVIEWING ? MC_STATUS_INTERVIEWING
                                              : MC_STATUS_OPERATIONAL;
    a->fast_mode = c->fast;
    a->safe_reason = c->safe_reason;
    a->cfg_rev = c->cfg.rev;
    a->cfg_result = c->cfg_result;
    a->cfg_error = c->cfg_error;
    a->boot_reason = c->boot_reason;
    a->reset_count = c->diag.reset_count;
    a->rejoin_count = c->diag.rejoin_count;
    a->last_error = c->diag.last_error;
    a->voltage_mv = c->voltage_mv;
}

void mc_encode_slot_reading(const mc_reading_t *r, uint8_t out[8])
{
    out[0] = r->type;
    out[1] = r->error;
    out[2] = (uint8_t)((uint16_t)r->value & 0xFF);
    out[3] = (uint8_t)((uint16_t)r->value >> 8);
    out[4] = (uint8_t)(r->raw & 0xFF);
    out[5] = (uint8_t)(r->raw >> 8);
    out[6] = (uint8_t)(r->cfg_rev & 0xFF);
    out[7] = (uint8_t)(r->cfg_rev >> 8);
}

bool mc_core_pump_running(const mc_core_t *c)
{
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        if (c->pump[i].state == MC_PUMP_ON) {
            return true;
        }
    }
    return false;
}

/* ---- lifecycle --------------------------------------------------------------------------------------- */

void mc_core_init(mc_core_t *c, const mc_board_t *board, uint16_t adc_max)
{
    memset(c, 0, sizeof *c);
    c->board = board;
    c->adc_max = adc_max;
    c->lc = MC_LC_BOOT;
    c->led = MC_LED_OFF;
    mc_config_default(&c->cfg);
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        c->readings[i].value = MC_VALUE_UNKNOWN;
    }
}

static void persist_diag(mc_actions_t *out)
{
    mc_act(out, MC_ACT_PERSIST_DIAG);
}

static void outputs_off(mc_core_t *c, mc_actions_t *out)
{
    mc_pumps_force_off(c, out);
    mc_act(out, MC_ACT_ALL_OUTPUTS_OFF);
}

/* Everything the machines of the operational container do stops (a lifecycle exit, 7.1). */
static void stop_operational(mc_core_t *c, mc_actions_t *out)
{
    outputs_off(c, out);
    mc_sense_stop(c, out);
    mc_cfg_drop_stage(c, out);
}

static void link_up(mc_core_t *c, mc_actions_t *out)
{
    c->joined = true;
    c->link_up = true;
    mc_msg_flush(c, out);
}

static void enter_safe_mode(mc_core_t *c, mc_actions_t *out, uint8_t reason)
{
    stop_operational(c, out);
    c->lc = MC_LC_SAFE_MODE;
    c->safe_reason = reason;
    mc_msg_event(c, out, MC_EVENT_CODE_SAFE_MODE, MC_SLOT_NONE, reason);
    mc_attrs_changed(out, c->link_up);
    mc_led_update(c, out);
}

static void enter_unprovisioned(mc_core_t *c, mc_actions_t *out)
{
    c->lc = MC_LC_UNPROVISIONED;
    c->link_up = false;
    c->joined = false;
    mc_led_update(c, out);
}

static void enter_steering(mc_core_t *c, mc_actions_t *out)
{
    c->lc = MC_LC_STEERING;
    mc_act(out, MC_ACT_START_STEERING);
    mc_arm(out, MC_TIMER_STEERING, 0, MC_STEERING_TIMEOUT_MS);
    mc_led_update(c, out);
}

static void enter_interviewing(mc_core_t *c, mc_actions_t *out)
{
    mc_cancel(out, MC_TIMER_STEERING, 0);
    c->lc = MC_LC_INTERVIEWING;
    mc_arm(out, MC_TIMER_INTERVIEW, 0, MC_INTERVIEW_TIMEOUT_MS);
    link_up(c, out);
    mc_sense_start(c, out);
    mc_attrs_changed(out, true);
    mc_led_update(c, out);
}

static void enter_operational(mc_core_t *c, mc_actions_t *out)
{
    mc_cancel(out, MC_TIMER_INTERVIEW, 0);
    mc_cancel(out, MC_TIMER_REJOIN, 0);
    c->lc = MC_LC_OPERATIONAL;
    c->rejoin_attempt = 0;
    link_up(c, out);
    mc_sense_start(c, out);
    mc_attrs_changed(out, true);
    mc_led_update(c, out);
}

static uint32_t rejoin_delay_ms(uint8_t attempt)
{
    uint32_t d = MC_REJOIN_FIRST_MS;
    for (uint8_t i = 0; i < attempt && d < MC_REJOIN_MAX_MS; i++) {
        d *= 2;
    }
    return d > MC_REJOIN_MAX_MS ? MC_REJOIN_MAX_MS : d;
}

static void rejoin_attempt(mc_core_t *c, mc_actions_t *out)
{
    mc_act(out, MC_ACT_REJOIN);
    mc_arm(out, MC_TIMER_REJOIN, 0, rejoin_delay_ms(c->rejoin_attempt));
    if (c->rejoin_attempt < 255) {
        c->rejoin_attempt++;
    }
}

static void enter_rejoining(mc_core_t *c, mc_actions_t *out)
{
    c->lc = MC_LC_REJOINING;
    c->link_up = false;
    c->rejoin_attempt = 0;
    rejoin_attempt(c, out);
    mc_led_update(c, out);
}

static void enter_factory_reset(mc_core_t *c, mc_actions_t *out)
{
    stop_operational(c, out);
    c->lc = MC_LC_FACTORY_RESET;
    c->link_up = false;
    mc_act(out, MC_ACT_LEAVE_NETWORK);
    mc_act(out, MC_ACT_ERASE_STATE);
    mc_act(out, MC_ACT_REBOOT);
    mc_led_update(c, out);
}

/* The coordinator told the module to leave: configuration and network state go (7.3). */
static void left_network(mc_core_t *c, mc_actions_t *out)
{
    stop_operational(c, out);
    mc_act(out, MC_ACT_ERASE_STATE);
    mc_config_default(&c->cfg);
    c->cfg_result = MC_CFG_RESULT_OK;
    c->cfg_error = 0;
    c->pending_n = 0;
    mc_cmd_reset_all(c);
    if (c->lc == MC_LC_SAFE_MODE) {
        c->joined = false;
        c->link_up = false;
        return;
    }
    enter_unprovisioned(c, out);
}

static void on_boot(mc_core_t *c, mc_actions_t *out, const mc_boot_t *b)
{
    c->boot_reason = b->reset_reason;
    c->first_boot = b->first_boot;
    c->boot_id = b->boot_id;
    c->diag.reset_count = (uint16_t)(b->reset_count_stored + 1);
    c->diag.rejoin_count = b->rejoin_count_stored;
    c->diag.last_error = b->last_error_stored;

    bool unexpected = b->reset_reason == MC_BOOT_REASON_PANIC || b->reset_reason == MC_BOOT_REASON_WATCHDOG ||
                      b->reset_reason == MC_BOOT_REASON_BROWNOUT;
    if (b->reset_reason == MC_BOOT_REASON_POWER_ON) {
        c->diag.crash_count = 0;
    } else if (unexpected) {
        c->diag.crash_count = (uint8_t)(b->crash_count_stored + 1);
    } else {
        c->diag.crash_count = b->crash_count_stored;
    }
    persist_diag(out);

    mc_act(out, MC_ACT_ALL_OUTPUTS_OFF); /* outputs come up off after any reset */
    if (b->config_valid) {
        c->cfg = b->config;
    } else {
        mc_config_default(&c->cfg);
        mc_set_error(c, MC_ERR_CONFIG_STORED_INVALID);
        mc_msg_event(c, out, MC_EVENT_CODE_CONFIG_REJECTED, MC_SLOT_NONE, MC_CFG_ERROR_SCHEMA_UNKNOWN);
    }
    mc_msg_event(c, out, MC_EVENT_CODE_BOOT, MC_SLOT_NONE, b->reset_reason);

    if (!b->factory_valid) {
        mc_act(out, MC_ACT_START_ZIGBEE);
        enter_safe_mode(c, out, MC_SAFE_REASON_FACTORY_INVALID);
    } else if (c->board == NULL) {
        mc_act(out, MC_ACT_START_ZIGBEE);
        enter_safe_mode(c, out, MC_SAFE_REASON_BOARD_UNKNOWN);
    } else if (c->diag.crash_count >= MC_CRASH_LOOP_COUNT) {
        mc_act(out, MC_ACT_START_ZIGBEE);
        enter_safe_mode(c, out, MC_SAFE_REASON_CRASH_LOOP);
    } else {
        c->lc = MC_LC_STACK_STARTING;
        mc_act(out, MC_ACT_START_ZIGBEE);
        mc_arm(out, MC_TIMER_ZB_START, 0, MC_ZB_START_TIMEOUT_MS);
        mc_arm(out, MC_TIMER_STABLE, 0, MC_STABLE_MS);
    }
}

static void on_stack_ready(mc_core_t *c, mc_actions_t *out, bool joined)
{
    if (c->lc == MC_LC_SAFE_MODE) {
        if (joined) {
            link_up(c, out);
            mc_attrs_changed(out, true);
        }
        return;
    }
    if (c->lc != MC_LC_STACK_STARTING) {
        return;
    }
    mc_cancel(out, MC_TIMER_ZB_START, 0);
    if (joined) {
        enter_operational(c, out);
    } else if (c->first_boot) {
        enter_steering(c, out);
    } else {
        enter_unprovisioned(c, out);
    }
}

static void on_timer(mc_core_t *c, mc_actions_t *out, mc_timer_t id, uint8_t arg)
{
    switch (id) {
    case MC_TIMER_ZB_START:
        if (c->lc == MC_LC_STACK_STARTING) {
            mc_set_error(c, MC_ERR_ZIGBEE_START);
            persist_diag(out);
            mc_act(out, MC_ACT_REBOOT);
        }
        break;
    case MC_TIMER_STEERING:
        if (c->lc == MC_LC_STEERING) {
            enter_unprovisioned(c, out);
        }
        break;
    case MC_TIMER_INTERVIEW:
        if (c->lc == MC_LC_INTERVIEWING) {
            enter_operational(c, out);
        }
        break;
    case MC_TIMER_REJOIN:
        if (c->lc == MC_LC_REJOINING) {
            rejoin_attempt(c, out);
        }
        break;
    case MC_TIMER_STABLE:
        c->diag.crash_count = 0;
        persist_diag(out);
        break;
    case MC_TIMER_IDENTIFY:
        c->identify = false;
        mc_led_update(c, out);
        break;
    case MC_TIMER_CFG_TXN:
        mc_cfg_on_timeout(c, out);
        break;
    case MC_TIMER_PUMP_END:
    case MC_TIMER_PUMP_PAUSE:
        mc_cmd_on_timer(c, out, id, arg);
        break;
    default:
        mc_sense_on_timer(c, out, id, arg);
        break;
    }
}

static bool provisioned_state(const mc_core_t *c)
{
    return c->lc == MC_LC_INTERVIEWING || c->lc == MC_LC_OPERATIONAL || c->lc == MC_LC_REJOINING;
}

static void on_button(mc_core_t *c, mc_actions_t *out, mc_ev_kind_t kind)
{
    switch (kind) {
    case MC_EV_BTN_SHORT:
        if (c->lc == MC_LC_BOOT || c->lc == MC_LC_STACK_STARTING || c->lc == MC_LC_FACTORY_RESET) {
            break;
        }
        c->identify = true;
        mc_arm(out, MC_TIMER_IDENTIFY, 0, MC_IDENTIFY_MS);
        mc_led_update(c, out);
        if (c->link_up) {
            mc_attrs_changed(out, true);
        }
        break;
    case MC_EV_BTN_HOLD_3S:
        if (c->lc == MC_LC_UNPROVISIONED) {
            enter_steering(c, out);
        } else if (c->lc == MC_LC_OPERATIONAL || c->lc == MC_LC_REJOINING || c->lc == MC_LC_INTERVIEWING) {
            c->cue = true; /* only the "keep holding" cue on a joined module */
            mc_led_update(c, out);
        }
        break;
    case MC_EV_BTN_HOLD_10S:
        if (c->lc == MC_LC_UNPROVISIONED || c->lc == MC_LC_STEERING || provisioned_state(c) ||
            c->lc == MC_LC_SAFE_MODE) {
            c->cue = false;
            enter_factory_reset(c, out);
        }
        break;
    default: /* MC_EV_BTN_RELEASE */
        c->cue = false;
        mc_led_update(c, out);
        break;
    }
}

void mc_core_step(mc_core_t *c, const mc_event_t *ev, mc_actions_t *out)
{
    out->n = 0;
    out->overflow = false;
    c->now_ms = ev->now_ms;

    switch (ev->kind) {
    case MC_EV_BOOT:
        on_boot(c, out, &ev->u.boot);
        break;
    case MC_EV_CRASH_LOOP:
        if (c->lc != MC_LC_BOOT && c->lc != MC_LC_FACTORY_RESET && c->lc != MC_LC_SAFE_MODE) {
            enter_safe_mode(c, out, MC_SAFE_REASON_CRASH_LOOP);
        }
        break;
    case MC_EV_ZB_STACK_READY:
        on_stack_ready(c, out, ev->u.joined);
        break;
    case MC_EV_ZB_STEERING_DONE:
        break; /* the steering timeout is the only way out of Steering besides a join */
    case MC_EV_ZB_JOINED:
        if (c->lc == MC_LC_STEERING) {
            enter_interviewing(c, out);
        }
        break;
    case MC_EV_ZB_CONFIGURED:
        if (c->lc == MC_LC_INTERVIEWING) {
            enter_operational(c, out);
        }
        break;
    case MC_EV_ZB_PARENT_LOST:
        if (c->lc == MC_LC_OPERATIONAL || c->lc == MC_LC_INTERVIEWING) {
            mc_cancel(out, MC_TIMER_INTERVIEW, 0);
            enter_rejoining(c, out);
        } else if (c->lc == MC_LC_SAFE_MODE && c->joined) {
            c->link_up = false;
        }
        break;
    case MC_EV_ZB_REJOIN_DONE:
        if (c->lc == MC_LC_REJOINING && ev->u.ok) {
            c->diag.rejoin_count++;
            persist_diag(out);
            enter_operational(c, out);
        } else if (c->lc == MC_LC_SAFE_MODE && ev->u.ok) {
            link_up(c, out);
        }
        break;
    case MC_EV_ZB_LEFT:
        if (provisioned_state(c) || c->lc == MC_LC_SAFE_MODE || c->lc == MC_LC_STEERING) {
            left_network(c, out);
        }
        break;
    case MC_EV_ZB_ATTR_WRITE:
        mc_cfg_on_write(c, out, ev->u.write.attr, ev->u.write.data, ev->u.write.len);
        break;
    case MC_EV_ZB_CMD:
        mc_cmd_on_zb(c, out, &ev->u.cmd);
        break;
    case MC_EV_ZB_REPORT_RESULT:
        mc_sense_on_report_result(c, out);
        break;
    case MC_EV_TIMER:
        on_timer(c, out, ev->u.timer.id, ev->u.timer.arg);
        break;
    case MC_EV_ADC_DONE:
        mc_sense_on_adc(c, out, ev->u.adc.slot, ev->u.adc.ok, ev->u.adc.raw);
        break;
    case MC_EV_BTN_SHORT:
    case MC_EV_BTN_HOLD_3S:
    case MC_EV_BTN_HOLD_10S:
    case MC_EV_BTN_RELEASE:
        on_button(c, out, ev->kind);
        break;
    case MC_EV_BATT_SAMPLE:
        mc_sense_on_battery(c, out, ev->u.mv);
        break;
    }
}

/* Used by the command machine: device_action clear_safe_mode and reboot. */
void mc_lifecycle_reboot(mc_core_t *c, mc_actions_t *out, bool clear_crash)
{
    if (clear_crash) {
        c->diag.crash_count = 0;
        persist_diag(out);
    }
    outputs_off(c, out);
    mc_act(out, MC_ACT_REBOOT);
}
