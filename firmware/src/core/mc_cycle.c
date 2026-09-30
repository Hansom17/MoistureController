#include "mc_cycle.h"

#include <string.h>
#include <zephyr/sys/util.h>

#include "mc_pins.h"

#define MAX_PAYLOAD_IN 1024   /* mqtt.md §9: server -> device */
#define MAX_PAYLOAD_OUT 2048  /* device -> server */
#define MAX_EVENTS 4

struct inbox {
	char desired[MAX_PAYLOAD_IN + 1];
	bool has_desired;
	struct mc_cmd cmds[MC_CMD_BATCH_MAX];
	size_t n_cmds;
};

static struct inbox inbox;
static char out[MAX_PAYLOAD_OUT];

/* --- helpers ---------------------------------------------------------------------------------- */

static void say(struct mc_app *a, const char *msg)
{
	if (a->io->log) {
		a->io->log(a->io_user, msg);
	}
}

static int64_t now_s(const struct mc_app *a)
{
	if (a->clock_base_s <= 0) {
		return 0;
	}
	return a->clock_base_s + a->io->uptime_ms(a->io_user) / 1000;
}

static void update_ctx_time(struct mc_app *a)
{
	a->ctx.now = now_s(a);
	a->ctx.time_synced = a->clock_base_s > 0;
}

static bool pub(struct mc_app *a, const char *suffix, int len, bool retain)
{
	if (len < 0) {
		say(a, "payload too large, dropped");
		return true; /* a message that can never be sent must not block the queue */
	}
	return a->io->publish(a->io_user, suffix, out, (size_t)len, retain) == 0;
}

static bool flush_acks(struct mc_app *a)
{
	while (a->rtc->pend_n) {
		int n = mc_enc_ack(out, sizeof(out), &a->rtc->pend[0]);

		if (!pub(a, "cmd/ack", n, false)) {
			return false;
		}
		mc_pend_drop_first(a->rtc);
	}
	return true;
}

static bool flush_telemetry(struct mc_app *a)
{
	const struct mc_tel *t;

	while ((t = mc_tbuf_oldest(a->rtc)) != NULL) {
		int n = mc_enc_telemetry(out, sizeof(out), t);

		if (!pub(a, "telemetry", n, false)) {
			return false;
		}
		mc_tbuf_drop_oldest(a->rtc);
	}
	return true;
}

/* --- pumps ------------------------------------------------------------------------------------------ */

static void pump_off(struct mc_app *a, const struct mc_slot *s)
{
	a->io->pump_set(a->io_user, s, false, false);
}

/* A held run whose time has come is switched off first thing (before any network). */
static void stop_due_pumps(struct mc_app *a)
{
	int slot;

	while ((slot = mc_pump_due_stop(&a->ctx)) >= 0) {
		const struct mc_slot *s = mc_config_slot(a->ctx.cfg, slot);
		struct mc_ack ack;

		if (s != NULL) {
			pump_off(a, s);
		}
		if (mc_pump_end_hold(&a->ctx.pump[slot], a->ctx.now, MC_ACK_DONE, &ack)) {
			mc_hist_put(a->ctx.hist, ack.id, &ack);
			mc_pend_push(a->rtc, &ack);
		}
	}
	/* Nothing may stay on unless a hold says so (after a crash or a config change). */
	for (int i = 0; i < a->ctx.cfg->n; i++) {
		const struct mc_slot *s = &a->ctx.cfg->slots[i];
		const struct mc_module_info *m = mc_module_info(s->module);

		if (m && m->actuator && a->ctx.pump[s->slot].run_ends_at == 0) {
			pump_off(a, s);
		}
	}
}

/* --- sensors and telemetry ------------------------------------------------------------------------- */

struct fault_event {
	uint8_t slot;
};

