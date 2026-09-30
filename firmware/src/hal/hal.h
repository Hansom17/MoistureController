/* ESP32 / Zephyr side of the firmware: everything that touches hardware. */
#ifndef HAL_H
#define HAL_H

#include "mc_ble.h"
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

enum hal_led { HAL_LED_OFF, HAL_LED_PAIRING, HAL_LED_CONNECTED, HAL_LED_MAINTENANCE };
void hal_board_led(enum hal_led pattern);

/* BOOT button (ble.md §3): how long it is held, up to `limit_ms`, LED feedback at the thresholds. */
#define HAL_HOLD_MAINTENANCE_MS 3000
#define HAL_HOLD_FACTORY_RESET_MS 10000
int32_t hal_board_button_hold_ms(int32_t limit_ms);

/* Logs free/allocated/peak bytes of the kernel heap (WiFi, Bluetooth and TLS all live there). */
void hal_heap_log(const char *where);

/* --- storage -------------------------------------------------------------------------------- */
int hal_store_init(void);
enum mc_cfg_load hal_store_load_config(struct mc_config *c);
int hal_store_save_config(const struct mc_config *c);
/* False if the device was never paired. With MC_DEV_PROVISION the build's values are stored first. */
bool hal_store_load_prov(struct hal_prov *p);
int hal_store_save_prov(const struct hal_prov *p);
void hal_store_factory_reset(void);
void hal_store_clear_config(void);
/* The 16-byte PoP from the factory partition (ble.md §7.7). With MC_DEV_POP_HEX a blank one falls back to that. */
bool hal_store_load_pop(uint8_t pop[MC_BLE_POP_LEN]);

/* --- retained RAM and sleep ------------------------------------------------------------------- */
void hal_rtc_load(struct mc_rtc *r);
void hal_rtc_store(const struct mc_rtc *r);
void hal_rtc_clear(void);
enum mc_wake hal_wake_cause(const struct mc_rtc *r);
/* Stores nothing: call hal_rtc_store() first. Does not return. */
void hal_sleep(int32_t seconds);

/* --- network ------------------------------------------------------------------------------------ */
void hal_net_set_prov(const struct hal_prov *p);
/* 2.4 GHz networks, strongest first; returns the count or <0. */
int hal_net_wifi_scan(struct mc_ble_net *out, size_t max);
/* Pairing test (ble.md §7.5): join WiFi, connect to the broker with TLS-PSK, publish `online`. */
int hal_net_test(const struct hal_prov *p, struct mc_ble_test *out);

/* --- BLE pairing -------------------------------------------------------------------------------------- */
enum hal_ble_result {
	HAL_BLE_PAIRED,   /* committed: restart into normal operation */
	HAL_BLE_TIMEOUT,  /* the window ran out */
	HAL_BLE_LOCKED,   /* 5 failed handshakes (ble.md §3) */
	HAL_BLE_ERROR,
};
int hal_ble_init(void);
/* Advertises and serves pairing sessions for up to `window_s`. Blocks. */
enum hal_ble_result hal_ble_pairing_window(const uint8_t pop[MC_BLE_POP_LEN], int32_t window_s);
extern const struct mc_io hal_io;

#endif /* HAL_H */
