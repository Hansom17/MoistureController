/*
 * Moisture controller: wake, run one cycle (src/core/mc_cycle.c), sleep.
 * Firmware_Specs.md has the design; contracts/mqtt.md the wire protocol.
 */
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/reboot.h>

#include "hal.h"

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

/* Nothing to connect to yet: sleep the default interval and look again (pairing comes later). */
#define UNPROVISIONED_SLEEP_S MC_WAKE_INTERVAL_DEFAULT_S

static struct mc_rtc rtc;
static struct mc_app app;
static struct hal_prov prov;

int main(void)
{
	hal_board_init();
	hal_store_init();
	hal_rtc_load(&rtc);

	enum mc_wake wake = hal_wake_cause(&rtc);

	LOG_INF("firmware " MC_FW_VERSION ", wake: %s", mc_wake_name(wake));

	if (!hal_store_load_prov(&prov)) {
		LOG_WRN("not paired: nothing to connect to");
		hal_sleep(UNPROVISIONED_SLEEP_S);
	}
	hal_net_set_prov(&prov);

	enum mc_cfg_load loaded = hal_store_load_config(&app.cfg);

	mc_app_begin(&app, &rtc, &hal_io, NULL, wake, loaded);
	if (wake == MC_WAKE_BUTTON) {
		app.service_request_s = CONFIG_MC_BUTTON_SERVICE_MINUTES * 60;
	}
	mc_cycle(&app);
	hal_rtc_store(&rtc);

	if (app.reboot) {
		LOG_INF("rebooting as commanded");
		sys_reboot(SYS_REBOOT_COLD);
	}
	hal_sleep(app.next_wake_s);
	return 0;
}
