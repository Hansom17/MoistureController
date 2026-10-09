#include "mc_pins.h"

bool mc_pin_adc(int pin, int *unit, int *channel)
{
	/* ESP32 technical reference, "ADC": SAR ADC1 and SAR ADC2 channel to GPIO mapping */
	static const signed char adc1[40] = {[36] = 0, [37] = 1, [38] = 2, [39] = 3, [32] = 4,
					     [33] = 5, [34] = 6, [35] = 7};
	static const signed char adc2[40] = {[4] = 0, [0] = 1, [2] = 2, [15] = 3, [13] = 4,
					     [12] = 5, [14] = 6, [27] = 7, [25] = 8, [26] = 9};

	if (pin < 0 || pin > 39) {
		return false;
	}
	if (pin >= 32 && pin <= 39) {
		*unit = 1;
		*channel = adc1[pin];
		return true;
	}
	switch (pin) {
	case 0: case 2: case 4: case 12: case 13: case 14: case 15: case 25: case 26: case 27:
		*unit = 2;
		*channel = adc2[pin];
		return true;
	default:
		return false;
	}
}

bool mc_pin_rtc_capable(int pin)
{
	switch (pin) {
	case 0: case 2: case 4: case 12: case 13: case 14: case 15: case 25: case 26: case 27:
	case 32: case 33: case 34: case 35: case 36: case 37: case 38: case 39:
		return true;
	default:
		return false;
	}
}
