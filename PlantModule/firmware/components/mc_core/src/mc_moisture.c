#include "mc_moisture.h"

#include "mc_interface.h"

uint8_t mc_moisture_convert(uint16_t raw, uint16_t cal_dry, uint16_t cal_wet, uint16_t adc_max, int16_t *value_x100)
{
    /* counts at the ADC limits: a floating or shorted input */
    if (raw == 0 || raw >= adc_max) {
        return MC_SENSOR_ERROR_NO_SIGNAL;
    }
    int32_t dry = cal_dry, wet = cal_wet;
    int32_t span = dry > wet ? dry - wet : wet - dry;
    int32_t margin = span * 15 / 100; /* more than 15 % of the span outside either point is out of range */
    int32_t lo = (dry < wet ? dry : wet) - margin;
    int32_t hi = (dry < wet ? wet : dry) + margin;
    if ((int32_t)raw < lo || (int32_t)raw > hi) {
        return MC_SENSOR_ERROR_OUT_OF_RANGE;
    }
    /* percent x 100, rounded to the nearest */
    int32_t num = ((int32_t)raw - dry) * 10000;
    int32_t den = wet - dry;
    int32_t v = (num >= 0) == (den > 0) ? (num + den / 2) / den : (num - den / 2) / den;
    if (v < 0) {
        v = 0;
    } else if (v > 10000) {
        v = 10000;
    }
    *value_x100 = (int16_t)v;
    return MC_SENSOR_ERROR_OK;
}
