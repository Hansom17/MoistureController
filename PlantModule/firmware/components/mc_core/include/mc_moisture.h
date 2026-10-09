#ifndef MC_MOISTURE_H
#define MC_MOISTURE_H

#include <stdint.h>

/* Two-point calibration (specs 5). Returns an mc_sensor_error_t.
 * On MC_SENSOR_ERROR_OK `*value_x100` is the moisture in percent x 100, clamped to 0..10000.
 * Polarity follows the points: dry > wet means small counts are wetter. */
uint8_t mc_moisture_convert(uint16_t raw, uint16_t cal_dry, uint16_t cal_wet, uint16_t adc_max, int16_t *value_x100);

#endif
