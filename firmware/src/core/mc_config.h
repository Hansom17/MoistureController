/*
 * Slot table and desired/reported config (mqtt.md §6). Validation mirrors
 * core/src/mc_core/pins.py (validate_config); the firmware is the final authority.
 */
#ifndef MC_CONFIG_H
#define MC_CONFIG_H

#include "mc_defs.h"
#include "mc_json.h"

#define MC_CAL_DRY_DEFAULT 3000
#define MC_CAL_WET_DEFAULT 1200

struct mc_slot {
	uint8_t slot;           /* index 0..MC_SLOTS_MAX-1 */
	enum mc_module module;
	int16_t pin;            /* -1 = not given */
	int16_t addr;           /* I2C address, -1 = not given */
	int32_t cal_dry;        /* ADC counts at 0 % / 100 % */
	int32_t cal_wet;
	bool active_high;       /* actuators */
	int32_t max_run_s;      /* actuators; -1 = not given */
	int32_t min_pause_s;    /* actuators; 0 = none */
};

struct mc_config {
	int32_t rev;
	int32_t wake_interval_s;
	uint8_t n;              /* slots in document order */
	struct mc_slot slots[MC_SLOTS_MAX];
};

/* mqtt.md §6.3 `error`. `code` is one of the §8.2 strings. */
struct mc_error {
	int16_t slot;           /* -1 = not slot specific */
	const char *code;
	char detail[56];
};

struct mc_module_info {
	const char *name;
	enum mc_bus bus;
	bool actuator;
	bool detectable;
};

const struct mc_module_info *mc_module_info(enum mc_module m);
enum mc_module mc_module_from_name(const char *name);
bool mc_module_is_moisture(enum mc_module m);

/* Empty config: rev 0, default interval, no slots. */
void mc_config_init(struct mc_config *c);

/* The slot with index `slot`, or NULL. */
const struct mc_slot *mc_config_slot(const struct mc_config *c, int slot);

/* Whole-document validation (mqtt.md §6.2); reports the first problem. */
bool mc_config_validate(const struct mc_config *c, struct mc_error *err);

/*
 * Parses a config/desired payload. `buf` is modified (in-place JSON parsing).
 * Returns false and fills `err` if it isn't a usable document; the result still
 * has to pass mc_config_validate().
 */
bool mc_config_parse(char *buf, size_t len, struct mc_config *out, struct mc_error *err);

/* Writes the config members (rev, wake_interval_s, slots) into an open object. */
void mc_config_write(struct mc_jw *w, const struct mc_config *c);
/* The same without `rev` (wake_interval_s, slots). */
void mc_config_write_body(struct mc_jw *w, const struct mc_config *c);

/* True if both describe the same slots and settings (rev ignored). */
bool mc_config_same(const struct mc_config *a, const struct mc_config *b);

#endif /* MC_CONFIG_H */
