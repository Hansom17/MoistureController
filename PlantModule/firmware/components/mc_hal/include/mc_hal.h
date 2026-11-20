#ifndef MC_HAL_H
#define MC_HAL_H

/* ESP32-C6 hardware layer under mc_core. Everything here is called from the application task only (the timers
 * and the button poller post events into the application queue instead). */

#include <stdbool.h>
#include <stdint.h>

#include "mc_core.h"
#include "mc_factory.h"

/* The application's event queue entry point, implemented by main/mc_app.c; safe from any task. */
void mc_app_post(const mc_event_t *ev);

/* ---- sleeping (hal_sleep.c) ----------------------------------------------------------------------------------- */

/* True when this boot is the wake-up from a deep sleep (and the RTC memory is valid). */
bool mc_hal_sleep_is_deep_wake(void);

/* Adds the deep-sleep wake information (RTC counters, wake reason) to the boot event. */
void mc_hal_sleep_boot(mc_boot_t *b);

/* Light sleep on or off, following mc_core_sleep_allowed() (automatic power management). */
void mc_hal_sleep_apply(mc_sleep_t allowed);

/* Deep sleep for `ms`; the pump and sensor-supply pads are held. Does not return. */
void mc_hal_deep_sleep(uint32_t ms, uint16_t seq, const mc_config_t *cfg);

/* ---- storage (hal_store.c) ---------------------------------------------------------------------------- */

/* Initialises NVS. Returns false when it had to be erased and the stored state is gone. */
bool mc_hal_store_init(void);

/* Reads the `factory` partition. False for invalid data (the core then enters safe mode). */
bool mc_hal_factory_read(mc_factory_t *out);

/* Everything the BOOT event needs except the factory result; increments the boot counter. */
void mc_hal_boot_info(mc_boot_t *out);

bool mc_hal_config_store(const mc_config_t *cfg);
void mc_hal_diag_store(const mc_diag_t *diag);

/* Factory reset: forget the configuration and the "has booted before" flag. Counters stay. */
void mc_hal_state_erase(void);

/* ---- outputs, LED, button (hal_gpio.c) ------------------------------------------------------------------ */

void mc_hal_gpio_init(const mc_board_t *board);

/* Sets every pump slot of the configuration to its off level (and turns it into an output). Also used for the
 * "all outputs off" action and after a configuration change. */
void mc_hal_outputs_off(const mc_config_t *cfg);
void mc_hal_pump_set(uint8_t port, bool active_high, bool on);

void mc_hal_led_set(mc_led_t pattern);

/* Hold or release the pump pads and the sensor supply pad through deep sleep. */
void mc_hal_outputs_hold(const mc_config_t *cfg, bool hold);

/* Switches the sensor supply; a no-op on boards without a switched rail. */
void mc_hal_sensor_power(bool on);

/* Starts the 10 ms poll that decodes the button and posts BTN events. */
void mc_hal_button_start(void);

/* ---- analog (hal_adc.c) ---------------------------------------------------------------------------------- */

void mc_hal_adc_init(const mc_board_t *board);

/* Average of `samples` readings of the port, 12 bit. False when the port has no ADC channel. */
bool mc_hal_adc_read_port(uint8_t port, uint8_t samples, uint16_t *raw);

/* Voltage at the battery divider pin in mV (calibrated ADC, 8 conversions averaged). The core applies the divider
 * ratio, the per-device calibration and the filter. False when the board has no battery input or the read failed. */
bool mc_hal_battery_pin_mv(uint16_t *mv);

/* ---- timers (hal_timers.c) -------------------------------------------------------------------------------- */

/* The Zigbee layer mirrors every armed timer into its scheduler so that its sleep never overshoots one. */
void mc_hal_set_wake_hooks(void (*at)(uint8_t key, uint32_t ms), void (*cancel)(uint8_t key));

void mc_hal_timers_init(void);
void mc_hal_timer_arm(mc_timer_t id, uint8_t arg, uint32_t delay_ms);
void mc_hal_timer_cancel(mc_timer_t id, uint8_t arg);

/* Milliseconds since boot (wraps after 49 days; the core uses serial arithmetic). */
uint32_t mc_hal_now_ms(void);

#endif
