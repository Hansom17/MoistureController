#include "mc_cmd.h"

#include <string.h>
#include <zephyr/data/json.h>
#include <zephyr/sys/util.h>

#define ABSENT INT32_MIN

const char *mc_ack_status_name(enum mc_ack_status s)
{
	switch (s) {
	case MC_ACK_RUNNING: return "running";
	case MC_ACK_DONE: return "done";
	case MC_ACK_REJECTED: return "rejected";
	case MC_ACK_FAILED: return "failed";
	case MC_ACK_CANCELLED: return "cancelled";
	}
	return "failed";
}

/* --- parsing ------------------------------------------------------------------------------------- */

struct args_j {
	int32_t slot;
	int32_t seconds;
	int32_t minutes;
	const char *target;
};

struct cmd_j {
	const char *id;
	const char *action;
	int64_t exp;
	struct args_j args;
};

static const struct json_obj_descr args_descr[] = {
	JSON_OBJ_DESCR_PRIM(struct args_j, slot, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct args_j, seconds, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct args_j, minutes, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct args_j, target, JSON_TOK_STRING),
};

static const struct json_obj_descr cmd_descr[] = {
	JSON_OBJ_DESCR_PRIM(struct cmd_j, id, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct cmd_j, action, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct cmd_j, exp, JSON_TOK_INT64),
	JSON_OBJ_DESCR_OBJECT(struct cmd_j, args, args_descr),
};

static const struct {
	const char *name;
	enum mc_action action;
} actions[] = {
	{"pump.run", MC_ACT_PUMP_RUN},
	{"pump.stop", MC_ACT_PUMP_STOP},
	{"cmd.cancel", MC_ACT_CMD_CANCEL},
	{"device.identify", MC_ACT_DEVICE_IDENTIFY},
	{"device.service", MC_ACT_DEVICE_SERVICE},
	{"device.reboot", MC_ACT_DEVICE_REBOOT},
};

static void copy_id(char *dst, const char *src)
{
	strncpy(dst, src, MC_ID_LEN);
	dst[MC_ID_LEN] = '\0';
}

bool mc_cmd_parse(char *buf, size_t len, struct mc_cmd *out)
{
	struct cmd_j j = {.id = NULL, .action = NULL, .exp = 0,
			  .args = {ABSENT, ABSENT, ABSENT, NULL}};

	if (json_obj_parse(buf, len, cmd_descr, ARRAY_SIZE(cmd_descr), &j) < 0) {
		return false;
	}
	if (j.id == NULL || j.id[0] == '\0' || strlen(j.id) > MC_ID_LEN) {
		return false; /* without an id there is nothing to acknowledge */
	}
	memset(out, 0, sizeof(*out));
	copy_id(out->id, j.id);
	out->action = MC_ACT_UNKNOWN;
	for (size_t i = 0; j.action != NULL && i < ARRAY_SIZE(actions); i++) {
		if (strcmp(j.action, actions[i].name) == 0) {
			out->action = actions[i].action;
		}
	}
	out->exp = j.exp;
	out->slot = j.args.slot == ABSENT ? -1 : j.args.slot;
	out->seconds = j.args.seconds == ABSENT ? -1 : j.args.seconds;
	out->minutes = j.args.minutes == ABSENT ? -1 : j.args.minutes;
	if (j.args.target != NULL && strlen(j.args.target) <= MC_ID_LEN) {
		copy_id(out->target, j.args.target);
	}
	return true;
}

/* --- history ---------------------------------------------------------------------------------------- */

void mc_hist_init(struct mc_cmd_hist *h)
{
	memset(h, 0, sizeof(*h));
}

const struct mc_ack *mc_hist_find(const struct mc_cmd_hist *h, const char *id)
{
	for (int i = 0; i < MC_CMD_HISTORY; i++) {
		if (h->e[i].id[0] != '\0' && strcmp(h->e[i].id, id) == 0) {
			return &h->e[i];
		}
	}
	return NULL;
}

void mc_hist_put(struct mc_cmd_hist *h, const char *id, const struct mc_ack *ack)
{
	struct mc_ack *slot = NULL;

	for (int i = 0; i < MC_CMD_HISTORY; i++) {
		if (strcmp(h->e[i].id, id) == 0) {
			slot = &h->e[i];
			break;
		}
	}
	if (slot == NULL) {
		slot = &h->e[h->next];
		h->next = (uint8_t)((h->next + 1) % MC_CMD_HISTORY);
	}
	*slot = *ack;
	copy_id(slot->id, id);
}

/* --- decisions ----------------------------------------------------------------------------------------- */

