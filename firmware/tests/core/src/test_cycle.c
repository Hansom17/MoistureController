/* The whole wake cycle against a fake broker and fake hardware. */
#include <zephyr/ztest.h>
#include <string.h>

#include "mc_cycle.h"

#define T0 1790412000
#define MAXP 40

struct incoming {
	enum mc_in_kind kind;
	char payload[700];
};

struct fake {
	/* scripted */
	int32_t adc[MC_SLOTS_MAX];
	int32_t batt;
	int connect_rc;
	int sntp_rc;
	int64_t sntp_unix;
	int fail_publish_at;           /* publish number (1-based) that fails; 0 = never */
	struct incoming in[16];
	int n_in, in_pos;
	/* recorded */
	struct { char suffix[16]; char payload[2100]; bool retain; } pub[MAXP];
	int n_pub, n_attempts;
	char log[1024];                /* call order, e.g. "adc connect publish:status" */
	struct { int slot; bool on; bool hold; } pump[16];
	int n_pump;
	int32_t delayed_ms;
	int identify_s;
	int sntp_calls;
	int saves;
	struct mc_config saved;
	bool disconnected;
	uint32_t uptime;
};

static struct fake f;
static struct mc_rtc rtc;
static struct mc_app app;

static void note(const char *w)
{
	if (strlen(f.log) + strlen(w) + 2 < sizeof(f.log)) {
		strcat(f.log, f.log[0] ? " " : "");
		strcat(f.log, w);
	}
}

static int io_adc(void *u, const struct mc_slot *s, int32_t *raw)
{
	note("adc");
	if (f.adc[s->slot] < 0) {
		return -1;
	}
	*raw = f.adc[s->slot];
	return 0;
}
static int32_t io_batt(void *u) { return f.batt; }
static void io_pump(void *u, const struct mc_slot *s, bool on, bool hold)
{
	f.pump[f.n_pump].slot = s->slot;
	f.pump[f.n_pump].on = on;
	f.pump[f.n_pump].hold = hold;
	f.n_pump++;
	note(on ? "pump_on" : "pump_off");
}
static void io_delay(void *u, int32_t ms) { f.delayed_ms += ms; f.uptime += ms; }
static void io_identify(void *u, int32_t s) { f.identify_s = s; }
static uint32_t io_uptime(void *u) { return f.uptime; }
static int io_sntp(void *u, int64_t *t)
{
	f.sntp_calls++;
	note("sntp");
	if (f.sntp_rc) {
		return -1;
	}
	*t = f.sntp_unix + f.uptime / 1000;
	return 0;
}
static int io_save(void *u, const struct mc_config *c)
{
	f.saves++;
	f.saved = *c;
	return 0;
}
static int io_connect(void *u, const char *will, size_t len, int32_t *rssi, int32_t *wifi_ms)
{
	note("connect");
	f.uptime += 1400;
	if (f.connect_rc) {
		return -1;
	}
	zassert_equal(len, strlen("{\"state\":\"offline\"}"));
	zassert_mem_equal(will, "{\"state\":\"offline\"}", len);
	*rssi = -67;
	*wifi_ms = 1400;
	return 0;
}
static int io_publish(void *u, const char *suffix, const char *payload, size_t len, bool retain)
{
	f.n_attempts++;
	if (f.fail_publish_at && f.n_attempts == f.fail_publish_at) {
		return -1;
	}
	zassert_true(f.n_pub < MAXP);
	strcpy(f.pub[f.n_pub].suffix, suffix);
	memcpy(f.pub[f.n_pub].payload, payload, len);
	f.pub[f.n_pub].payload[len] = '\0';
	f.pub[f.n_pub].retain = retain;
	f.n_pub++;
	char tag[32];

	snprintk(tag, sizeof(tag), "pub:%s", suffix);
	note(tag);
	return 0;
}
static void io_poll(void *u, int32_t ms, mc_in_fn cb, void *cb_user)
{
	note("poll");
	f.uptime += ms;
	while (f.in_pos < f.n_in) {
		struct incoming *m = &f.in[f.in_pos++];

		cb(cb_user, m->kind, (const uint8_t *)m->payload, strlen(m->payload));
	}
}
static void io_disconnect(void *u) { f.disconnected = true; note("disconnect"); }

