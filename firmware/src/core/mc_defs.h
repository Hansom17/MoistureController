/*
 * Shared constants and enums. Hardware independent: everything in src/core is
 * unit-tested on QEMU (tests/core) and implements contracts/mqtt.md.
 */
#ifndef MC_DEFS_H
#define MC_DEFS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define MC_FW_VERSION "0.1.0"

/* mqtt.md §6.3 `limits`: what this firmware supports. */
#define MC_SLOTS_MAX       6
#define MC_MAX_RUN_S_HARD  300

#define MC_WAKE_INTERVAL_MIN_S 60
#define MC_WAKE_INTERVAL_MAX_S 86400
#define MC_WAKE_INTERVAL_DEFAULT_S 600

#define MC_ID_LEN 26 /* ULID */
#define MC_CMD_HISTORY 16 /* mqtt.md §5.2 */
#define MC_TELEMETRY_BUFFER 6 /* mqtt.md §4.2 */

/* mqtt.md §8.1 */
enum mc_module {
	MC_MOD_UNKNOWN = -1,
	MC_MOD_MOISTURE_CAPACITIVE,
	MC_MOD_MOISTURE_RESISTIVE,
	MC_MOD_PUMP_RELAY,
	MC_MOD_DS18B20,
	MC_MOD_SHT3X,
	MC_MOD_WATER_LEVEL_FLOAT,
	MC_MOD_COUNT,
};

enum mc_bus { MC_BUS_ADC, MC_BUS_GPIO_OUT, MC_BUS_GPIO_IN, MC_BUS_ONEWIRE, MC_BUS_I2C };

/* mqtt.md §8.3 */
enum mc_sensor_err {
	MC_SENSOR_OK = 0,
	MC_SENSOR_NO_SIGNAL,
	MC_SENSOR_OUT_OF_RANGE,
	MC_SENSOR_BUS_ERROR,
	MC_SENSOR_NOT_FOUND,
};

enum mc_type { MC_TYPE_SOIL_MOISTURE, MC_TYPE_TEMPERATURE, MC_TYPE_AIR_HUMIDITY,
	       MC_TYPE_WATER_LEVEL_OK };

/* mqtt.md §4.2 health.wake */
enum mc_wake { MC_WAKE_TIMER, MC_WAKE_PUMP_STOP, MC_WAKE_BUTTON, MC_WAKE_POWER_ON,
	       MC_WAKE_RESET };

#endif /* MC_DEFS_H */
