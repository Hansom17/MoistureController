/*
 * Moisture controller: wake, run one cycle (src/core/mc_cycle.c), sleep.
 * Firmware_Specs.md has the design; contracts/mqtt.md the wire protocol, contracts/ble.md pairing.
 */
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/reboot.h>

#include "hal.h"

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

/* Not paired: look for the app again after this (ble.md §3: the window reopens on every wake). */
#define UNPROVISIONED_SLEEP_S 1800
#define PAIRING_WINDOW_S 600     /* unprovisioned */
#define MAINTENANCE_WINDOW_S 300 /* after a 3 s BOOT press */
#define MAINTENANCE_SERVICE_S (15 * 60)

static struct mc_rtc rtc;
static struct mc_app app;
static struct hal_prov prov;

/* BOOT held 10 s: wipe pairing and config (the PoP stays), start over unpaired. */
static void factory_reset(void)
{
	LOG_WRN("factory reset");
	hal_store_factory_reset();
	hal_rtc_clear();
	k_msleep(200);
	sys_reboot(SYS_REBOOT_COLD);
}

/* Opens the pairing window; returns true if the device was paired (and must restart). */
static bool pairing_window(int32_t seconds)
{
	uint8_t pop[MC_BLE_POP_LEN];

	if (!hal_store_load_pop(pop)) {
		LOG_ERR("no PoP in the factory partition: pairing is not possible (tools/make_label.py)");
		return false;
	}
	if (hal_ble_init() != 0) {
		return false;
	}
	enum hal_ble_result r = hal_ble_pairing_window(pop, seconds);

	LOG_INF("pairing window closed: %s", r == HAL_BLE_PAIRED ? "paired" :
					      r == HAL_BLE_LOCKED ? "too many failed attempts" :
					      r == HAL_BLE_TIMEOUT ? "timeout" : "error");
	return r == HAL_BLE_PAIRED;
}

int main(void)
{
	hal_board_init();
	hal_heap_log("at boot");
	hal_store_init();
	hal_rtc_load(&rtc);

	enum mc_wake wake = hal_wake_cause(&rtc);

	LOG_INF("firmware " MC_FW_VERSION ", wake: %s", mc_wake_name(wake));

	/* BOOT button: 3 s opens the pairing window, 10 s is a factory reset (ble.md §3) */
	int32_t held = 0;

	if (wake == MC_WAKE_BUTTON) {
		held = hal_board_button_hold_ms(HAL_HOLD_FACTORY_RESET_MS);
		if (held >= HAL_HOLD_FACTORY_RESET_MS) {
			factory_reset();
		}
	}
	bool maintenance = held >= HAL_HOLD_MAINTENANCE_MS;

	LOG_INF("loading pairing data");
	bool paired = hal_store_load_prov(&prov);

	if (!paired || maintenance) {
		if (pairing_window(paired ? MAINTENANCE_WINDOW_S : PAIRING_WINDOW_S)) {
			k_msleep(500);
			sys_reboot(SYS_REBOOT_COLD);
		}
		if (!paired) {
			LOG_WRN("not paired: sleeping %d s", UNPROVISIONED_SLEEP_S);
			hal_sleep(UNPROVISIONED_SLEEP_S);
		}
	}
	hal_net_set_prov(&prov);
	LOG_INF("paired as %s, gateway %s:%u", prov.device_id, prov.host, prov.port);

	enum mc_cfg_load loaded = hal_store_load_config(&app.cfg);

	LOG_INF("config: %s (rev %d, %d slots)",
		loaded == MC_CFG_LOADED ? "loaded" : loaded == MC_CFG_MISSING ? "none yet" : "CORRUPT",
		app.cfg.rev, app.cfg.n);

	mc_app_begin(&app, &rtc, &hal_io, NULL, wake, loaded);
	if (maintenance) {
		app.service_request_s = MAINTENANCE_SERVICE_S;
	} else if (wake == MC_WAKE_BUTTON) {
		app.service_request_s = CONFIG_MC_BUTTON_SERVICE_MINUTES * 60;
	}
	mc_cycle(&app);
	hal_rtc_store(&rtc);
	LOG_INF("cycle done, next wake in %d s", app.next_wake_s);

	if (app.reboot) {
		LOG_INF("rebooting as commanded");
		sys_reboot(SYS_REBOOT_COLD);
	}
	hal_sleep(app.next_wake_s);
	return 0;
}
