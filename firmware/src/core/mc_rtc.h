/*
 * State that must survive deep sleep (kept in RTC slow RAM, see the board overlay):
 * counters, command history, pump holds, the telemetry buffer. Validated with a magic
 * and CRC after every wake; anything else means power was lost -> start fresh.
 */
#ifndef MC_RTC_H
#define MC_RTC_H

#include "mc_cmd.h"
#include "mc_payload.h"

#define MC_RTC_MAGIC 0x4D43A002u /* "MC", layout version 2 */
#define MC_PENDING_ACKS 6        /* acks not yet handed to the broker */

struct mc_rtc {
	uint32_t magic;
	uint32_t seq;             /* last used telemetry/event seq (shared counter, §4.3) */
	uint32_t boot;            /* boot counter, deep-sleep wakes included */
	int32_t cfg_rev_published; /* config/state was last published for this rev (-1 = never) */
	int64_t wall_at_sleep;    /* Unix time estimate when going to sleep; 0 = unknown */
	uint32_t slept_s;         /* how long the timer was set for */
	uint32_t wakes_since_sync;
	uint32_t last_cycle_ms;   /* duration of the previous wake cycle */
	int32_t last_rssi;        /* for buffered telemetry whose cycle never connected */
	uint8_t pend_n;
	struct mc_ack pend[MC_PENDING_ACKS]; /* publish order; removed after PUBACK */
	bool low_batt_reported;
	bool sensor_ok[MC_SLOTS_MAX]; /* for one sensor_fault event per transition */
	struct mc_pump_state pump[MC_SLOTS_MAX];
	struct mc_cmd_hist hist;
	uint8_t t_head;           /* oldest entry */
	uint8_t t_count;
	struct mc_tel tel[MC_TELEMETRY_BUFFER];
	uint32_t crc;
};

/* Acks waiting to be published (a cycle may end before the broker took them). */
void mc_pend_push(struct mc_rtc *r, const struct mc_ack *a);
void mc_pend_drop_first(struct mc_rtc *r);

/* Fresh state after a power loss. */
void mc_rtc_init(struct mc_rtc *r);
/* Call before sleeping; afterwards mc_rtc_valid() holds. */
void mc_rtc_seal(struct mc_rtc *r);
bool mc_rtc_valid(const struct mc_rtc *r);

uint32_t mc_rtc_next_seq(struct mc_rtc *r);

/* Telemetry ring: a record is pushed first, then everything buffered is published in order. */
void mc_tbuf_push(struct mc_rtc *r, const struct mc_tel *t); /* drops the oldest when full */
const struct mc_tel *mc_tbuf_oldest(const struct mc_rtc *r); /* NULL if empty */
void mc_tbuf_drop_oldest(struct mc_rtc *r);

/*
 * The interval to sleep: the configured one, lengthened on low battery (x3 below
 * MC_BATT_LOW_MV), shortened to end a held pump run.
 */
int32_t mc_next_wake_s(const struct mc_ctx *ctx, int32_t batt_mv);

#endif /* MC_RTC_H */
