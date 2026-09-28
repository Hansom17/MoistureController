/*
 * Copyright (c) 2012-2014 Wind River Systems, Inc.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/adc.h>
#include <esp32/rom/ets_sys.h>

#define LED0_NODE DT_ALIAS(led0)

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static const struct adc_dt_spec moisture_adc = ADC_DT_SPEC_GET(DT_PATH(zephyr_user));

int main(void)
{
	int16_t sample;
	struct adc_sequence sequence = {
		.buffer = &sample,
		.buffer_size = sizeof(sample),
	};

	if (!gpio_is_ready_dt(&led)) {
		return 0;
	}

	if (gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE) < 0) {
		return 0;
	}

	if (!adc_is_ready_dt(&moisture_adc)) {
		ets_printf("Moisture ADC not ready\n");
		return 0;
	}

	if (adc_channel_setup_dt(&moisture_adc) < 0) {
		ets_printf("Failed to set up moisture ADC channel\n");
		return 0;
	}

	while (1) {
		gpio_pin_toggle_dt(&led);

		(void)adc_sequence_init_dt(&moisture_adc, &sequence);

		if (adc_read_dt(&moisture_adc, &sequence) < 0) {
			ets_printf("Moisture ADC read failed\n");
		} else {
			ets_printf("Moisture raw: %d\n", sample);
		}

		k_msleep(500);
	}

	return 0;
}