static void read_sensors(struct mc_app *a, struct mc_tel *t, struct fault_event *faults,
			 size_t *n_faults)
{
	const struct mc_config *cfg = &a->cfg;

	t->n = 0;
	for (int i = 0; i < cfg->n && t->n < MC_SLOTS_MAX; i++) {
		const struct mc_slot *s = &cfg->slots[i];
		const struct mc_module_info *m = mc_module_info(s->module);
		struct mc_reading *r = &t->r[t->n];

		if (m == NULL || m->actuator) {
			continue;
		}
		memset(r, 0, sizeof(*r));
		r->slot = s->slot;
		if (mc_module_is_moisture(s->module)) {
			int32_t raw = 0;

			if (a->io->read_adc(a->io_user, s, &raw) < 0) {
				r->type = MC_TYPE_SOIL_MOISTURE;
				r->err = MC_SENSOR_BUS_ERROR;
			} else {
				mc_moisture_reading(s, raw, r);
			}
		} else {
			/* Drivers for 1-Wire, I2C and float switches come later (Firmware_Specs phase 3). */
			r->type = s->module == MC_MOD_WATER_LEVEL_FLOAT ? MC_TYPE_WATER_LEVEL_OK
								       : MC_TYPE_TEMPERATURE;
			r->err = MC_SENSOR_NOT_FOUND;
		}
		/* one sensor_fault event per transition ok -> error, recovery is silent */
		if (r->err != MC_SENSOR_OK && a->rtc->sensor_ok[s->slot] && *n_faults < MAX_EVENTS) {
			faults[(*n_faults)++].slot = s->slot;
		} else if (r->err == MC_SENSOR_OK) {
			a->rtc->sensor_ok[s->slot] = true;
		}
		t->n++;
	}
}

/* --- config ------------------------------------------------------------------------------------------ */

static void publish_config_state(struct mc_app *a, enum mc_cfg_result result,
				 int32_t rejected_rev, const struct mc_error *err)
{
	int n = mc_enc_config_state(out, sizeof(out), &a->cfg, result, rejected_rev, err);

	if (pub(a, "config/state", n, true)) {
		a->rtc->cfg_rev_published = a->cfg.rev;
	}
}

static void apply_desired(struct mc_app *a)
{
	struct mc_config next;
	struct mc_error err = {.slot = -1, .code = "out_of_range"};

	if (!inbox.has_desired) {
		return;
	}
	inbox.has_desired = false;

	if (!mc_config_parse(inbox.desired, strlen(inbox.desired), &next, &err)) {
		say(a, "config/desired unusable, ignored");
		return;
	}
	if (next.rev <= a->cfg.rev) {
		return; /* duplicate or old */
	}
	if (!mc_config_validate(&next, &err)) {
		say(a, "config rejected");
		publish_config_state(a, MC_CFG_REJECTED, next.rev, &err);
		return;
	}
	/* Nothing runs across a config change. */
	for (int i = 0; i < a->cfg.n; i++) {
		const struct mc_slot *s = &a->cfg.slots[i];
		const struct mc_module_info *m = mc_module_info(s->module);

		if (m && m->actuator) {
			struct mc_ack ack;

			pump_off(a, s);
			if (mc_pump_end_hold(&a->ctx.pump[s->slot], a->ctx.now, MC_ACK_CANCELLED, &ack)) {
				mc_hist_put(a->ctx.hist, ack.id, &ack);
				mc_pend_push(a->rtc, &ack);
			}
		}
	}
	if (a->io->save_config(a->io_user, &next) < 0) {
		struct mc_error e = {.slot = -1, .code = "out_of_range"};

		strcpy(e.detail, "could not store the config");
		say(a, "saving the config failed");
		publish_config_state(a, MC_CFG_REJECTED, next.rev, &e);
		return;
	}
	a->cfg = next;
	a->ctx.cfg = &a->cfg;
	publish_config_state(a, MC_CFG_APPLIED, 0, NULL);
}

/* --- commands -------------------------------------------------------------------------------------------- */

