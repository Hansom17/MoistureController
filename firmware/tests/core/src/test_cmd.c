#include <zephyr/ztest.h>
#include <string.h>

#include "contract_examples.h"
#include "mc_cmd.h"

#define NOW 1790412000

static struct mc_config cfg;
static struct mc_cmd_hist hist;
static struct mc_ctx ctx;

static void before(void *f)
{
	struct mc_error e;
	char doc[] = "{\"rev\":1,\"wake_interval_s\":600,\"slots\":["
		     "{\"slot\":0,\"module\":\"moisture_capacitive\",\"pin\":34},"
		     "{\"slot\":2,\"module\":\"pump_relay\",\"pin\":25,\"max_run_s\":60,"
		     "\"min_pause_s\":600}]}";

	zassert_true(mc_config_parse(doc, strlen(doc), &cfg, &e));
	zassert_true(mc_config_validate(&cfg, &e));
	mc_hist_init(&hist);
	memset(&ctx, 0, sizeof(ctx));
	ctx.cfg = &cfg;
	ctx.now = NOW;
	ctx.time_synced = true;
	ctx.hist = &hist;
}

static bool parse(const char *json, struct mc_cmd *c)
{
	char buf[256];

	strncpy(buf, json, sizeof(buf) - 1);
	buf[sizeof(buf) - 1] = '\0';
	return mc_cmd_parse(buf, strlen(buf), c);
}

static struct mc_outcome decide(const char *json)
{
	struct mc_cmd c;
	struct mc_outcome o;

	zassert_true(parse(json, &c), "%s", json);
	mc_cmd_decide(&ctx, &c, &o);
	return o;
}

#define CMD(id, action, exp, args) \
	"{\"id\":\"" id "\",\"action\":\"" action "\",\"exp\":" #exp ",\"args\":{" args "}}"

ZTEST(cmd, test_contract_example_parses)
{
	struct mc_cmd c;

	zassert_true(EXAMPLE_CMDS_N >= 1);
	zassert_true(parse(example_cmds[0], &c));
	zassert_str_equal(c.id, "01J8ZQ6H7K2M4N5P6Q7R8S9T0V");
	zassert_equal(c.action, MC_ACT_PUMP_RUN);
	zassert_equal(c.exp, 1790414100);
	zassert_equal(c.slot, 2);
	zassert_equal(c.seconds, 10);
	zassert_equal(c.minutes, -1);
}

ZTEST(cmd, test_parse_rejects_what_cannot_be_acknowledged)
{
	struct mc_cmd c;

	zassert_false(parse("{\"action\":\"pump.run\",\"exp\":1}", &c));           /* no id */
	zassert_false(parse("{\"id\":\"\",\"action\":\"pump.run\"}", &c));
	zassert_false(parse("{\"id\":\"01234567890123456789012345X\",\"action\":\"x\"}", &c));
	zassert_false(parse("garbage", &c));
	zassert_true(parse("{\"id\":\"A\",\"action\":\"pump.fly\",\"exp\":1}", &c));
	zassert_equal(c.action, MC_ACT_UNKNOWN);
	zassert_true(parse("{\"id\":\"A\",\"exp\":1}", &c)); /* missing action: unknown, not a crash */
	zassert_equal(c.action, MC_ACT_UNKNOWN);
}

ZTEST(cmd, test_accepts_a_valid_run)
{
	struct mc_outcome o = decide(CMD("A", "pump.run", 1790414100, "\"slot\":2,\"seconds\":10"));

	zassert_equal(o.ack.status, MC_ACK_DONE);
	zassert_equal(o.action, MC_DO_PUMP_RUN);
	zassert_equal(o.slot, 2);
	zassert_equal(o.value, 10);
	zassert_equal(o.ack.ts, NOW);
}

