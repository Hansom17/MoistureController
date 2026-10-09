/*
 * The BOOT button while the device is awake (ble.md §3): held 3 s the LED blinks fast ("keep
 * holding"), held 10 s is a factory reset. From deep sleep the same holds are measured at
 * boot (main.c); this covers every other moment: pairing window, WiFi attempt, a cycle.
 */
#include "hal.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(hal_button, LOG_LEVEL_INF);

static void (*on_factory_reset)(void);

static void monitor(void *a, void *b, void *c)
{
	int64_t pressed_at = 0;
	bool cue = false;
	enum hal_led before = HAL_LED_OFF;

	while (true) {
		k_msleep(50);
		if (!hal_board_button_pressed()) {
			if (cue) { /* released before 10 s: back to what the LED was showing */
				hal_board_led(before);
				cue = false;
			}
			pressed_at = 0;
			continue;
		}
		if (pressed_at == 0) {
			pressed_at = k_uptime_get();
			LOG_INF("BOOT pressed (3 s = keep-holding cue, 10 s = factory reset)");
			continue;
		}
		int64_t held = k_uptime_get() - pressed_at;

		if (held >= HAL_HOLD_FACTORY_RESET_MS) {
			LOG_WRN("BOOT held %d s: factory reset", (int)(held / 1000));
			if (on_factory_reset) {
				on_factory_reset();
			}
			pressed_at = 0;
		} else if (held >= HAL_HOLD_MAINTENANCE_MS && !cue) {
			before = hal_board_led_get();
			hal_board_led(HAL_LED_MAINTENANCE);
			cue = true;
			LOG_INF("BOOT held 3 s: keep holding for a factory reset");
		}
	}
}

K_THREAD_STACK_DEFINE(monitor_stack, 1536);
static struct k_thread monitor_thread;

void hal_button_start(void (*factory_reset)(void))
{
	on_factory_reset = factory_reset;
	k_thread_create(&monitor_thread, monitor_stack, K_THREAD_STACK_SIZEOF(monitor_stack), monitor,
			NULL, NULL, NULL, 7, 0, K_NO_WAIT);
	k_thread_name_set(&monitor_thread, "button");
}
