#include "hal.h"

#include <esp_sleep.h>
#include <driver/rtc_io.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/retained_mem.h>
#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>
#include <zephyr/sys/poweroff.h>

LOG_MODULE_REGISTER(hal_rtc, LOG_LEVEL_INF);

static const struct device *const retained = DEVICE_DT_GET(DT_ALIAS(retainedmemdevice));

/* The overlay reserves 0x1000 bytes of RTC slow RAM for it. */
BUILD_ASSERT(sizeof(struct mc_rtc) <= 0x1000, "cycle state does not fit the retained RAM");

void hal_rtc_load(struct mc_rtc *r)
{
	if (!device_is_ready(retained) || retained_mem_size(retained) < sizeof(*r) ||
	    retained_mem_read(retained, 0, (uint8_t *)r, sizeof(*r)) < 0) {
		memset(r, 0, sizeof(*r)); /* invalid CRC: treated as a power loss */
	}
}

/* A new pairing starts from scratch: an all-zero state fails its CRC, which reads as a power loss. */
void hal_rtc_clear(void)
{
	static const uint8_t zeros[64];

	if (!device_is_ready(retained)) {
		return;
	}
	for (off_t off = 0; off < (off_t)sizeof(struct mc_rtc); off += sizeof(zeros)) {
		retained_mem_write(retained, off, zeros,
				   MIN(sizeof(zeros), sizeof(struct mc_rtc) - (size_t)off));
	}
}

void hal_rtc_store(const struct mc_rtc *r)
{
	if (device_is_ready(retained) && retained_mem_size(retained) >= sizeof(*r)) {
		retained_mem_write(retained, 0, (const uint8_t *)r, sizeof(*r));
	} else {
		LOG_ERR("retained memory too small for the cycle state");
	}
}

enum mc_wake hal_wake_cause(const struct mc_rtc *r)
{
	uint32_t causes = esp_sleep_get_wakeup_causes();

	if (causes & BIT(ESP_SLEEP_WAKEUP_TIMER)) {
		/* a timer wake at the end of a held pump run is a pump_stop wake */
		for (int i = 0; i < MC_SLOTS_MAX; i++) {
			if (r->pump[i].run_ends_at > 0 && r->wall_at_sleep > 0 &&
			    r->wall_at_sleep + r->slept_s >= r->pump[i].run_ends_at) {
				return MC_WAKE_PUMP_STOP;
			}
		}
		return MC_WAKE_TIMER;
	}
	if (causes & (BIT(ESP_SLEEP_WAKEUP_EXT0) | BIT(ESP_SLEEP_WAKEUP_EXT1) |
		      BIT(ESP_SLEEP_WAKEUP_GPIO))) {
		return MC_WAKE_BUTTON;
	}
	return MC_WAKE_POWER_ON;
}

void hal_sleep(int32_t seconds)
{
	/*
	 * The BOOT button (GPIO 0, active low, an RTC pin) wakes the device from deep sleep:
	 * ext0 is the ESP32's deep-sleep wake-up on an RTC GPIO (a plain GPIO interrupt does not
	 * work there). EN, the reset pin, restarts the device at any time.
	 */
	rtc_gpio_pullup_en(GPIO_NUM_0);
	rtc_gpio_pulldown_dis(GPIO_NUM_0);
	esp_err_t err = esp_sleep_enable_ext0_wakeup(GPIO_NUM_0, 0);

	if (err != ESP_OK) {
		LOG_ERR("BOOT button wake-up not available: %d", (int)err);
	}
	esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
	LOG_INF("deep sleep for %d s (BOOT or EN wakes the device)", seconds);
	hal_board_led(HAL_LED_OFF);
	k_msleep(30); /* the LED is switched off by a work item */
	log_panic(); /* deferred log lines would be lost in deep sleep */
	sys_poweroff();
}