static void make_ack(struct mc_outcome *o, const char *id, enum mc_ack_status st,
		     const char *reason, const struct mc_ctx *ctx)
{
	memset(&o->ack, 0, sizeof(o->ack));
	copy_id(o->ack.id, id);
	o->ack.status = st;
	if (reason != NULL) {
		strncpy(o->ack.reason, reason, sizeof(o->ack.reason) - 1);
	}
	if (st == MC_ACK_DONE && ctx->time_synced) {
		o->ack.ts = ctx->now;
	}
}

static void reject(struct mc_outcome *o, const struct mc_cmd *c, const char *reason,
		   const struct mc_ctx *ctx)
{
	make_ack(o, c->id, MC_ACK_REJECTED, reason, ctx);
	o->action = MC_DO_NONE;
}

static const struct mc_slot *actuator(const struct mc_ctx *ctx, int32_t slot)
{
	const struct mc_slot *s = slot < 0 ? NULL : mc_config_slot(ctx->cfg, slot);
	const struct mc_module_info *m = s ? mc_module_info(s->module) : NULL;

	return (m != NULL && m->actuator) ? s : NULL;
}

static bool pump_holding(const struct mc_ctx *ctx, int slot)
{
	return ctx->pump[slot].run_ends_at > 0 && ctx->pump[slot].run_ends_at > ctx->now;
}

void mc_cmd_decide(const struct mc_ctx *ctx, const struct mc_cmd *c, struct mc_outcome *o)
{
	memset(o, 0, sizeof(*o));
	o->slot = -1;

	const struct mc_ack *seen = mc_hist_find(ctx->hist, c->id);

	if (seen != NULL) { /* duplicate delivery: same answer, nothing executed twice */
		o->ack = *seen;
		o->duplicate = true;
		return;
	}
	if (c->action == MC_ACT_UNKNOWN) {
		reject(o, c, "unknown_action", ctx);
		return;
	}
	/*
	 * Expiry needs a clock. Stopping a pump and cancelling never wait for it: refusing
	 * to switch something off because of a missing clock would be the wrong way round.
	 */
	bool needs_time = c->action != MC_ACT_PUMP_STOP && c->action != MC_ACT_CMD_CANCEL;

	if (needs_time && !ctx->time_synced) {
		reject(o, c, "no_time", ctx);
		return;
	}
	if (needs_time && c->exp < ctx->now) {
		reject(o, c, "expired", ctx);
		return;
	}

	switch (c->action) {
	case MC_ACT_PUMP_RUN: {
		const struct mc_slot *s = actuator(ctx, c->slot);

		if (c->slot < 0 || c->seconds < 0) {
			reject(o, c, "invalid_args", ctx);
			return;
		}
		if (s == NULL) {
			reject(o, c, "slot_not_actuator", ctx);
			return;
		}
		int32_t limit = MIN(s->max_run_s, MC_MAX_RUN_S_HARD);

		if (c->seconds < 1 || c->seconds > limit) {
			reject(o, c, "safety_limit", ctx);
			return;
		}
		if (pump_holding(ctx, s->slot)) {
			reject(o, c, "busy", ctx);
			return;
		}
		const struct mc_pump_state *p = &ctx->pump[s->slot];

		if (s->min_pause_s > 0 && p->last_end > 0 &&
		    ctx->now - p->last_end < s->min_pause_s) {
			reject(o, c, "safety_limit", ctx);
			return;
		}
		make_ack(o, c->id, MC_ACK_DONE, NULL, ctx);
		o->action = MC_DO_PUMP_RUN;
		o->slot = s->slot;
		o->value = c->seconds;
		return;
	}
	case MC_ACT_PUMP_STOP:
		if (c->slot < 0) {
			reject(o, c, "invalid_args", ctx);
		} else if (actuator(ctx, c->slot) == NULL) {
			reject(o, c, "slot_not_actuator", ctx);
		} else {
			make_ack(o, c->id, MC_ACK_DONE, NULL, ctx);
			o->action = MC_DO_PUMP_STOP;
			o->slot = c->slot;
		}
		return;
	case MC_ACT_CMD_CANCEL: {
		const struct mc_ack *t = c->target[0] ? mc_hist_find(ctx->hist, c->target) : NULL;

		if (c->target[0] == '\0') {
			reject(o, c, "invalid_args", ctx);
		} else if (t != NULL && t->status != MC_ACK_CANCELLED) {
			reject(o, c, "already_done", ctx);   /* it already ran */
		} else {
			make_ack(o, c->id, MC_ACK_DONE, NULL, ctx); /* unseen yet, or already dropped */
		}
		return;
	}
	case MC_ACT_DEVICE_IDENTIFY:
		make_ack(o, c->id, MC_ACK_DONE, NULL, ctx);
		o->action = MC_DO_IDENTIFY;
		o->value = c->seconds < 0 ? 10 : CLAMP(c->seconds, 1, 60);
		return;
	case MC_ACT_DEVICE_SERVICE:
		make_ack(o, c->id, MC_ACK_DONE, NULL, ctx);
		o->action = MC_DO_SERVICE;
		o->value = c->minutes < 0 ? 15 : CLAMP(c->minutes, 1, 30);
		return;
	case MC_ACT_DEVICE_REBOOT:
		make_ack(o, c->id, MC_ACK_DONE, NULL, ctx);
		o->action = MC_DO_REBOOT;
		return;
	default:
		reject(o, c, "unknown_action", ctx);
		return;
	}
}