static void exec_cmd(struct mc_ctx *ctx, const struct mc_cmd *cmd, struct mc_outcome *o,
		     void *user)
{
	struct mc_app *a = user;
	const struct mc_slot *s = o->slot >= 0 ? mc_config_slot(ctx->cfg, o->slot) : NULL;

	update_ctx_time(a);
	switch (o->action) {
	case MC_DO_PUMP_RUN: {
		int64_t ends = ctx->now + o->value;

		/* Only RTC pins keep their level in deep sleep; on any other pin the device stays awake. */
		if (mc_pump_run_is_inline(o->value) || !mc_pin_rtc_capable(s->pin)) {
			a->io->pump_set(a->io_user, s, true, false);
			a->io->delay_ms(a->io_user, o->value * 1000);
			pump_off(a, s);
			update_ctx_time(a);
			mc_pump_finish(&ctx->pump[o->slot], ctx->now);
			o->ack.ts = ctx->now;
		} else { /* keep it on through deep sleep, wake at the end to switch off */
			a->io->pump_set(a->io_user, s, true, true);
			mc_pump_begin_hold(&ctx->pump[o->slot], cmd->id, ends);
			o->ack.status = MC_ACK_RUNNING;
			o->ack.ts = 0;
			o->ack.ends_at = ends;
		}
		break;
	}
	case MC_DO_PUMP_STOP: {
		struct mc_ack held;

		pump_off(a, s);
		if (mc_pump_end_hold(&ctx->pump[o->slot], ctx->now, MC_ACK_CANCELLED, &held)) {
			mc_hist_put(ctx->hist, held.id, &held);
			mc_pend_push(a->rtc, &held);
		}
		break;
	}
	case MC_DO_IDENTIFY:
		a->io->identify(a->io_user, o->value);
		break;
	case MC_DO_SERVICE:
		a->service_until = ctx->now + (int64_t)o->value * 60;
		break;
	case MC_DO_REBOOT:
		a->reboot = true;
		break;
	case MC_DO_NONE:
		break;
	}
	mc_pend_push(a->rtc, &o->ack);
}

static void run_commands(struct mc_app *a)
{
	if (inbox.n_cmds == 0) {
		return;
	}
	update_ctx_time(a);
	mc_cmd_process(&a->ctx, inbox.cmds, inbox.n_cmds, exec_cmd, a);
	inbox.n_cmds = 0;
}

static void on_incoming(void *user, enum mc_in_kind kind, const uint8_t *p, size_t len)
{
	struct mc_app *a = user;
	char buf[MAX_PAYLOAD_IN + 1];

	if (len == 0 || len > MAX_PAYLOAD_IN) {
		return; /* an empty retained payload clears; oversized ones are not ours */
	}
	if (kind == MC_IN_CONFIG) {
		memcpy(inbox.desired, p, len);
		inbox.desired[len] = '\0';
		inbox.has_desired = true; /* the last one wins */
		return;
	}
	if (inbox.n_cmds >= MC_CMD_BATCH_MAX) {
		say(a, "too many commands at once, the rest is dropped");
		return;
	}
	memcpy(buf, p, len);
	buf[len] = '\0';
	if (!mc_cmd_parse(buf, len, &inbox.cmds[inbox.n_cmds])) {
		say(a, "command without a usable id, dropped");
		return;
	}
	inbox.n_cmds++;
}

/* --- start ------------------------------------------------------------------------------------------------- */

void mc_app_begin(struct mc_app *a, struct mc_rtc *rtc, const struct mc_io *io, void *io_user,
		  enum mc_wake wake, enum mc_cfg_load cfg)
{
	a->rtc = rtc;
	a->io = io;
	a->io_user = io_user;
	a->wake = wake;
	a->next_wake_s = MC_WAKE_INTERVAL_DEFAULT_S;
	a->reboot = false;
	a->service_until = 0;
	a->service_request_s = 0;
	a->cold_boot = !mc_rtc_valid(rtc);
	if (a->cold_boot) {
		mc_rtc_init(rtc);
	}
	if (cfg != MC_CFG_LOADED) {
		mc_config_init(&a->cfg);
	}
	a->config_invalid_at_boot = cfg == MC_CFG_CORRUPT;
	/* The clock carries on from when we went to sleep (RTC timer), if we know it. */
	a->clock_base_s = (!a->cold_boot && rtc->wall_at_sleep > 0)
				  ? rtc->wall_at_sleep + rtc->slept_s
				  : 0;
	rtc->boot++;

	memset(&a->ctx, 0, sizeof(a->ctx));
	a->ctx.cfg = &a->cfg;
	a->ctx.hist = &rtc->hist;
	memcpy(a->ctx.pump, rtc->pump, sizeof(a->ctx.pump));
	update_ctx_time(a);
}

/* --- the cycle ------------------------------------------------------------------------------------------------- */

