/*
 * One wake cycle (mqtt.md §7, Firmware_Specs "Wake cycle sequence"). All hardware and
 * network access goes through `struct mc_io`, so the exact sequence of publishes,
 * the buffering and the sleep decision run in unit tests against a fake broker.
 */
#ifndef MC_CYCLE_H
#define MC_CYCLE_H

#include "mc_cmd.h"
#include "mc_config.h"
#include "mc_payload.h"
#include "mc_rtc.h"

/* Messages the broker delivers to the device (§3). */
enum mc_in_kind { MC_IN_CMD, MC_IN_CONFIG };
typedef void (*mc_in_fn)(void *cb_user, enum mc_in_kind kind, const uint8_t *payload,
			 size_t len);

struct mc_io {
	/* --- hardware ---------------------------------------------------------------------- */
	int (*read_adc)(void *u, const struct mc_slot *s, int32_t *raw); /* <0: driver error */
	int32_t (*battery_mv)(void *u);
	/* `hold`: keep the output latched through deep sleep (a long run). */
	void (*pump_set)(void *u, const struct mc_slot *s, bool on, bool hold);
	void (*delay_ms)(void *u, int32_t ms);
	void (*identify)(void *u, int32_t seconds);
	uint32_t (*uptime_ms)(void *u); /* since this boot (deep-sleep wakes reset it) */

	/* --- clock and storage ---------------------------------------------------------------- */
	int (*sntp)(void *u, int64_t *unix_s); /* <0: no sync possible */
	int (*save_config)(void *u, const struct mc_config *c);

	/* --- network -------------------------------------------------------------------------------- */
	/*
	 * WiFi up, MQTT connected (persistent session, Last Will = `will` on status, retained),
	 * subscribed to cmd and config/desired. <0: could not connect.
	 */
	int (*connect)(void *u, const char *will, size_t will_len, int32_t *rssi,
		       int32_t *wifi_ms);
	/* QoS 1: returns 0 once the broker acknowledged it, <0 if the connection is gone. */
	int (*publish)(void *u, const char *suffix, const char *payload, size_t len, bool retain);
	/* Lets the broker deliver queued messages; calls `cb` for each one. */
	void (*poll)(void *u, int32_t timeout_ms, mc_in_fn cb, void *cb_user);
	void (*disconnect)(void *u);

	void (*log)(void *u, const char *msg); /* optional */
};

/* Time spent listening for queued messages after subscribing (mqtt.md §7). */
#define MC_DRAIN_MS 300
/* Re-sync the clock every N wakes (the RTC oscillator drifts). */
#define MC_SNTP_EVERY_WAKES 6

struct mc_app {
	struct mc_config cfg;            /* active config; set by the caller before mc_app_begin */
	struct mc_rtc *rtc;
	const struct mc_io *io;
	void *io_user;

	enum mc_wake wake;
	bool cold_boot;
	bool config_invalid_at_boot;     /* stored config was unusable: a default is active */
	int64_t clock_base_s;            /* Unix time at uptime 0 of this boot; 0 = unknown */
	int64_t service_until;           /* > 0: stay connected until then (service mode) */
	int32_t service_request_s;       /* > 0: enter service mode for this long once the clock is known */
	struct mc_ctx ctx;

	/* results */
	int32_t next_wake_s;
	bool reboot;                     /* a device.reboot was acknowledged */
};

/* What the caller found in persistent storage. */
enum mc_cfg_load {
	MC_CFG_LOADED,  /* app->cfg holds the stored (and validated) config */
	MC_CFG_MISSING, /* first boot: nothing stored yet, the empty default is used */
	MC_CFG_CORRUPT, /* stored but unusable: the default is used and a config_error is reported */
};

/*
 * Call once per boot. `rtc` is the retained state as found (validated here: anything
 * invalid means power was lost, so it is reset and this counts as a cold boot).
 */
void mc_app_begin(struct mc_app *a, struct mc_rtc *rtc, const struct mc_io *io, void *io_user,
		  enum mc_wake wake, enum mc_cfg_load cfg);

/* Runs the whole cycle and seals the retained state; then the caller puts the device to sleep. */
void mc_cycle(struct mc_app *a);

#endif /* MC_CYCLE_H */
