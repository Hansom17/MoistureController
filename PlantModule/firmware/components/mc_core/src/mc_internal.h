#ifndef MC_INTERNAL_H
#define MC_INTERNAL_H

#include <string.h>

#include "mc_core.h"
#include "mc_moisture.h"

/* ---- actions ---- */
mc_action_t *mc_act(mc_actions_t *out, mc_act_kind_t kind);
void mc_arm(mc_actions_t *out, mc_timer_t id, uint8_t arg, uint32_t delay_ms);
void mc_cancel(mc_actions_t *out, mc_timer_t id, uint8_t arg);
void mc_attrs_changed(mc_actions_t *out, bool report_now);

/* ---- messages to the hub (queued while the link is down) ---- */
void mc_msg_ack(mc_core_t *c, mc_actions_t *out, uint32_t cmd_id, uint8_t state, uint8_t reason, uint16_t ends_in_s);
void mc_msg_event(mc_core_t *c, mc_actions_t *out, uint8_t code, uint8_t slot, uint16_t arg);
void mc_msg_flush(mc_core_t *c, mc_actions_t *out);
void mc_set_error(mc_core_t *c, uint16_t code);

/* ---- lifecycle helpers used by the other machines ---- */
void mc_led_update(mc_core_t *c, mc_actions_t *out);
void mc_lifecycle_reboot(mc_core_t *c, mc_actions_t *out, bool clear_crash);

/* ---- sensing machine (mc_sense.c) ---- */
void mc_sense_start(mc_core_t *c, mc_actions_t *out);
void mc_sense_stop(mc_core_t *c, mc_actions_t *out);
void mc_sense_rearm(mc_core_t *c, mc_actions_t *out);
void mc_sense_on_timer(mc_core_t *c, mc_actions_t *out, mc_timer_t id, uint8_t arg);
void mc_sense_on_adc(mc_core_t *c, mc_actions_t *out, uint8_t slot, bool ok, uint16_t raw);
void mc_sense_on_report_result(mc_core_t *c, mc_actions_t *out);
void mc_sense_on_battery(mc_core_t *c, mc_actions_t *out, uint16_t mv);
void mc_readings_refresh_outputs(mc_core_t *c);
void mc_fast_enter(mc_core_t *c, mc_actions_t *out);
void mc_fast_maybe_leave(mc_core_t *c, mc_actions_t *out);

/* ---- command and pump machines (mc_cmd.c) ---- */
void mc_cmd_on_zb(mc_core_t *c, mc_actions_t *out, const mc_cmd_t *cmd);
void mc_cmd_on_timer(mc_core_t *c, mc_actions_t *out, mc_timer_t id, uint8_t arg);
void mc_pumps_force_off(mc_core_t *c, mc_actions_t *out);
void mc_cmd_reset_all(mc_core_t *c);

/* ---- configuration machine (mc_cfg.c) ---- */
void mc_cfg_on_write(mc_core_t *c, mc_actions_t *out, uint16_t attr, const uint8_t *data, uint8_t len);
void mc_cfg_commit(mc_core_t *c, mc_actions_t *out, uint16_t rev);
void mc_cfg_on_timeout(mc_core_t *c, mc_actions_t *out);
void mc_cfg_drop_stage(mc_core_t *c, mc_actions_t *out);

#endif