static const struct mc_io io = {
	.read_adc = io_adc, .battery_mv = io_batt, .pump_set = io_pump, .delay_ms = io_delay,
	.identify = io_identify, .uptime_ms = io_uptime, .sntp = io_sntp, .save_config = io_save,
	.connect = io_connect, .publish = io_publish, .poll = io_poll, .disconnect = io_disconnect,
};

static const char *CFG =
	"{\"rev\":3,\"wake_interval_s\":600,\"slots\":["
	"{\"slot\":0,\"module\":\"moisture_capacitive\",\"pin\":34,\"cal\":{\"dry\":3000,\"wet\":1200}},"
	"{\"slot\":2,\"module\":\"pump_relay\",\"pin\":25,\"active_high\":true,\"max_run_s\":60,"
	"\"min_pause_s\":0}]}";

static void give(enum mc_in_kind k, const char *payload)
{
	f.in[f.n_in].kind = k;
	strcpy(f.in[f.n_in].payload, payload);
	f.n_in++;
}

static void before(void *x)
{
	struct mc_error e;
	char doc[700];

	memset(&f, 0, sizeof(f));
	f.batt = 3900;
	f.sntp_unix = T0;
	f.adc[0] = 2100;
	memset(&rtc, 0, sizeof(rtc));
	memset(&app, 0, sizeof(app));
	strcpy(doc, CFG);
	zassert_true(mc_config_parse(doc, strlen(doc), &app.cfg, &e));
}

/* Starts an app on the retained state as it is (zeroed = power loss) and runs one cycle. */
static void cycle(enum mc_wake wake, enum mc_cfg_load cfg)
{
	struct mc_config keep = app.cfg;

	f.n_pub = f.n_attempts = f.n_pump = 0;
	f.delayed_ms = f.sntp_calls = f.saves = 0;
	f.in_pos = 0;
	f.log[0] = '\0';
	f.disconnected = false;
	mc_app_begin(&app, &rtc, &io, NULL, wake, cfg);
	if (cfg == MC_CFG_LOADED) {
		app.cfg = keep;
		app.ctx.cfg = &app.cfg;
	}
	mc_cycle(&app);
}

static void next_wake_cycle(void)
{
	/* what the hardware does between two cycles: time passes, uptime starts over */
	f.uptime = 0;
	f.n_in = 0;
}

static void sleep_for(int seconds);

static int find(const char *suffix, int from)
{
	for (int i = from; i < f.n_pub; i++) {
		if (strcmp(f.pub[i].suffix, suffix) == 0) {
			return i;
		}
	}
	return -1;
}

/* Index of the first publish on `suffix` (from `from`) whose payload contains `needle`. */
static int find_with(const char *suffix, const char *needle, int from)
{
	for (int i = from; i < f.n_pub; i++) {
		if (strcmp(f.pub[i].suffix, suffix) == 0 && strstr(f.pub[i].payload, needle)) {
			return i;
		}
	}
	return -1;
}

/* What the hardware timer does: time passes, then we wake with the retained state intact. */
static void sleep_for(int seconds)
{
	f.uptime = 0;
	f.n_in = 0;
	rtc.slept_s = (uint32_t)seconds;
	mc_rtc_seal(&rtc);
	zassert_true(mc_rtc_valid(&rtc));
}

static void expect_order(const char *const *want, size_t n)
{
	zassert_equal(f.n_pub, (int)n, "%d publishes, log: %s", f.n_pub, f.log);
	for (size_t i = 0; i < n; i++) {
		zassert_str_equal(f.pub[i].suffix, want[i], "#%d in: %s", (int)i, f.log);
	}
}