/* Service mode (mqtt.md §4.1 `service`): awake and reachable until `service_until`. */
static bool service_mode(struct mc_app *a)
{
	struct mc_event ev = {.kind = MC_EV_SERVICE_MODE, .slot = -1};
	bool ok;

	update_ctx_time(a);
	if (a->ctx.now >= a->service_until) {
		return true;
	}
	int32_t left = (int32_t)(a->service_until - a->ctx.now);

	ok = pub(a, "status", mc_enc_status_service(out, sizeof(out), left), true);
	ev.seq = mc_rtc_next_seq(a->rtc);
	ev.ts = a->ctx.now;
	ok = ok && pub(a, "event", mc_enc_event(out, sizeof(out), &ev), false);
	while (ok && a->ctx.now < a->service_until) {
		a->io->poll(a->io_user, 1000, on_incoming, a);
		apply_desired(a);
		run_commands(a);
		ok = flush_acks(a);
		update_ctx_time(a);
	}
	return ok;
}

/* The interval to sleep, from what is known now (holds started during this cycle count). */
static void plan_sleep(struct mc_app *a, int32_t batt_mv)
{
	update_ctx_time(a);
	a->next_wake_s = mc_next_wake_s(&a->ctx, batt_mv);
}

/* Last thing in a cycle: nothing may touch the retained state after this. */
static void seal(struct mc_app *a, uint32_t started_ms)
{
	memcpy(a->rtc->pump, a->ctx.pump, sizeof(a->rtc->pump));
	a->rtc->wall_at_sleep = a->ctx.now; /* 0 if the clock was never set */
	a->rtc->slept_s = (uint32_t)a->next_wake_s;
	a->rtc->last_cycle_ms = a->io->uptime_ms(a->io_user) - started_ms;
	mc_rtc_seal(a->rtc);
}

