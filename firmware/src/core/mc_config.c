#include "mc_config.h"

#include <errno.h>
#include <string.h>
#include <zephyr/sys/util.h>
#include <zephyr/data/json.h>
#include <zephyr/sys/printk.h>

/* --- modules and pin rules (pins.py) ------------------------------------------ */

static const struct mc_module_info modules[MC_MOD_COUNT] = {
	[MC_MOD_MOISTURE_CAPACITIVE] = {"moisture_capacitive", MC_BUS_ADC, false, false},
	[MC_MOD_MOISTURE_RESISTIVE] = {"moisture_resistive", MC_BUS_ADC, false, false},
	[MC_MOD_PUMP_RELAY] = {"pump_relay", MC_BUS_GPIO_OUT, true, false},
	[MC_MOD_DS18B20] = {"ds18b20", MC_BUS_ONEWIRE, false, true},
	[MC_MOD_SHT3X] = {"sht3x", MC_BUS_I2C, false, true},
	[MC_MOD_WATER_LEVEL_FLOAT] = {"water_level_float", MC_BUS_GPIO_IN, false, false},
};

#define BIT64_(n) ((uint64_t)1 << (n))
#define MASK_OF(...) mask_of((const uint8_t[]){__VA_ARGS__}, \
			     sizeof((const uint8_t[]){__VA_ARGS__}))

static uint64_t mask_of(const uint8_t *pins, size_t n)
{
	uint64_t m = 0;

	for (size_t i = 0; i < n; i++) {
		m |= BIT64_(pins[i]);
	}
	return m;
}

static const char *reserved_reason(int pin)
{
	switch (pin) {
	case 0: return "BOOT button / strapping";
	case 1: return "UART0 TX";
	case 2: return "onboard LED";
	case 3: return "UART0 RX";
	case 6: case 7: case 8: case 9: case 10: case 11: return "SPI flash";
	default: return NULL;
	}
}

static uint64_t input_only_mask(void)
{
	return MASK_OF(34, 35, 36, 39);
}

static uint64_t adc_mask(void)
{
	return MASK_OF(32, 33, 34, 35, 36, 39, 4, 12, 13, 14, 15, 25, 26, 27);
}

/* GPIOs broken out on the DevKit V1 header. */
static uint64_t exposed_mask(void)
{
	return MASK_OF(4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33, 34,
		       35, 36, 39);
}

static uint64_t allowed_pins(enum mc_bus bus)
{
	switch (bus) {
	case MC_BUS_ADC:
		return adc_mask();
	case MC_BUS_GPIO_OUT:
	case MC_BUS_ONEWIRE:
		return exposed_mask() & ~input_only_mask();
	case MC_BUS_GPIO_IN:
		return exposed_mask();
	default:
		return 0;
	}
}

const struct mc_module_info *mc_module_info(enum mc_module m)
{
	return (m >= 0 && m < MC_MOD_COUNT) ? &modules[m] : NULL;
}

enum mc_module mc_module_from_name(const char *name)
{
	if (name == NULL) {
		return MC_MOD_UNKNOWN;
	}
	for (int i = 0; i < MC_MOD_COUNT; i++) {
		if (strcmp(modules[i].name, name) == 0) {
			return (enum mc_module)i;
		}
	}
	return MC_MOD_UNKNOWN;
}

bool mc_module_is_moisture(enum mc_module m)
{
	return m == MC_MOD_MOISTURE_CAPACITIVE || m == MC_MOD_MOISTURE_RESISTIVE;
}

/* --- config ---------------------------------------------------------------------- */

void mc_config_init(struct mc_config *c)
{
	memset(c, 0, sizeof(*c));
	c->wake_interval_s = MC_WAKE_INTERVAL_DEFAULT_S;
}

const struct mc_slot *mc_config_slot(const struct mc_config *c, int slot)
{
	for (int i = 0; i < c->n; i++) {
		if (c->slots[i].slot == slot) {
			return &c->slots[i];
		}
	}
	return NULL;
}

#define FAIL(e, slot_, code_, ...)                                                   \
	do {                                                                         \
		(e)->slot = (int16_t)(slot_);                                        \
		(e)->code = (code_);                                                 \
		snprintk((e)->detail, sizeof((e)->detail), "" __VA_ARGS__);          \
	} while (0)

