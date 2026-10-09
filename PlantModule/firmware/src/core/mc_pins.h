/* What the ESP32 silicon knows about a GPIO (the board rules are in mc_config.c). */
#ifndef MC_PINS_H
#define MC_PINS_H

#include <stdbool.h>

/* ADC unit (1 or 2) and its channel for a GPIO; false if the pin has no ADC. */
bool mc_pin_adc(int pin, int *unit, int *channel);

/* RTC GPIOs can keep an output level through deep sleep (ESP32: rtc_gpio_hold_en). */
bool mc_pin_rtc_capable(int pin);

#endif /* MC_PINS_H */