void mc_cycle(struct mc_app *a)
{
	const struct mc_io *io = a->io;
	void *u = a->io_user;
	uint32_t started = io->uptime_ms(u);
	struct mc_tel tel;
	struct fault_event faults[MAX_EVENTS];
	size_t n_faults = 0;
	int32_t rssi = a->rtc->last_rssi, wifi_ms = -1;

	memset(&tel, 0, sizeof(tel));
	memset(&inbox, 0, sizeof(inbox));

	/* 1. held pump runs that are due; nothing on by accident */
	stop_due_pumps(a);

	/* 2. sensors, all of them, before the radio is on (ADC2 vs WiFi) */
	int32_t batt = io->battery_mv(u);

	uint32_t read_uptime_ms = io->uptime_ms(u);

	read_sensors(a, &tel, faults, &n_faults);
	tel.seq = mc_rtc_next_seq(a->rtc);
	tel.ts = a->ctx.time_synced ? a->ctx.now : 0;
	tel.cfg_rev = a->cfg.rev;
	tel.h = (struct mc_health){.batt_mv = batt, .rssi = rssi, .wake = a->wake,
				   .cycle_ms = a->cold_boot ? -1 : (int32_t)a->rtc->last_cycle_ms,
				   .wifi_ms = -1};
	mc_tbuf_push(a->rtc, &tel); /* buffered first: a failed connect loses nothing */

	/* 3. connect (WiFi, MQTT with persistent session and Last Will) */
	int wn = mc_enc_status_offline(out, sizeof(out));

	if (io->connect(u, out, (size_t)wn, &rssi, &wifi_ms) < 0) {
		say(a, "could not connect: telemetry stays buffered");
		plan_sleep(a, batt);
		seal(a, started);
		return;
	}
	a->rtc->last_rssi = rssi;
	{ /* the record just pushed gets what we only know now */
		struct mc_tel *newest =
			&a->rtc->tel[(a->rtc->t_head + a->rtc->t_count - 1) % MC_TELEMETRY_BUFFER];

		newest->h.rssi = rssi;
		newest->h.wifi_ms = wifi_ms;
	}

	/* 4. status online (retained) */
	bool ok = pub(a, "status", mc_enc_status_online(out, sizeof(out), a->rtc->boot), true);

	/* clock: needed to check exp; also refreshed regularly */
	if (ok && (a->clock_base_s <= 0 || ++a->rtc->wakes_since_sync >= MC_SNTP_EVERY_WAKES)) {
		int64_t unix_s;

		if (io->sntp(u, &unix_s) == 0 && unix_s > 0) {
			a->clock_base_s = unix_s - io->uptime_ms(u) / 1000;
			a->rtc->wakes_since_sync = 0;
			/* the readings were taken before we knew the time: date them now */
			struct mc_tel *newest = &a->rtc->tel[(a->rtc->t_head + a->rtc->t_count - 1) %
							     MC_TELEMETRY_BUFFER];

			if (newest->seq == tel.seq && newest->ts == 0) {
				newest->ts = a->clock_base_s + read_uptime_ms / 1000;
			}
		} else {
			say(a, "no time sync");
		}
		update_ctx_time(a);
	}

	/* a button press asks for service mode; the clock is known now */
	if (a->service_request_s > 0 && a->ctx.time_synced) {
		a->service_until = a->ctx.now + a->service_request_s;
		a->service_request_s = 0;
	}

	/* 5. queued messages from the broker */
	if (ok) {
		io->poll(u, MC_DRAIN_MS, on_incoming, a);
	}

	/* 6. telemetry (buffered cycles first), then events */
	ok = ok && flush_telemetry(a);

	if (ok && a->cold_boot) {
		struct mc_event e = {.seq = mc_rtc_next_seq(a->rtc), .ts = a->ctx.time_synced ? a->ctx.now : 0,
				     .kind = MC_EV_BOOT, .slot = -1};

		strcpy(e.detail, a->wake == MC_WAKE_POWER_ON ? "power_on" : "reset");
		ok = pub(a, "event", mc_enc_event(out, sizeof(out), &e), false);
	}
	if (ok && a->config_invalid_at_boot) {
		struct mc_event e = {.seq = mc_rtc_next_seq(a->rtc), .kind = MC_EV_CONFIG_ERROR,
				     .slot = -1};

		strcpy(e.detail, "stored config invalid");
		ok = pub(a, "event", mc_enc_event(out, sizeof(out), &e), false);
		a->config_invalid_at_boot = false;
	}
	for (size_t i = 0; ok && i < n_faults; i++) {
		struct mc_event e = {.seq = mc_rtc_next_seq(a->rtc), .ts = a->ctx.time_synced ? a->ctx.now : 0,
				     .kind = MC_EV_SENSOR_FAULT, .slot = faults[i].slot};

		ok = pub(a, "event", mc_enc_event(out, sizeof(out), &e), false);
		if (ok) {
			a->rtc->sensor_ok[faults[i].slot] = false;
		}
	}
	if (ok && batt > 0 && batt < MC_BATT_LOW_MV && !a->rtc->low_batt_reported) {
		struct mc_event e = {.seq = mc_rtc_next_seq(a->rtc), .ts = a->ctx.time_synced ? a->ctx.now : 0,
				     .kind = MC_EV_LOW_BATTERY, .slot = -1};

		ok = pub(a, "event", mc_enc_event(out, sizeof(out), &e), false);
		a->rtc->low_batt_reported = ok || a->rtc->low_batt_reported;
	} else if (batt > MC_BATT_LOW_MV + 200) {
		a->rtc->low_batt_reported = false;
	}

	/* 7. config before commands (a command may refer to a newly configured slot) */
	if (ok) {
		apply_desired(a);
		if (a->rtc->cfg_rev_published != a->cfg.rev) { /* -1 after a power loss */
			publish_config_state(a, MC_CFG_BOOT, 0, NULL);
		}
		/* 8. commands, in order */
		run_commands(a);
		ok = flush_acks(a);
	}

	/* 9. service mode: stay connected and keep handling messages */
	if (ok && a->service_until > 0) {
		ok = service_mode(a);
	}

	/* 10. sleep: decide the interval first (it depends on holds started above), say it, seal */
	plan_sleep(a, batt);
	if (ok) {
		ok = flush_acks(a);
	}
	if (ok) {
		pub(a, "status", mc_enc_status_sleeping(out, sizeof(out), a->next_wake_s), true);
	}
	seal(a, started);
	io->disconnect(u); /* clean: no Last Will */
}
