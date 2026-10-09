/* Encoders for everything the device publishes (mqtt.md §4, §5.3, §6.3). */
#ifndef MC_PAYLOAD_H
#define MC_PAYLOAD_H

#include "mc_cmd.h"
#include "mc_config.h"
#include "mc_json.h"
#include "mc_sensor.h"

/* §4.1 status. Each returns the payload length or -1 (buffer too small). */
int mc_enc_status_online(char *buf, size_t cap, uint32_t boot);
int mc_enc_status_sleeping(char *buf, size_t cap, int32_t next_wake_s);
int mc_enc_status_offline(char *buf, size_t cap); /* the Last Will */
int mc_enc_status_service(char *buf, size_t cap, int32_t until_s);

/* §4.2 telemetry */
struct mc_health {
	int32_t batt_mv;
	int32_t rssi;
	enum mc_wake wake;
	int32_t cycle_ms;       /* -1 = omit */
	int32_t wifi_ms;        /* -1 = omit */
};

struct mc_tel {
	uint32_t seq;
	int64_t ts;             /* 0 = clock not synced: omitted */
	int32_t cfg_rev;
	uint8_t n;
	struct mc_reading r[MC_SLOTS_MAX];
	struct mc_health h;
};

int mc_enc_telemetry(char *buf, size_t cap, const struct mc_tel *t);

/* §4.3 event */
enum mc_event_kind { MC_EV_BOOT, MC_EV_SAFETY_STOP, MC_EV_SENSOR_FAULT, MC_EV_LOW_BATTERY,
		     MC_EV_CONFIG_ERROR, MC_EV_SERVICE_MODE };

struct mc_event {
	uint32_t seq;
	int64_t ts;             /* 0 = omit */
	enum mc_event_kind kind;
	int16_t slot;           /* -1 = omit */
	char detail[32];        /* "" = omit */
};

int mc_enc_event(char *buf, size_t cap, const struct mc_event *e);

/* §5.3 cmd/ack */
int mc_enc_ack(char *buf, size_t cap, const struct mc_ack *a);

/* §6.3 config/state */
enum mc_cfg_result { MC_CFG_APPLIED, MC_CFG_REJECTED, MC_CFG_BOOT };

/* `err`/`rejected_rev` only for MC_CFG_REJECTED. `cfg` is what is running. */
int mc_enc_config_state(char *buf, size_t cap, const struct mc_config *cfg,
			enum mc_cfg_result result, int32_t rejected_rev,
			const struct mc_error *err);

const char *mc_wake_name(enum mc_wake w);

#endif /* MC_PAYLOAD_H */