bool mc_config_validate(const struct mc_config *c, struct mc_error *err)
{
	struct mc_error dummy;
	int used[40];
	bool seen[MC_SLOTS_MAX] = {0};

	if (err == NULL) {
		err = &dummy;
	}
	for (size_t i = 0; i < ARRAY_SIZE(used); i++) {
		used[i] = -1;
	}
	if (c->wake_interval_s < MC_WAKE_INTERVAL_MIN_S ||
	    c->wake_interval_s > MC_WAKE_INTERVAL_MAX_S) {
		FAIL(err, -1, "out_of_range", "wake_interval_s must be %d-%d",
		     MC_WAKE_INTERVAL_MIN_S, MC_WAKE_INTERVAL_MAX_S);
		return false;
	}
	if (c->n > MC_SLOTS_MAX) {
		FAIL(err, -1, "out_of_range", "at most %d slots", MC_SLOTS_MAX);
		return false;
	}

	for (int i = 0; i < c->n; i++) {
		const struct mc_slot *s = &c->slots[i];
		const struct mc_module_info *m = mc_module_info(s->module);

		if (m == NULL) {
			FAIL(err, s->slot, "unknown_module");
			return false;
		}
		if (s->slot >= MC_SLOTS_MAX || seen[s->slot]) {
			FAIL(err, s->slot, "out_of_range", "invalid slot index");
			return false;
		}
		seen[s->slot] = true;

		if (m->bus == MC_BUS_I2C) {
			if (s->addr < 0x08 || s->addr > 0x77) {
				FAIL(err, s->slot, "out_of_range", "I2C address");
				return false;
			}
		} else {
			if (s->pin < 0) {
				FAIL(err, s->slot, "out_of_range", "pin missing");
				return false;
			}
			if (s->pin > 39) {
				FAIL(err, s->slot, "out_of_range", "GPIO %d not usable for %s",
				     s->pin, m->name);
				return false;
			}
			const char *why = reserved_reason(s->pin);

			if (why != NULL) {
				FAIL(err, s->slot, "pin_reserved", "GPIO %d: %s", s->pin, why);
				return false;
			}
			if (m->actuator && (input_only_mask() & BIT64_(s->pin))) {
				FAIL(err, s->slot, "pin_not_output", "GPIO %d is input-only",
				     s->pin);
				return false;
			}
			if (!(allowed_pins(m->bus) & BIT64_(s->pin))) {
				FAIL(err, s->slot, "out_of_range", "GPIO %d not usable for %s",
				     s->pin, m->name);
				return false;
			}
			if (used[s->pin] >= 0) {
				FAIL(err, s->slot, "pin_conflict", "GPIO %d also used by slot %d",
				     s->pin, used[s->pin]);
				return false;
			}
			used[s->pin] = s->slot;
		}

		if (m->actuator) {
			if (s->max_run_s < 1 || s->max_run_s > MC_MAX_RUN_S_HARD) {
				FAIL(err, s->slot, "out_of_range", "max_run_s must be 1-%d",
				     MC_MAX_RUN_S_HARD);
				return false;
			}
			if (s->min_pause_s < 0) {
				FAIL(err, s->slot, "out_of_range", "min_pause_s");
				return false;
			}
		}
		if (mc_module_is_moisture(s->module) && s->cal_dry == s->cal_wet) {
			FAIL(err, s->slot, "out_of_range", "cal.dry and cal.wet must differ");
			return false;
		}
	}
	return true;
}

/* --- parsing (Zephyr JSON library, in place) ------------------------------------------- */

#define ABSENT INT32_MIN

struct cal_j {
	int32_t dry;
	int32_t wet;
};

struct slot_j {
	int32_t slot;
	const char *module;
	int32_t pin;
	int32_t addr;
	struct cal_j cal;
	bool active_high;
	int32_t max_run_s;
	int32_t min_pause_s;
};

struct config_j {
	int32_t rev;
	int32_t wake_interval_s;
	struct slot_j slots[MC_SLOTS_MAX];
	size_t n_slots;
};

static const struct json_obj_descr cal_descr[] = {
	JSON_OBJ_DESCR_PRIM(struct cal_j, dry, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct cal_j, wet, JSON_TOK_NUMBER),
};