ZTEST(cmd, test_rejections)
{
	struct { const char *json; const char *reason; } t[] = {
		{CMD("A", "pump.run", 1790411999, "\"slot\":2,\"seconds\":10"), "expired"},
		{CMD("A", "pump.run", 1790414100, "\"seconds\":10"), "invalid_args"},
		{CMD("A", "pump.run", 1790414100, "\"slot\":2"), "invalid_args"},
		{CMD("A", "pump.run", 1790414100, "\"slot\":0,\"seconds\":10"), "slot_not_actuator"},
		{CMD("A", "pump.run", 1790414100, "\"slot\":5,\"seconds\":10"), "slot_not_actuator"},
		{CMD("A", "pump.run", 1790414100, "\"slot\":2,\"seconds\":61"), "safety_limit"},
		{CMD("A", "pump.run", 1790414100, "\"slot\":2,\"seconds\":0"), "safety_limit"},
		{CMD("A", "pump.fly", 1790414100, ""), "unknown_action"},
		{CMD("A", "pump.stop", 1790414100, "\"slot\":0"), "slot_not_actuator"},
		{CMD("A", "pump.stop", 1790414100, ""), "invalid_args"},
	};

	for (size_t i = 0; i < ARRAY_SIZE(t); i++) {
		struct mc_outcome o = decide(t[i].json);

		zassert_equal(o.ack.status, MC_ACK_REJECTED, "%s", t[i].json);
		zassert_str_equal(o.ack.reason, t[i].reason, "%s", t[i].json);
		zassert_equal(o.action, MC_DO_NONE);
	}
}

ZTEST(cmd, test_expiry_boundary_is_inclusive)
{
	struct mc_outcome o = decide(CMD("A", "pump.run", 1790412000, "\"slot\":2,\"seconds\":5"));

	zassert_equal(o.ack.status, MC_ACK_DONE); /* exp == now still runs */
}

ZTEST(cmd, test_no_clock_means_no_watering)
{
	ctx.time_synced = false;
	struct mc_outcome o = decide(CMD("A", "pump.run", 1790414100, "\"slot\":2,\"seconds\":5"));

	zassert_equal(o.ack.status, MC_ACK_REJECTED);
	zassert_str_equal(o.ack.reason, "no_time");
	o = decide(CMD("B", "device.identify", 1790414100, ""));
	zassert_str_equal(o.ack.reason, "no_time");
	/* switching off never waits for a clock */
	o = decide(CMD("C", "pump.stop", 1790414100, "\"slot\":2"));
	zassert_equal(o.ack.status, MC_ACK_DONE);
	zassert_equal(o.action, MC_DO_PUMP_STOP);
	zassert_equal(o.ack.ts, 0); /* no timestamp without a clock */
}

ZTEST(cmd, test_min_pause_and_busy)
{
	ctx.pump[2].last_end = NOW - 100; /* ended 100 s ago, pause is 600 s */
	struct mc_outcome o = decide(CMD("A", "pump.run", 1790414100, "\"slot\":2,\"seconds\":5"));

	zassert_str_equal(o.ack.reason, "safety_limit");
	ctx.pump[2].last_end = NOW - 600;
	o = decide(CMD("A", "pump.run", 1790414100, "\"slot\":2,\"seconds\":5"));
	zassert_equal(o.ack.status, MC_ACK_DONE);

	ctx.pump[2].last_end = 0;
	mc_pump_begin_hold(&ctx.pump[2], "HELD", NOW + 120);
	o = decide(CMD("B", "pump.run", 1790414100, "\"slot\":2,\"seconds\":5"));
	zassert_str_equal(o.ack.reason, "busy");
}

ZTEST(cmd, test_misc_actions_and_clamping)
{
	struct mc_outcome o = decide(CMD("A", "device.identify", 1790414100, ""));

	zassert_equal(o.action, MC_DO_IDENTIFY);
	zassert_equal(o.value, 10);
	o = decide(CMD("B", "device.identify", 1790414100, "\"seconds\":500"));
	zassert_equal(o.value, 60);
	o = decide(CMD("C", "device.service", 1790414100, "\"minutes\":99"));
	zassert_equal(o.action, MC_DO_SERVICE);
	zassert_equal(o.value, 30);
	o = decide(CMD("D", "device.service", 1790414100, ""));
	zassert_equal(o.value, 15);
	o = decide(CMD("E", "device.reboot", 1790414100, ""));
	zassert_equal(o.action, MC_DO_REBOOT);
}

