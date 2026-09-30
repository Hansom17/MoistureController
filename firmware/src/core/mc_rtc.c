#include "mc_rtc.h"

#include <string.h>
#include <zephyr/sys/crc.h>

static uint32_t crc_of(const struct mc_rtc *r)
{
	return crc32_ieee((const uint8_t *)r, offsetof(struct mc_rtc, crc));
}

void mc_rtc_init(struct mc_rtc *r)
{
	memset(r, 0, sizeof(*r));
	r->magic = MC_RTC_MAGIC;
	r->cfg_rev_published = -1;
	mc_hist_init(&r->hist);
	for (int i = 0; i < MC_SLOTS_MAX; i++) {
		r->sensor_ok[i] = true;
	}
}

void mc_rtc_seal(struct mc_rtc *r)
{
	r->magic = MC_RTC_MAGIC;
	r->crc = crc_of(r);
}

bool mc_rtc_valid(const struct mc_rtc *r)
{
	return r->magic == MC_RTC_MAGIC && r->crc == crc_of(r);
}

uint32_t mc_rtc_next_seq(struct mc_rtc *r)
{
	return ++r->seq;
}

void mc_tbuf_push(struct mc_rtc *r, const struct mc_tel *t)
{
	if (r->t_count == MC_TELEMETRY_BUFFER) {
		r->t_head = (uint8_t)((r->t_head + 1) % MC_TELEMETRY_BUFFER);
		r->t_count--;
	}
	r->tel[(r->t_head + r->t_count) % MC_TELEMETRY_BUFFER] = *t;
	r->t_count++;
}

const struct mc_tel *mc_tbuf_oldest(const struct mc_rtc *r)
{
	return r->t_count ? &r->tel[r->t_head] : NULL;
}

void mc_tbuf_drop_oldest(struct mc_rtc *r)
{
	if (r->t_count) {
		r->t_head = (uint8_t)((r->t_head + 1) % MC_TELEMETRY_BUFFER);
		r->t_count--;
	}
}

void mc_pend_push(struct mc_rtc *r, const struct mc_ack *a)
{
	if (r->pend_n == MC_PENDING_ACKS) { /* oldest answer dropped: the server expires it itself */
		mc_pend_drop_first(r);
	}
	r->pend[r->pend_n++] = *a;
}

void mc_pend_drop_first(struct mc_rtc *r)
{
	if (r->pend_n) {
		memmove(&r->pend[0], &r->pend[1], sizeof(r->pend[0]) * (r->pend_n - 1));
		r->pend_n--;
	}
}

int32_t mc_next_wake_s(const struct mc_ctx *ctx, int32_t batt_mv)
{
	int64_t s = ctx->cfg->wake_interval_s;

	if (batt_mv > 0 && batt_mv < MC_BATT_LOW_MV) {
		s *= 3;
		if (s > MC_WAKE_INTERVAL_MAX_S) {
			s = MC_WAKE_INTERVAL_MAX_S;
		}
	}
	int32_t stop = mc_pump_next_stop_in(ctx);

	if (stop >= 0 && stop < s) {
		s = stop; /* wake just for switching the pump off */
	}
	return (int32_t)s;
}
