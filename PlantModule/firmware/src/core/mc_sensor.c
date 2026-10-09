#include "mc_sensor.h"

#define ADC_MAX 4095

enum mc_sensor_err mc_moisture_convert(int32_t raw, int32_t dry, int32_t wet, int32_t *pct_x10)
{
	if (raw <= 0 || raw >= ADC_MAX) {
		return MC_SENSOR_NO_SIGNAL;
	}
	if (dry == wet) {
		return MC_SENSOR_OUT_OF_RANGE;
	}
	int64_t span = (int64_t)dry - wet;           /* > 0 for capacitive, < 0 if inverted */
	int64_t margin = (span < 0 ? -span : span) * 15 / 100;
	int64_t lo = (dry < wet ? dry : wet) - margin;
	int64_t hi = (dry > wet ? dry : wet) + margin;

	if (raw < lo || raw > hi) {
		return MC_SENSOR_OUT_OF_RANGE;
	}
	/* percent = (raw - dry) / (wet - dry), in tenths, rounded to nearest (either orientation) */
	int64_t num = ((int64_t)raw - dry) * 1000;
	int64_t den = (int64_t)wet - dry;

	if (den < 0) {
		num = -num;
		den = -den;
	}
	int64_t t = (num >= 0 ? num + den / 2 : num - den / 2) / den;

	if (t < 0) {
		t = 0;
	} else if (t > 1000) {
		t = 1000;
	}
	*pct_x10 = (int32_t)t;
	return MC_SENSOR_OK;
}

void mc_moisture_reading(const struct mc_slot *s, int32_t raw, struct mc_reading *out)
{
	out->slot = s->slot;
	out->type = MC_TYPE_SOIL_MOISTURE;
	out->has_raw = true;
	out->raw = raw;
	out->value_x10 = 0;
	out->err = mc_moisture_convert(raw, s->cal_dry, s->cal_wet, &out->value_x10);
	out->has_value = out->err == MC_SENSOR_OK;
}

const char *mc_type_name(enum mc_type t)
{
	switch (t) {
	case MC_TYPE_SOIL_MOISTURE: return "soil_moisture";
	case MC_TYPE_TEMPERATURE: return "temperature";
	case MC_TYPE_AIR_HUMIDITY: return "air_humidity";
	case MC_TYPE_WATER_LEVEL_OK: return "water_level_ok";
	}
	return "unknown";
}

const char *mc_type_unit(enum mc_type t)
{
	switch (t) {
	case MC_TYPE_SOIL_MOISTURE: return "%";
	case MC_TYPE_TEMPERATURE: return "\xC2\xB0" "C"; /* °C, UTF-8 */
	case MC_TYPE_AIR_HUMIDITY: return "%";
	case MC_TYPE_WATER_LEVEL_OK: return "bool";
	}
	return "";
}

const char *mc_sensor_err_name(enum mc_sensor_err e)
{
	switch (e) {
	case MC_SENSOR_NO_SIGNAL: return "no_signal";
	case MC_SENSOR_OUT_OF_RANGE: return "out_of_range";
	case MC_SENSOR_BUS_ERROR: return "bus_error";
	case MC_SENSOR_NOT_FOUND: return "not_found";
	default: return NULL;
	}
}