void mc_cmd_process(struct mc_ctx *ctx, const struct mc_cmd *cmds, size_t n,
		    mc_cmd_exec_fn cb, void *user)
{
	bool cancelled[MC_CMD_BATCH_MAX] = {0};
	bool cancels_one[MC_CMD_BATCH_MAX] = {0};

	if (n > MC_CMD_BATCH_MAX) {
		n = MC_CMD_BATCH_MAX;
	}
	/* A cancel wins over a command of the same batch that hasn't run (§5.1). */
	for (size_t i = 0; i < n; i++) {
		if (cmds[i].action != MC_ACT_CMD_CANCEL || cmds[i].target[0] == '\0' ||
		    mc_hist_find(ctx->hist, cmds[i].id) != NULL) {
			continue;
		}
		for (size_t j = 0; j < n; j++) {
			if (j != i && strcmp(cmds[j].id, cmds[i].target) == 0 &&
			    mc_hist_find(ctx->hist, cmds[j].id) == NULL) {
				cancelled[j] = true;
				cancels_one[i] = true;
			}
		}
	}

	for (size_t i = 0; i < n; i++) {
		struct mc_outcome out;

		if (cancelled[i]) {
			memset(&out, 0, sizeof(out));
			out.slot = -1;
			make_ack(&out, cmds[i].id, MC_ACK_CANCELLED, NULL, ctx);
		} else if (cancels_one[i]) {
			memset(&out, 0, sizeof(out));
			out.slot = -1;
			make_ack(&out, cmds[i].id, MC_ACK_DONE, NULL, ctx);
		} else {
			mc_cmd_decide(ctx, &cmds[i], &out);
		}

		cb(ctx, &cmds[i], &out, user);

		if (out.duplicate) {
			continue;
		}
		mc_hist_put(ctx->hist, cmds[i].id, &out.ack);
		/* A cancel for a command we haven't seen: drop it if it still shows up. */
		if (cmds[i].action == MC_ACT_CMD_CANCEL && out.ack.status == MC_ACK_DONE &&
		    !cancels_one[i] && cmds[i].target[0] != '\0' &&
		    mc_hist_find(ctx->hist, cmds[i].target) == NULL) {
			struct mc_ack tomb = {.status = MC_ACK_CANCELLED};

			mc_hist_put(ctx->hist, cmds[i].target, &tomb);
		}
	}
}

/* --- pump state ---------------------------------------------------------------------------------------- */

bool mc_pump_run_is_inline(int32_t seconds)
{
	return seconds <= MC_PUMP_INLINE_MAX_S;
}

void mc_pump_begin_hold(struct mc_pump_state *p, const char *cmd_id, int64_t ends_at)
{
	p->run_ends_at = ends_at;
	copy_id(p->run_cmd, cmd_id);
}

void mc_pump_finish(struct mc_pump_state *p, int64_t now)
{
	p->last_end = now;
	p->run_ends_at = 0;
	p->run_cmd[0] = '\0';
}

bool mc_pump_end_hold(struct mc_pump_state *p, int64_t now, enum mc_ack_status status,
		      struct mc_ack *ack)
{
	bool had_cmd = p->run_cmd[0] != '\0';

	if (had_cmd) {
		memset(ack, 0, sizeof(*ack));
		copy_id(ack->id, p->run_cmd);
		ack->status = status;
		ack->ts = status == MC_ACK_DONE ? now : 0;
	}
	mc_pump_finish(p, now);
	return had_cmd;
}

int mc_pump_due_stop(const struct mc_ctx *ctx)
{
	for (int i = 0; i < MC_SLOTS_MAX; i++) {
		if (ctx->pump[i].run_ends_at > 0 && ctx->pump[i].run_ends_at <= ctx->now) {
			return i;
		}
	}
	return -1;
}

int32_t mc_pump_next_stop_in(const struct mc_ctx *ctx)
{
	int64_t best = -1;

	for (int i = 0; i < MC_SLOTS_MAX; i++) {
		int64_t end = ctx->pump[i].run_ends_at;

		if (end > 0) {
			int64_t in = end - ctx->now;

			if (in < 1) {
				in = 1;
			}
			if (best < 0 || in < best) {
				best = in;
			}
		}
	}
	return (int32_t)best;
}
