#include "hal.h"

#include <zephyr/device.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <driver/rtc_io.h>

#include "mc_pins.h"

LOG_MODULE_REGISTER(hal_board, LOG_LEVEL_INF);

#define ADC_SAMPLES 8
#define ADC_RESOLUTION 12
#define ADC_FULL_SCALE_MV 3100 /* ADC_GAIN_1_4 on the ESP32: about 3.1 V for 4095 counts */

static const struct device *const gpio_dev[2] = {DEVICE_DT_GET(DT_NODELABEL(gpio0)),
						 DEVICE_DT_GET(DT_NODELABEL(gpio1))};
static const struct device *const adc_dev[2] = {DEVICE_DT_GET(DT_NODELABEL(adc0)),
						DEVICE_DT_GET(DT_NODELABEL(adc1))};
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios);

int hal_board_init(void)
{
	for (int i = 0; i < 2; i++) {
		if (!device_is_ready(gpio_dev[i]) || !device_is_ready(adc_dev[i])) {
			LOG_ERR("gpio/adc %d not ready", i);
			return -ENODEV;
		}
	}
	if (gpio_is_ready_dt(&led)) {
		gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	}
	if (gpio_is_ready_dt(&button)) {
		gpio_pin_configure_dt(&button, GPIO_INPUT);
	}
	return 0;
}

/* Raw counts of one moisture sensor pin (averaged); runtime channel binding. */
int hal_board_read_adc(int pin, int32_t *raw)
{
	int unit, channel;

	if (!mc_pin_adc(pin, &unit, &channel)) {
		return -EINVAL;
	}
	const struct device *dev = adc_dev[unit - 1];
	struct adc_channel_cfg cfg = {
		.gain = ADC_GAIN_1_4,
		.reference = ADC_REF_INTERNAL,
		.acquisition_time = ADC_ACQ_TIME_DEFAULT,
		.channel_id = channel,
	};
	int err = adc_channel_setup(dev, &cfg);

	if (err < 0) {
		return err;
	}
	int32_t sum = 0;

	for (int i = 0; i < ADC_SAMPLES; i++) {
		int16_t sample = 0;
		struct adc_sequence seq = {
			.channels = BIT(channel),
			.buffer = &sample,
			.buffer_size = sizeof(sample),
			.resolution = ADC_RESOLUTION,
		};

		err = adc_read(dev, &seq);
		if (err < 0) {
			return err;
		}
		sum += sample;
		k_busy_wait(200);
	}
	*raw = sum / ADC_SAMPLES;
	return 0;
}

int32_t hal_board_battery_mv(void)
{
	int32_t raw;

	if (CONFIG_MC_BATT_ADC_PIN < 0 || hal_board_read_adc(CONFIG_MC_BATT_ADC_PIN, &raw) < 0) {
		return 0; /* unknown */
	}
	int32_t pin_mv = raw * ADC_FULL_SCALE_MV / 4095;

	return pin_mv * CONFIG_MC_BATT_DIVIDER_PERCENT / 100;
}

/*
 * Drives a pump relay. With `hold_through_sleep` the level is latched in the RTC domain
 * so the pump keeps running while the chip is in deep sleep (the caller schedules the
 * wake that ends the run). Releasing a held pin happens on the next call for that pin.
 */
void hal_board_pump(int pin, bool active_high, bool on, bool hold_through_sleep)
{
	int level = (on == active_high) ? 1 : 0;

	if (mc_pin_rtc_capable(pin)) {
		rtc_gpio_hold_dis(pin); /* harmless if it wasn't held */
	}
	if (on && hold_through_sleep) {
		if (!mc_pin_rtc_capable(pin)) {
			LOG_ERR("GPIO %d cannot hold through deep sleep", pin);
		} else {
			rtc_gpio_init(pin);
			rtc_gpio_set_direction(pin, RTC_GPIO_MODE_OUTPUT_ONLY);
			rtc_gpio_set_level(pin, level);
			rtc_gpio_hold_en(pin);
			return;
		}
	}
	if (mc_pin_rtc_capable(pin)) {
		rtc_gpio_deinit(pin); /* back to the digital GPIO matrix */
	}
	const struct device *dev = gpio_dev[pin >= 32];

	gpio_pin_configure(dev, pin % 32, GPIO_OUTPUT);
	gpio_pin_set_raw(dev, pin % 32, level);
}

void hal_board_identify(int32_t seconds)
{
	for (int32_t i = 0; i < seconds * 2; i++) {
		gpio_pin_toggle_dt(&led);
		k_msleep(250);
	}
	gpio_pin_set_dt(&led, 0);
}

bool hal_board_button_pressed(void)
{
	return gpio_is_ready_dt(&button) && gpio_pin_get_dt(&button) > 0;
}

/* --- LED patterns (pairing feedback) and the BOOT button hold -------------------------------------- */

static enum hal_led led_pattern;
static void led_tick(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(led_work, led_tick);

static void led_tick(struct k_work *work)
{
	static int phase;

	switch (led_pattern) {
	case HAL_LED_PAIRING: /* slow blink */
		gpio_pin_set_dt(&led, (phase++ / 5) & 1);
		k_work_reschedule(&led_work, K_MSEC(100));
		break;
	case HAL_LED_MAINTENANCE: /* fast blink */
		gpio_pin_set_dt(&led, phase++ & 1);
		k_work_reschedule(&led_work, K_MSEC(100));
		break;
	case HAL_LED_CONNECTED: /* solid */
		gpio_pin_set_dt(&led, 1);
		break;
	default:
		gpio_pin_set_dt(&led, 0);
	}
}

void hal_board_led(enum hal_led pattern)
{
	led_pattern = pattern;
	k_work_reschedule(&led_work, K_NO_WAIT);
}

/* Holds are measured while the button stays pressed; the LED lights at 3 s and blinks at 10 s. */
int32_t hal_board_button_hold_ms(int32_t limit_ms)
{
	int64_t start = k_uptime_get();
	int32_t held = 0;

	while (hal_board_button_pressed() && held < limit_ms) {
		k_msleep(50);
		held = (int32_t)(k_uptime_get() - start);
		if (held >= HAL_HOLD_FACTORY_RESET_MS) {
			gpio_pin_toggle_dt(&led);
		} else if (held >= HAL_HOLD_MAINTENANCE_MS) {
			gpio_pin_set_dt(&led, 1);
		}
	}
	gpio_pin_set_dt(&led, 0);
	return held;
}

/* --- heap statistics ----------------------------------------------------------------------------- */

extern struct k_heap _system_heap;

void hal_heap_log(const char *where)
{
	struct sys_memory_stats st;

	if (sys_heap_runtime_stats_get(&_system_heap.heap, &st) == 0) {
		LOG_INF("heap %s: %u free, %u used, %u peak", where, (unsigned)st.free_bytes,
			(unsigned)st.allocated_bytes, (unsigned)st.max_allocated_bytes);
	}
}
