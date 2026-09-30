/* ESP32 / Zephyr side of the firmware: everything that touches hardware. */
#ifndef HAL_H
#define HAL_H

#include "mc_cycle.h"

/* What pairing gives the device (contracts/ble.md); stored in settings. */
struct hal_prov {
	char ssid[33];
	char wifi_password[65];
	char host[64];          /* the gateway's LAN address */
	uint16_t port;
	char device_id[32];     /* mc-…: MQTT client id and TLS-PSK identity */
	uint8_t psk[32];
};

/* --- board: ADC, pumps, LED ---------------------------------------------------------------- */
int hal_board_init(void);
int hal_board_read_adc(int pin, int32_t *raw);
int32_t hal_board_battery_mv(void);
void hal_board_pump(int pin, bool active_high, bool on, bool hold_through_sleep);
void hal_board_identify(int32_t seconds);
bool hal_board_button_pressed(void);

/* --- storage -------------------------------------------------------------------------------- */
int hal_store_init(void);
enum mc_cfg_load hal_store_load_config(struct mc_config *c);
int hal_store_save_config(const struct mc_config *c);
/* False if the device was never paired. With MC_DEV_PROVISION the build's values are stored first. */
bool hal_store_load_prov(struct hal_prov *p);
int hal_store_save_prov(const struct hal_prov *p);
void hal_store_factory_reset(void);

/* --- retained RAM and sleep ------------------------------------------------------------------- */
void hal_rtc_load(struct mc_rtc *r);
void hal_rtc_store(const struct mc_rtc *r);
enum mc_wake hal_wake_cause(const struct mc_rtc *r);
/* Stores nothing: call hal_rtc_store() first. Does not return. */
void hal_sleep(int32_t seconds);

/* --- network ------------------------------------------------------------------------------------ */
void hal_net_set_prov(const struct hal_prov *p);
extern const struct mc_io hal_io;

#endif /* HAL_H */