ZTEST(cycle, test_normal_cycle_follows_the_wire_sequence)
{
	cycle(MC_WAKE_POWER_ON, MC_CFG_LOADED);
	const char *want[] = {"status", "telemetry", "event", "config/state", "status"};

	expect_order(want, ARRAY_SIZE(want));
	zassert_str_equal(f.pub[0].payload,
			  "{\"state\":\"online\",\"fw\":\"" MC_FW_VERSION "\",\"boot\":1}");
	zassert_true(f.pub[0].retain);
	zassert_not_null(strstr(f.pub[1].payload, "\"seq\":1,\"ts\":17904120"));
	zassert_not_null(strstr(f.pub[1].payload, "\"value\":50.0"));
	zassert_not_null(strstr(f.pub[1].payload, "\"rssi\":-67"));
	zassert_not_null(strstr(f.pub[1].payload, "\"wake\":\"power_on\""));
	zassert_not_null(strstr(f.pub[1].payload, "\"wifi_ms\":1400"));
	zassert_false(f.pub[1].retain);
	zassert_not_null(strstr(f.pub[2].payload, "\"kind\":\"boot\""));
	zassert_not_null(strstr(f.pub[2].payload, "\"seq\":2"));
	zassert_not_null(strstr(f.pub[3].payload, "\"result\":\"boot\""));
	zassert_true(f.pub[3].retain);
	zassert_str_equal(f.pub[4].payload, "{\"state\":\"sleeping\",\"next_wake_s\":600}");
	zassert_true(f.pub[4].retain);
	zassert_true(f.disconnected);
	zassert_equal(app.next_wake_s, 600);
	zassert_true(mc_rtc_valid(&rtc)); /* sealed for the next wake */
}

ZTEST(cycle, test_sensors_are_read_before_the_radio)
{
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	char *adc = strstr(f.log, "adc"), *conn = strstr(f.log, "connect");

	zassert_not_null(adc);
	zassert_not_null(conn);
	zassert_true(adc < conn, "%s", f.log);
}

ZTEST(cycle, test_second_wake_is_quiet_and_keeps_counting)
{
	cycle(MC_WAKE_POWER_ON, MC_CFG_LOADED);
	next_wake_cycle();
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	const char *want[] = {"status", "telemetry", "status"}; /* no boot event, no config/state */

	expect_order(want, ARRAY_SIZE(want));
	zassert_not_null(strstr(f.pub[0].payload, "\"boot\":2"));
	zassert_not_null(strstr(f.pub[1].payload, "\"seq\":3")); /* 1 telemetry, 2 boot event, 3 now */
	zassert_not_null(strstr(f.pub[1].payload, "\"cycle_ms\":"));
	/* the clock carried over the sleep: no SNTP needed */
	zassert_equal(f.sntp_calls, 0);
	zassert_not_null(strstr(f.pub[1].payload, "\"ts\":1790412"));
}

ZTEST(cycle, test_failed_connect_buffers_and_the_next_cycle_sends_oldest_first)
{
	f.connect_rc = -1;
	cycle(MC_WAKE_POWER_ON, MC_CFG_LOADED);
	zassert_equal(f.n_pub, 0);
	zassert_equal(rtc.t_count, 1);
	zassert_true(mc_rtc_valid(&rtc));
	zassert_equal(app.next_wake_s, 600);
	zassert_false(f.disconnected); /* never connected */

	next_wake_cycle();
	f.connect_rc = -1;
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(rtc.t_count, 2);

	next_wake_cycle();
	f.connect_rc = 0;
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	int t1 = find("telemetry", 0), t2 = find("telemetry", t1 + 1), t3 = find("telemetry", t2 + 1);

	zassert_true(t1 >= 0 && t2 > t1 && t3 > t2, "three telemetry messages, got %s", f.log);
	zassert_not_null(strstr(f.pub[t1].payload, "\"seq\":1,"));
	zassert_not_null(strstr(f.pub[t2].payload, "\"seq\":2,"));
	zassert_not_null(strstr(f.pub[t3].payload, "\"seq\":3,"));
	zassert_equal(rtc.t_count, 0);
	/* the old record has its own wake reason and no clock (it never had one) */
	zassert_not_null(strstr(f.pub[t1].payload, "\"wake\":\"power_on\""));
	zassert_is_null(strstr(f.pub[t1].payload, "\"ts\":"));
}

ZTEST(cycle, test_a_dropped_publish_keeps_the_rest_buffered)
{
	f.fail_publish_at = 2; /* status went out, the telemetry publish fails */
	cycle(MC_WAKE_POWER_ON, MC_CFG_LOADED);
	zassert_equal(rtc.t_count, 1, "still buffered");
	zassert_true(f.disconnected);
	zassert_equal(find("status", 1), -1, "no 'sleeping' on a broken connection");
	zassert_true(mc_rtc_valid(&rtc));
}