ZTEST(cmd, test_duplicates_are_answered_again_not_executed)
{
	struct mc_cmd c;
	struct mc_outcome o;
	struct mc_ack running = {.id = "A", .status = MC_ACK_RUNNING, .ends_at = NOW + 100};

	zassert_true(parse(CMD("A", "pump.run", 1790414100, "\"slot\":2,\"seconds\":5"), &c));
	mc_hist_put(&hist, "A", &running);
	mc_cmd_decide(&ctx, &c, &o);
	zassert_true(o.duplicate);
	zassert_equal(o.action, MC_DO_NONE);
	zassert_equal(o.ack.status, MC_ACK_RUNNING);
	zassert_equal(o.ack.ends_at, NOW + 100);
}

ZTEST(cmd, test_history_keeps_the_last_16)
{
	struct mc_ack a = {.status = MC_ACK_DONE};
	char id[8];

	for (int i = 1; i <= 20; i++) {
		snprintk(id, sizeof(id), "C%d", i);
		mc_hist_put(&hist, id, &a);
	}
	zassert_is_null(mc_hist_find(&hist, "C1"));
	zassert_is_null(mc_hist_find(&hist, "C4"));
	zassert_not_null(mc_hist_find(&hist, "C5"));
	zassert_not_null(mc_hist_find(&hist, "C20"));
	/* updating an existing id does not evict another */
	a.status = MC_ACK_REJECTED;
	mc_hist_put(&hist, "C5", &a);
	zassert_not_null(mc_hist_find(&hist, "C6"));
	zassert_equal(mc_hist_find(&hist, "C5")->status, MC_ACK_REJECTED);
}

/* --- batches ------------------------------------------------------------------------------------ */

struct log {
	int n;
	char id[8][MC_ID_LEN + 1];
	enum mc_ack_status status[8];
	enum mc_do_kind action[8];
	char reason[8][20];
};

static void exec(struct mc_ctx *c, const struct mc_cmd *cmd, struct mc_outcome *out, void *user)
{
	struct log *l = user;

	strcpy(l->id[l->n], out->ack.id);
	l->status[l->n] = out->ack.status;
	l->action[l->n] = out->action;
	strcpy(l->reason[l->n], out->ack.reason);
	l->n++;
	if (out->action == MC_DO_PUMP_RUN) { /* what the app does for a short run */
		mc_pump_finish(&c->pump[out->slot], c->now);
	}
}

static struct log run_batch(const char *const *json, size_t n)
{
	struct mc_cmd cmds[MC_CMD_BATCH_MAX];
	struct log l = {0};

	for (size_t i = 0; i < n; i++) {
		zassert_true(parse(json[i], &cmds[i]));
	}
	mc_cmd_process(&ctx, cmds, n, exec, &l);
	return l;
}

ZTEST(cmd, test_cancel_wins_over_a_command_in_the_same_batch)
{
	const char *b[] = {
		CMD("RUN", "pump.run", 1790414100, "\"slot\":2,\"seconds\":10"),
		CMD("CXL", "cmd.cancel", 1790414100, "\"target\":\"RUN\""),
	};
	struct log l = run_batch(b, 2);

	zassert_equal(l.n, 2);
	zassert_str_equal(l.id[0], "RUN");
	zassert_equal(l.status[0], MC_ACK_CANCELLED);
	zassert_equal(l.action[0], MC_DO_NONE); /* the pump never ran */
	zassert_str_equal(l.id[1], "CXL");
	zassert_equal(l.status[1], MC_ACK_DONE);
	zassert_equal(ctx.pump[2].last_end, 0);
}

ZTEST(cmd, test_cancel_arriving_first_also_works)
{
	const char *b[] = {
		CMD("CXL", "cmd.cancel", 1790414100, "\"target\":\"RUN\""),
		CMD("RUN", "pump.run", 1790414100, "\"slot\":2,\"seconds\":10"),
	};
	struct log l = run_batch(b, 2);

	zassert_equal(l.status[0], MC_ACK_DONE);
	zassert_equal(l.status[1], MC_ACK_CANCELLED);
	zassert_equal(l.action[1], MC_DO_NONE);
}

ZTEST(cmd, test_cancel_after_the_run_is_already_done)
{
	const char *b1[] = {CMD("RUN", "pump.run", 1790414100, "\"slot\":2,\"seconds\":10")};
	const char *b2[] = {CMD("CXL", "cmd.cancel", 1790414100, "\"target\":\"RUN\"")};
	struct log l = run_batch(b1, 1);

	zassert_equal(l.status[0], MC_ACK_DONE);
	l = run_batch(b2, 1);
	zassert_equal(l.status[0], MC_ACK_REJECTED);
	zassert_str_equal(l.reason[0], "already_done");
}

