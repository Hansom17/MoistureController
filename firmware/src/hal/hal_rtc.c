#include "hal.h"

#include <esp_sleep.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/retained_mem.h>
#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>
#include <zephyr/sys/poweroff.h>

LOG_MODULE_REGISTER(hal_rtc, LOG_LEVEL_INF);

static const struct device *const retained = DEVICE_DT_GET(DT_ALIAS(retainedmemdevice));
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios);

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
	/* The BOOT button (GPIO 0, active low) wakes the device into service mode. */
	if (gpio_is_ready_dt(&button)) {
		gpio_pin_configure_dt(&button, GPIO_INPUT);
		gpio_pin_interrupt_configure_dt(&button, GPIO_INT_LEVEL_ACTIVE | GPIO_INT_WAKEUP);
	}
	esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
	LOG_INF("deep sleep for %d s", seconds);
	log_panic(); /* deferred log lines would be lost in deep sleep */
	sys_poweroff();
}