static const struct json_obj_descr slot_descr[] = {
	JSON_OBJ_DESCR_PRIM(struct slot_j, slot, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct slot_j, module, JSON_TOK_STRING),
	JSON_OBJ_DESCR_PRIM(struct slot_j, pin, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct slot_j, addr, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_OBJECT(struct slot_j, cal, cal_descr),
	JSON_OBJ_DESCR_PRIM(struct slot_j, active_high, JSON_TOK_TRUE),
	JSON_OBJ_DESCR_PRIM(struct slot_j, max_run_s, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct slot_j, min_pause_s, JSON_TOK_NUMBER),
};

static const struct json_obj_descr config_descr[] = {
	JSON_OBJ_DESCR_PRIM(struct config_j, rev, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_PRIM(struct config_j, wake_interval_s, JSON_TOK_NUMBER),
	JSON_OBJ_DESCR_OBJ_ARRAY(struct config_j, slots, MC_SLOTS_MAX, n_slots, slot_descr,
				 ARRAY_SIZE(slot_descr)),
};

bool mc_config_parse(char *buf, size_t len, struct mc_config *out, struct mc_error *err)
{
	static struct config_j j; /* large: keep off the stack; single-threaded use */
	struct mc_error dummy;

	if (err == NULL) {
		err = &dummy;
	}
	j.rev = ABSENT;
	j.wake_interval_s = ABSENT;
	j.n_slots = 0;
	for (int i = 0; i < MC_SLOTS_MAX; i++) {
		j.slots[i] = (struct slot_j){.slot = ABSENT, .module = NULL, .pin = ABSENT,
					     .addr = ABSENT, .cal = {ABSENT, ABSENT},
					     .active_high = true, .max_run_s = ABSENT,
					     .min_pause_s = ABSENT};
	}

	int64_t r = json_obj_parse(buf, len, config_descr, ARRAY_SIZE(config_descr), &j);

	if (r == -ENOSPC) {
		FAIL(err, -1, "out_of_range", "at most %d slots", MC_SLOTS_MAX);
		return false;
	}
	if (r < 0) {
		FAIL(err, -1, "out_of_range", "not a valid config document");
		return false;
	}
	if (j.rev == ABSENT || j.wake_interval_s == ABSENT) {
		FAIL(err, -1, "out_of_range", "rev and wake_interval_s are required");
		return false;
	}

	mc_config_init(out);
	out->rev = j.rev;
	out->wake_interval_s = j.wake_interval_s;
	out->n = (uint8_t)j.n_slots;
	for (size_t i = 0; i < j.n_slots; i++) {
		const struct slot_j *s = &j.slots[i];
		struct mc_slot *d = &out->slots[i];

		if (s->slot == ABSENT || s->slot < 0 || s->slot > 255) {
			FAIL(err, -1, "out_of_range", "slot %d: invalid slot index", (int)i);
			return false;
		}
		d->slot = (uint8_t)s->slot;
		d->module = mc_module_from_name(s->module);
		d->pin = s->pin == ABSENT ? -1 : (int16_t)s->pin;
		d->addr = s->addr == ABSENT ? -1 : (int16_t)s->addr;
		d->cal_dry = s->cal.dry == ABSENT ? MC_CAL_DRY_DEFAULT : s->cal.dry;
		d->cal_wet = s->cal.wet == ABSENT ? MC_CAL_WET_DEFAULT : s->cal.wet;
		d->active_high = s->active_high;
		d->max_run_s = s->max_run_s == ABSENT ? -1 : s->max_run_s;
		d->min_pause_s = s->min_pause_s == ABSENT ? 0 : s->min_pause_s;
	}
	return true;
}

/* --- encoding ------------------------------------------------------------------------------ */

void mc_config_write(struct mc_jw *w, const struct mc_config *c)
{
	mc_jw_kv_int(w, "rev", c->rev);
	mc_config_write_body(w, c);
}

void mc_config_write_body(struct mc_jw *w, const struct mc_config *c)
{
	mc_jw_kv_int(w, "wake_interval_s", c->wake_interval_s);
	mc_jw_key(w, "slots");
	mc_jw_arr(w);
	for (int i = 0; i < c->n; i++) {
		const struct mc_slot *s = &c->slots[i];
		const struct mc_module_info *m = mc_module_info(s->module);

		if (m == NULL) {
			continue;
		}
		mc_jw_obj(w);
		mc_jw_kv_int(w, "slot", s->slot);
		mc_jw_kv_str(w, "module", m->name);
		if (m->bus == MC_BUS_I2C) {
			mc_jw_kv_int(w, "addr", s->addr);
		} else {
			mc_jw_kv_int(w, "pin", s->pin);
		}
		if (mc_module_is_moisture(s->module)) {
			mc_jw_key(w, "cal");
			mc_jw_obj(w);
			mc_jw_kv_int(w, "dry", s->cal_dry);
			mc_jw_kv_int(w, "wet", s->cal_wet);
			mc_jw_end_obj(w);
		}
		if (m->actuator) {
			mc_jw_kv_bool(w, "active_high", s->active_high);
			mc_jw_kv_int(w, "max_run_s", s->max_run_s);
			mc_jw_kv_int(w, "min_pause_s", s->min_pause_s);
		}
		mc_jw_end_obj(w);
	}
	mc_jw_end_arr(w);
}

bool mc_config_same(const struct mc_config *a, const struct mc_config *b)
{
	if (a->wake_interval_s != b->wake_interval_s || a->n != b->n) {
		return false;
	}
	for (int i = 0; i < a->n; i++) {
		const struct mc_slot *x = &a->slots[i], *y = &b->slots[i];

		if (x->slot != y->slot || x->module != y->module || x->pin != y->pin ||
		    x->addr != y->addr || x->cal_dry != y->cal_dry || x->cal_wet != y->cal_wet ||
		    x->active_high != y->active_high || x->max_run_s != y->max_run_s ||
		    x->min_pause_s != y->min_pause_s) {
			return false;
		}
	}
	return true;
}