ZTEST(cycle, test_unsynced_clock_runs_sntp_and_failing_it_rejects_commands)
{
	f.sntp_rc = -1;
	give(MC_IN_CMD, "{\"id\":\"A\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":5}}");
	cycle(MC_WAKE_POWER_ON, MC_CFG_LOADED);
	zassert_equal(f.sntp_calls, 1);
	int ack = find("cmd/ack", 0);

	zassert_true(ack >= 0);
	zassert_str_equal(f.pub[ack].payload,
			  "{\"id\":\"A\",\"status\":\"rejected\",\"reason\":\"no_time\"}");
	zassert_equal(f.n_pump > 0 ? f.pump[f.n_pump - 1].on : false, false, "pump never ran");
	zassert_is_null(strstr(f.pub[find("telemetry", 0)].payload, "\"ts\":"));
}

ZTEST(cycle, test_config_is_applied_before_commands_and_reported)
{
	give(MC_IN_CMD, "{\"id\":\"A\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":4,\"seconds\":5}}");
	give(MC_IN_CONFIG, "{\"rev\":4,\"wake_interval_s\":900,\"slots\":["
			   "{\"slot\":0,\"module\":\"moisture_capacitive\",\"pin\":34},"
			   "{\"slot\":4,\"module\":\"pump_relay\",\"pin\":26,\"max_run_s\":30}]}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	int cs = find("config/state", 0), ack = find("cmd/ack", 0);

	zassert_true(cs >= 0 && ack > cs, "config/state before the ack: %s", f.log);
	zassert_not_null(strstr(f.pub[cs].payload, "\"rev\":4,\"result\":\"applied\""));
	zassert_not_null(strstr(f.pub[ack].payload, "{\"id\":\"A\",\"status\":\"done\",\"ts\":17904120"));
	zassert_equal(f.saves, 1);
	zassert_equal(f.saved.rev, 4);
	zassert_equal(app.cfg.wake_interval_s, 900);
	zassert_equal(app.next_wake_s, 900);
}

ZTEST(cycle, test_rejected_config_changes_nothing)
{
	give(MC_IN_CONFIG, "{\"rev\":4,\"wake_interval_s\":600,\"slots\":["
			   "{\"slot\":2,\"module\":\"pump_relay\",\"pin\":34,\"max_run_s\":30}]}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	int cs = find("config/state", 0);

	zassert_true(cs >= 0);
	zassert_not_null(strstr(f.pub[cs].payload, "\"rev\":3,\"result\":\"rejected\",\"rejected_rev\":4"));
	zassert_not_null(strstr(f.pub[cs].payload, "\"code\":\"pin_not_output\""));
	zassert_equal(f.saves, 0);
	zassert_equal(app.cfg.rev, 3);
}

ZTEST(cycle, test_old_and_duplicate_config_revisions_are_ignored)
{
	give(MC_IN_CONFIG, "{\"rev\":3,\"wake_interval_s\":900,\"slots\":[]}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(f.saves, 0);
	zassert_equal(app.cfg.wake_interval_s, 600);
}

ZTEST(cycle, test_garbage_from_the_broker_does_not_hurt)
{
	give(MC_IN_CONFIG, "{oops");
	give(MC_IN_CMD, "{also not json");
	give(MC_IN_CMD, "{\"action\":\"pump.run\"}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(find("cmd/ack", 0), -1);
	zassert_true(find("status", 1) >= 0, "still went to sleep properly");
}

ZTEST(cycle, test_short_pump_run_happens_inside_the_wake)
{
	give(MC_IN_CMD, "{\"id\":\"A\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":10}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(f.delayed_ms, 10000);
	bool on = false, off_after = false;

	for (int i = 0; i < f.n_pump; i++) {
		if (f.pump[i].slot == 2 && f.pump[i].on) {
			on = true;
			zassert_false(f.pump[i].hold);
		} else if (on && f.pump[i].slot == 2) {
			off_after = true;
		}
	}
	zassert_true(on && off_after);
	zassert_false(f.pump[f.n_pump - 1].on);
	int ack = find("cmd/ack", 0);

	zassert_not_null(strstr(f.pub[ack].payload, "\"status\":\"done\""));
	zassert_equal(rtc.pump[2].run_ends_at, 0);
	zassert_true(rtc.pump[2].last_end > T0);
}

ZTEST(cycle, test_long_run_holds_through_sleep_and_ends_in_its_own_wake)
{
	give(MC_IN_CMD, "{\"id\":\"LONG\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":60}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(f.delayed_ms, 0, "the device does not babysit the pump");
	zassert_true(f.pump[f.n_pump - 1].on && f.pump[f.n_pump - 1].hold);
	int ack = find("cmd/ack", 0);

	zassert_not_null(strstr(f.pub[ack].payload, "\"status\":\"running\",\"ends_at\":17904120"));
	int sl = find("status", 1);

	zassert_true(sl > 0);
	zassert_not_null(strstr(f.pub[sl].payload, "\"next_wake_s\":")); /* shortened to the end of the run */
	zassert_true(app.next_wake_s <= 60 && app.next_wake_s >= 50, "%d", app.next_wake_s);

	/* the wake at the end of the run */
	sleep_for(60);
	cycle(MC_WAKE_PUMP_STOP, MC_CFG_LOADED);
	zassert_false(app.cold_boot, "retained state must have survived");
	zassert_false(f.pump[0].on, "pump switched off first thing");
	zassert_equal(f.pump[0].slot, 2);
	char *off = strstr(f.log, "pump_off"), *conn = strstr(f.log, "connect");

	zassert_true(off && conn && off < conn, "off before the radio: %s", f.log);
	ack = find("cmd/ack", 0);
	zassert_true(ack >= 0);
	zassert_not_null(strstr(f.pub[ack].payload, "\"id\":\"LONG\",\"status\":\"done\""));
	zassert_equal(app.next_wake_s, 600);
	zassert_equal(rtc.pump[2].run_ends_at, 0);
}

ZTEST(cycle, test_finished_run_ack_survives_a_failed_connect)
{
	give(MC_IN_CMD, "{\"id\":\"LONG\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":60}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	sleep_for(60);
	f.connect_rc = -1; /* the wake at the end of the run has no WiFi */
	cycle(MC_WAKE_PUMP_STOP, MC_CFG_LOADED);
	zassert_false(f.pump[0].on, "pump is off regardless");
	zassert_equal(rtc.pend_n, 1, "the final ack waits");

	sleep_for(600);
	f.connect_rc = 0;
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	int ack = find("cmd/ack", 0);

	zassert_true(ack >= 0);
	zassert_not_null(strstr(f.pub[ack].payload, "\"id\":\"LONG\",\"status\":\"done\""));
	zassert_equal(rtc.pend_n, 0);
}

ZTEST(cycle, test_redelivered_command_is_reacked_not_rerun)
{
	give(MC_IN_CMD, "{\"id\":\"A\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":5}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(f.delayed_ms, 5000);
	next_wake_cycle();
	give(MC_IN_CMD, "{\"id\":\"A\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":5}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(f.delayed_ms, 0, "not run twice");
	int ack = find("cmd/ack", 0);

	zassert_true(ack >= 0);
	zassert_not_null(strstr(f.pub[ack].payload, "\"id\":\"A\",\"status\":\"done\""));
}

ZTEST(cycle, test_cancel_in_the_same_delivery_prevents_the_run)
{
	give(MC_IN_CMD, "{\"id\":\"A\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":5}}");
	give(MC_IN_CMD, "{\"id\":\"B\",\"action\":\"cmd.cancel\",\"exp\":1790414100,"
			"\"args\":{\"target\":\"A\"}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(f.delayed_ms, 0);
	int a1 = find("cmd/ack", 0), a2 = find("cmd/ack", a1 + 1);

	zassert_not_null(strstr(f.pub[a1].payload, "\"id\":\"A\",\"status\":\"cancelled\""));
	zassert_not_null(strstr(f.pub[a2].payload, "\"id\":\"B\",\"status\":\"done\""));
}

ZTEST(cycle, test_sensor_fault_is_reported_once_per_transition)
{
	f.adc[0] = 4095; /* nothing connected */
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_true(find_with("event", "\"kind\":\"sensor_fault\",\"slot\":0", 0) >= 0);
	zassert_not_null(strstr(f.pub[find("telemetry", 0)].payload, "\"error\":\"no_signal\""));
	next_wake_cycle();
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(find("event", 0), -1, "still broken: no second event");
	next_wake_cycle();
	f.adc[0] = 2100; /* recovered */
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(find("event", 0), -1, "recovery is silent");
	next_wake_cycle();
	f.adc[0] = 4095; /* broken again */
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_true(find_with("event", "sensor_fault", 0) >= 0);
}

ZTEST(cycle, test_driver_error_is_a_bus_error)
{
	f.adc[0] = -1;
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_not_null(strstr(f.pub[find("telemetry", 0)].payload, "\"error\":\"bus_error\""));
}

ZTEST(cycle, test_low_battery_event_once_and_longer_sleep)
{
	f.batt = 3200;
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_true(find_with("event", "\"kind\":\"low_battery\"", 0) >= 0);
	zassert_equal(app.next_wake_s, 1800);
	next_wake_cycle();
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(find("event", 0), -1, "reported once");
	next_wake_cycle();
	f.batt = 3700;
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	next_wake_cycle();
	f.batt = 3200;
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_true(find_with("event", "low_battery", 0) >= 0, "reported again after a recovery");
}

ZTEST(cycle, test_service_mode_stays_awake_and_handles_messages)
{
	give(MC_IN_CMD, "{\"id\":\"S\",\"action\":\"device.service\",\"exp\":1790414100,"
			"\"args\":{\"minutes\":1}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	int st = find("status", 1);

	zassert_true(st > 0);
	zassert_not_null(strstr(f.pub[st].payload, "\"state\":\"service\",\"until_s\":"));
	zassert_true(f.uptime >= 60000, "stayed awake about a minute, uptime %u", (unsigned)f.uptime);
	int sl = find("status", st + 1);

	zassert_true(sl > st);
	zassert_not_null(strstr(f.pub[sl].payload, "\"state\":\"sleeping\""));
	zassert_not_null(strstr(f.pub[find("event", 0)].payload, "\"kind\":\"boot\"")); /* cold boot first */
}

ZTEST(cycle, test_identify_and_reboot)
{
	give(MC_IN_CMD, "{\"id\":\"I\",\"action\":\"device.identify\",\"exp\":1790414100,"
			"\"args\":{\"seconds\":7}}");
	give(MC_IN_CMD, "{\"id\":\"R\",\"action\":\"device.reboot\",\"exp\":1790414100}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(f.identify_s, 7);
	zassert_true(app.reboot);
	zassert_true(find("cmd/ack", 0) >= 0);
	/* the ack was sent before anything restarts */
}

ZTEST(cycle, test_corrupt_stored_config_reports_an_error_and_runs_the_default)
{
	cycle(MC_WAKE_POWER_ON, MC_CFG_CORRUPT);
	int ev = find("event", 0), ev2 = find("event", ev + 1);

	zassert_true(ev >= 0 && ev2 > ev);
	zassert_not_null(strstr(f.pub[ev2].payload, "\"kind\":\"config_error\""));
	zassert_equal(app.cfg.n, 0);
	zassert_not_null(strstr(f.pub[find("telemetry", 0)].payload, "\"readings\":[]"));
}

ZTEST(cycle, test_first_boot_without_config_is_not_an_error)
{
	cycle(MC_WAKE_POWER_ON, MC_CFG_MISSING);
	int ev = find("event", 0);

	zassert_true(ev >= 0);
	zassert_is_null(strstr(f.pub[ev].payload, "config_error"));
	zassert_equal(find("event", ev + 1), -1);
}

ZTEST(cycle, test_a_config_change_switches_pumps_off)
{
	give(MC_IN_CMD, "{\"id\":\"LONG\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":60}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	sleep_for(10);
	give(MC_IN_CONFIG, "{\"rev\":9,\"wake_interval_s\":600,\"slots\":[]}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_false(app.cold_boot);
	zassert_false(f.pump[f.n_pump - 1].on);
	zassert_equal(rtc.pump[2].run_ends_at, 0);
	int ack = find("cmd/ack", 0);

	zassert_true(ack >= 0);
	zassert_not_null(strstr(f.pub[ack].payload, "\"id\":\"LONG\",\"status\":\"cancelled\""));
}

ZTEST_SUITE(cycle, NULL, NULL, before, NULL, NULL);

ZTEST(cycle, test_long_run_on_a_pin_without_rtc_hold_stays_awake)
{
	/* GPIO 18 cannot keep its level in deep sleep: the run happens inside the wake */
	struct mc_error e;
	char doc[] = "{\"rev\":3,\"wake_interval_s\":600,\"slots\":["
		     "{\"slot\":2,\"module\":\"pump_relay\",\"pin\":18,\"max_run_s\":60}]}";

	zassert_true(mc_config_parse(doc, strlen(doc), &app.cfg, &e));
	give(MC_IN_CMD, "{\"id\":\"LONG\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":40}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	zassert_equal(f.delayed_ms, 40000);
	zassert_false(f.pump[f.n_pump - 1].on);
	for (int i = 0; i < f.n_pump; i++) {
		zassert_false(f.pump[i].hold);
	}
	zassert_not_null(strstr(f.pub[find("cmd/ack", 0)].payload, "\"status\":\"done\""));
	zassert_equal(app.next_wake_s, 600);
}

ZTEST(cycle, test_button_wake_enters_service_mode_once_the_clock_is_known)
{
	mc_app_begin(&app, &rtc, &io, NULL, MC_WAKE_BUTTON, MC_CFG_LOADED);
	app.service_request_s = 60;
	f.log[0] = '\0';
	mc_cycle(&app);
	zassert_true(f.uptime >= 60000, "stayed up, uptime %u", (unsigned)f.uptime);
	zassert_not_null(strstr(f.pub[find("status", 1)].payload, "\"state\":\"service\""));
}

/*
 * Prints every message of a few rich cycles as `MCPUB <topic suffix> <payload>`.
 * scripts/test.py feeds them to the Python contract models (mc_core) that the gateway
 * and the API parse them with: the firmware must produce what the server accepts.
 */
static void dump(void)
{
	for (int i = 0; i < f.n_pub; i++) {
		printk("MCPUB %s %s\n", f.pub[i].suffix, f.pub[i].payload);
	}
}

ZTEST(cycle, test_dump_messages_for_the_contract_check)
{
	/* cold boot: broken sensor, low battery, cancel, rejected and accepted commands */
	f.adc[0] = 4095;
	f.batt = 3200;
	give(MC_IN_CONFIG, "{\"rev\":5,\"wake_interval_s\":900,\"slots\":["
			   "{\"slot\":0,\"module\":\"moisture_capacitive\",\"pin\":34,"
			   "\"cal\":{\"dry\":3000,\"wet\":1200}},"
			   "{\"slot\":1,\"module\":\"ds18b20\",\"pin\":27},"
			   "{\"slot\":2,\"module\":\"pump_relay\",\"pin\":25,\"max_run_s\":120,"
			   "\"min_pause_s\":0}]}");
	give(MC_IN_CMD, "{\"id\":\"RUN\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":5}}");
	give(MC_IN_CMD, "{\"id\":\"BAD\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":500}}");
	give(MC_IN_CMD, "{\"id\":\"OLD\",\"action\":\"pump.run\",\"exp\":1,\"args\":{\"slot\":2,\"seconds\":5}}");
	give(MC_IN_CMD, "{\"id\":\"LONG\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":90}}");
	give(MC_IN_CMD, "{\"id\":\"CXL\",\"action\":\"cmd.cancel\",\"exp\":1790414100,"
			"\"args\":{\"target\":\"LONG\"}}");
	give(MC_IN_CMD, "{\"id\":\"ID\",\"action\":\"device.identify\",\"exp\":1790414100}");
	cycle(MC_WAKE_POWER_ON, MC_CFG_LOADED);
	dump();

	/* a rejected config, then a held long run and its end */
	sleep_for(900);
	give(MC_IN_CONFIG, "{\"rev\":6,\"wake_interval_s\":900,\"slots\":["
			   "{\"slot\":2,\"module\":\"pump_relay\",\"pin\":34,\"max_run_s\":10}]}");
	give(MC_IN_CMD, "{\"id\":\"LONG2\",\"action\":\"pump.run\",\"exp\":1790414100,"
			"\"args\":{\"slot\":2,\"seconds\":100}}");
	cycle(MC_WAKE_TIMER, MC_CFG_LOADED);
	dump();
	sleep_for(100);
	cycle(MC_WAKE_PUMP_STOP, MC_CFG_LOADED);
	dump();
	zassert_true(f.n_pub > 0);
}
