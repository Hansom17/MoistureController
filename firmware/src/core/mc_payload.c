#include "mc_payload.h"

const char *mc_wake_name(enum mc_wake w)
{
	switch (w) {
	case MC_WAKE_TIMER: return "timer";
	case MC_WAKE_PUMP_STOP: return "pump_stop";
	case MC_WAKE_BUTTON: return "button";
	case MC_WAKE_POWER_ON: return "power_on";
	case MC_WAKE_RESET: return "reset";
	}
	return "reset";
}

static int status(char *buf, size_t cap, const char *state, const char *key1, int64_t v1,
		  bool str_fw, uint32_t boot)
{
	struct mc_jw w;

	mc_jw_init(&w, buf, cap);
	mc_jw_obj(&w);
	mc_jw_kv_str(&w, "state", state);
	if (key1 != NULL) {
		mc_jw_kv_int(&w, key1, v1);
	}
	if (str_fw) {
		mc_jw_kv_str(&w, "fw", MC_FW_VERSION);
		mc_jw_kv_int(&w, "boot", boot);
	}
	mc_jw_end_obj(&w);
	return mc_jw_finish(&w);
}

int mc_enc_status_online(char *buf, size_t cap, uint32_t boot)
{
	return status(buf, cap, "online", NULL, 0, true, boot);
}

int mc_enc_status_sleeping(char *buf, size_t cap, int32_t next_wake_s)
{
	return status(buf, cap, "sleeping", "next_wake_s", next_wake_s, false, 0);
}

int mc_enc_status_offline(char *buf, size_t cap)
{
	return status(buf, cap, "offline", NULL, 0, false, 0);
}

int mc_enc_status_service(char *buf, size_t cap, int32_t until_s)
{
	return status(buf, cap, "service", "until_s", until_s, false, 0);
}

int mc_enc_telemetry(char *buf, size_t cap, const struct mc_tel *t)
{
	struct mc_jw w;

	mc_jw_init(&w, buf, cap);
	mc_jw_obj(&w);
	mc_jw_kv_int(&w, "seq", t->seq);
	if (t->ts > 0) {
		mc_jw_kv_int(&w, "ts", t->ts);
	}
	mc_jw_kv_int(&w, "cfg_rev", t->cfg_rev);
	mc_jw_key(&w, "readings");
	mc_jw_arr(&w);
	for (int i = 0; i < t->n; i++) {
		const struct mc_reading *r = &t->r[i];

		mc_jw_obj(&w);
		mc_jw_kv_int(&w, "slot", r->slot);
		mc_jw_kv_str(&w, "type", mc_type_name(r->type));
		if (r->has_value) {
			mc_jw_key(&w, "value");
			mc_jw_dec1(&w, r->value_x10);
			mc_jw_kv_str(&w, "unit", mc_type_unit(r->type));
		}
		if (r->err != MC_SENSOR_OK) {
			mc_jw_kv_str(&w, "error", mc_sensor_err_name(r->err));
		}
		if (r->has_raw) {
			mc_jw_kv_int(&w, "raw", r->raw);
		}
		mc_jw_end_obj(&w);
	}
	mc_jw_end_arr(&w);
	mc_jw_key(&w, "health");
	mc_jw_obj(&w);
	mc_jw_kv_int(&w, "batt_mv", t->h.batt_mv);
	mc_jw_kv_int(&w, "rssi", t->h.rssi);
	mc_jw_kv_str(&w, "wake", mc_wake_name(t->h.wake));
	if (t->h.cycle_ms >= 0) {
		mc_jw_kv_int(&w, "cycle_ms", t->h.cycle_ms);
	}
	if (t->h.wifi_ms >= 0) {
		mc_jw_kv_int(&w, "wifi_ms", t->h.wifi_ms);
	}
	mc_jw_end_obj(&w);
	mc_jw_end_obj(&w);
	return mc_jw_finish(&w);
}

static const char *event_name(enum mc_event_kind k)
{
	switch (k) {
	case MC_EV_BOOT: return "boot";
	case MC_EV_SAFETY_STOP: return "safety_stop";
	case MC_EV_SENSOR_FAULT: return "sensor_fault";
	case MC_EV_LOW_BATTERY: return "low_battery";
	case MC_EV_CONFIG_ERROR: return "config_error";
	case MC_EV_SERVICE_MODE: return "service_mode";
	}
	return "boot";
}

int mc_enc_event(char *buf, size_t cap, const struct mc_event *e)
{
	struct mc_jw w;

	mc_jw_init(&w, buf, cap);
	mc_jw_obj(&w);
	mc_jw_kv_int(&w, "seq", e->seq);
	if (e->ts > 0) {
		mc_jw_kv_int(&w, "ts", e->ts);
	}
	mc_jw_kv_str(&w, "kind", event_name(e->kind));
	if (e->slot >= 0) {
		mc_jw_kv_int(&w, "slot", e->slot);
	}
	if (e->detail[0] != '\0') {
		mc_jw_kv_str(&w, "detail", e->detail);
	}
	mc_jw_end_obj(&w);
	return mc_jw_finish(&w);
}

int mc_enc_ack(char *buf, size_t cap, const struct mc_ack *a)
{
	struct mc_jw w;

	mc_jw_init(&w, buf, cap);
	mc_jw_obj(&w);
	mc_jw_kv_str(&w, "id", a->id);
	mc_jw_kv_str(&w, "status", mc_ack_status_name(a->status));
	if (a->reason[0] != '\0') {
		mc_jw_kv_str(&w, "reason", a->reason);
	}
	if (a->ts > 0) {
		mc_jw_kv_int(&w, "ts", a->ts);
	}
	if (a->ends_at > 0) {
		mc_jw_kv_int(&w, "ends_at", a->ends_at);
	}
	mc_jw_end_obj(&w);
	return mc_jw_finish(&w);
}

int mc_enc_config_state(char *buf, size_t cap, const struct mc_config *cfg,
			enum mc_cfg_result result, int32_t rejected_rev,
			const struct mc_error *err)
{
	static const char *const names[] = {"applied", "rejected", "boot"};
	struct mc_jw w;

	mc_jw_init(&w, buf, cap);
	mc_jw_obj(&w);
	mc_jw_kv_int(&w, "rev", cfg->rev);
	mc_jw_kv_str(&w, "result", names[result]);
	if (result == MC_CFG_REJECTED) {
		mc_jw_kv_int(&w, "rejected_rev", rejected_rev);
		mc_jw_key(&w, "error");
		mc_jw_obj(&w);
		if (err->slot >= 0) {
			mc_jw_kv_int(&w, "slot", err->slot);
		}
		mc_jw_kv_str(&w, "code", err->code);
		if (err->detail[0] != '\0') {
			mc_jw_kv_str(&w, "detail", err->detail);
		}
		mc_jw_end_obj(&w);
	}
	mc_config_write_body(&w, cfg);
	mc_jw_key(&w, "detected"); /* auto-detect (I2C scan, 1-Wire search) is not implemented yet */
	mc_jw_arr(&w);
	mc_jw_end_arr(&w);
	mc_jw_key(&w, "limits");
	mc_jw_obj(&w);
	mc_jw_kv_int(&w, "max_run_s_hard", MC_MAX_RUN_S_HARD);
	mc_jw_kv_int(&w, "slots_max", MC_SLOTS_MAX);
	mc_jw_end_obj(&w);
	mc_jw_end_obj(&w);
	return mc_jw_finish(&w);
}
