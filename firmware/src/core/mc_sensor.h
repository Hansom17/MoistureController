/* Sensor readings and calibration (mqtt.md §4.2, §8.3). */
#ifndef MC_SENSOR_H
#define MC_SENSOR_H

#include "mc_config.h"
#include "mc_defs.h"

struct mc_reading {
	uint8_t slot;
	enum mc_type type;
	enum mc_sensor_err err;
	bool has_value;
	int32_t value_x10;      /* calibrated value in tenths of the unit */
	bool has_raw;
	int32_t raw;
};

/*
 * Raw ADC counts (12 bit) -> soil moisture in tenths of a percent.
 * 0 % = `dry` counts, 100 % = `wet` counts (capacitive sensors read lower when wet).
 *  - raw <= 0 or >= 4095: the input is pulled to a rail, nothing connected -> NO_SIGNAL
 *  - further than 15 % of the dry..wet span outside it -> OUT_OF_RANGE
 *  - otherwise clamped to 0..100 %.
 */
enum mc_sensor_err mc_moisture_convert(int32_t raw, int32_t dry, int32_t wet, int32_t *pct_x10);

/* Fills a reading for a moisture slot from a raw ADC value. */
void mc_moisture_reading(const struct mc_slot *s, int32_t raw, struct mc_reading *out);

const char *mc_type_name(enum mc_type t);
const char *mc_type_unit(enum mc_type t);
const char *mc_sensor_err_name(enum mc_sensor_err e);

/* Battery: Li-ion voltage at the ADC divider -> percent is the app's job; here only the limits. */
#define MC_BATT_LOW_MV 3300

#endif /* MC_SENSOR_H */