ZTEST(cmd, test_cancel_for_a_command_not_seen_yet_leaves_a_tombstone)
{
	const char *b1[] = {CMD("CXL", "cmd.cancel", 1790414100, "\"target\":\"LATER\"")};
	const char *b2[] = {CMD("LATER", "pump.run", 1790414100, "\"slot\":2,\"seconds\":10")};
	struct log l = run_batch(b1, 1);

	zassert_equal(l.status[0], MC_ACK_DONE);
	l = run_batch(b2, 1);
	zassert_equal(l.n, 1);
	zassert_equal(l.status[0], MC_ACK_CANCELLED);
	zassert_equal(l.action[0], MC_DO_NONE);
}

ZTEST(cmd, test_a_redelivered_batch_is_not_executed_twice)
{
	const char *b[] = {CMD("RUN", "pump.run", 1790414100, "\"slot\":2,\"seconds\":10"),
			   CMD("ID", "device.identify", 1790414100, "")};
	struct log l = run_batch(b, 2);

	zassert_equal(l.action[0], MC_DO_PUMP_RUN);
	ctx.pump[2].last_end = 0; /* would otherwise trip the safety pause */
	l = run_batch(b, 2);
	zassert_equal(l.n, 2);
	zassert_equal(l.action[0], MC_DO_NONE);
	zassert_equal(l.action[1], MC_DO_NONE);
	zassert_equal(l.status[0], MC_ACK_DONE); /* same answer again */
}

ZTEST(cmd, test_commands_run_in_order_and_the_pause_applies_between_them)
{
	const char *b[] = {CMD("R1", "pump.run", 1790414100, "\"slot\":2,\"seconds\":5"),
			   CMD("R2", "pump.run", 1790414100, "\"slot\":2,\"seconds\":5")};
	struct log l = run_batch(b, 2);

	zassert_equal(l.status[0], MC_ACK_DONE);
	zassert_equal(l.status[1], MC_ACK_REJECTED); /* min_pause_s 600 after the first */
	zassert_str_equal(l.reason[1], "safety_limit");
}

/* --- pump holds through sleep ---------------------------------------------------------------------- */

ZTEST(cmd, test_long_run_hold_lifecycle)
{
	zassert_false(mc_pump_run_is_inline(MC_PUMP_INLINE_MAX_S + 1));
	zassert_true(mc_pump_run_is_inline(MC_PUMP_INLINE_MAX_S));
	zassert_equal(mc_pump_due_stop(&ctx), -1);
	zassert_equal(mc_pump_next_stop_in(&ctx), -1);

	mc_pump_begin_hold(&ctx.pump[2], "LONG", NOW + 300);
	zassert_equal(mc_pump_due_stop(&ctx), -1);
	zassert_equal(mc_pump_next_stop_in(&ctx), 300);

	ctx.now = NOW + 300; /* woke up at the end */
	zassert_equal(mc_pump_due_stop(&ctx), 2);
	struct mc_ack ack;

	zassert_true(mc_pump_end_hold(&ctx.pump[2], ctx.now, MC_ACK_DONE, &ack));
	zassert_str_equal(ack.id, "LONG");
	zassert_equal(ack.status, MC_ACK_DONE);
	zassert_equal(ack.ts, NOW + 300);
	zassert_equal(mc_pump_due_stop(&ctx), -1);
	zassert_equal(ctx.pump[2].last_end, NOW + 300);
	zassert_false(mc_pump_end_hold(&ctx.pump[2], ctx.now, MC_ACK_DONE, &ack)); /* nothing left */
}

ZTEST(cmd, test_stopping_a_held_run_cancels_its_command)
{
	struct mc_ack ack;

	mc_pump_begin_hold(&ctx.pump[2], "LONG", NOW + 300);
	zassert_true(mc_pump_end_hold(&ctx.pump[2], ctx.now, MC_ACK_CANCELLED, &ack));
	zassert_equal(ack.status, MC_ACK_CANCELLED);
	zassert_equal(ack.ts, 0);
}

ZTEST_SUITE(cmd, NULL, NULL, before, NULL, NULL);
