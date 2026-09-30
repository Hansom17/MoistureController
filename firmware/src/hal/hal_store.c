#include "hal.h"

#include <string.h>
#include <zephyr/logging/log.h>
#include <zephyr/storage/flash_map.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/crc.h>

LOG_MODULE_REGISTER(hal_store, LOG_LEVEL_INF);

/* Stored blobs carry a version and a CRC: a layout change or a torn write reads as "corrupt". */
#define CFG_VERSION 1
#define PROV_VERSION 1

struct cfg_blob {
	uint32_t version;
	struct mc_config cfg;
	uint32_t crc;
};

struct prov_blob {
	uint32_t version;
	struct hal_prov prov;
	uint32_t crc;
};

struct load_ctx {
	const char *name;
	void *dst;
	size_t size;
	bool found;
	bool size_ok;
};

static int load_cb(const char *key, size_t len, settings_read_cb read_cb, void *cb_arg, void *param)
{
	struct load_ctx *c = param;

	if (strcmp(key, c->name) != 0) {
		return 0;
	}
	c->found = true;
	c->size_ok = len == c->size && read_cb(cb_arg, c->dst, c->size) == (ssize_t)c->size;
	return 0;
}

static bool load_blob(const char *name, void *dst, size_t size, bool *corrupt)
{
	struct load_ctx c = {.name = name, .dst = dst, .size = size};

	settings_load_subtree_direct("mc", load_cb, &c);
	*corrupt = c.found && !c.size_ok;
	return c.found && c.size_ok;
}

int hal_store_init(void)
{
	return settings_subsys_init();
}

enum mc_cfg_load hal_store_load_config(struct mc_config *out)
{
	static struct cfg_blob b;
	bool corrupt;

	if (!load_blob("cfg", &b, sizeof(b), &corrupt)) {
		return corrupt ? MC_CFG_CORRUPT : MC_CFG_MISSING;
	}
	if (b.version != CFG_VERSION || b.crc != crc32_ieee((uint8_t *)&b, offsetof(struct cfg_blob, crc)) ||
	    !mc_config_validate(&b.cfg, NULL)) {
		LOG_ERR("stored config is invalid");
		return MC_CFG_CORRUPT;
	}
	*out = b.cfg;
	return MC_CFG_LOADED;
}

int hal_store_save_config(const struct mc_config *c)
{
	static struct cfg_blob b;

	memset(&b, 0, sizeof(b));
	b.version = CFG_VERSION;
	b.cfg = *c;
	b.crc = crc32_ieee((uint8_t *)&b, offsetof(struct cfg_blob, crc));
	return settings_save_one("mc/cfg", &b, sizeof(b));
}

static int hex_to_bytes(const char *hex, uint8_t *out, size_t n)
{
	if (strlen(hex) != n * 2) {
		return -EINVAL;
	}
	for (size_t i = 0; i < n; i++) {
		unsigned int v = 0;

		for (int k = 0; k < 2; k++) {
			char ch = hex[i * 2 + k];

			v <<= 4;
			if (ch >= '0' && ch <= '9') {
				v |= ch - '0';
			} else if (ch >= 'a' && ch <= 'f') {
				v |= ch - 'a' + 10;
			} else if (ch >= 'A' && ch <= 'F') {
				v |= ch - 'A' + 10;
			} else {
				return -EINVAL;
			}
		}
		out[i] = (uint8_t)v;
	}
	return 0;
}

int hal_store_save_prov(const struct hal_prov *p)
{
	static struct prov_blob b;

	memset(&b, 0, sizeof(b));
	b.version = PROV_VERSION;
	b.prov = *p;
	b.crc = crc32_ieee((uint8_t *)&b, offsetof(struct prov_blob, crc));
	return settings_save_one("mc/prov", &b, sizeof(b));
}

bool hal_store_load_prov(struct hal_prov *out)
{
	static struct prov_blob b;
	bool corrupt;
	bool stored = load_blob("prov", &b, sizeof(b), &corrupt) && b.version == PROV_VERSION &&
		      b.crc == crc32_ieee((uint8_t *)&b, offsetof(struct prov_blob, crc));

#ifdef CONFIG_MC_DEV_PROVISION
	/* A build provisioned from dev.conf always wins over what an earlier build stored. */
	struct hal_prov p = {.port = CONFIG_MC_DEV_BROKER_PORT};

	strncpy(p.ssid, CONFIG_MC_DEV_WIFI_SSID, sizeof(p.ssid) - 1);
	strncpy(p.wifi_password, CONFIG_MC_DEV_WIFI_PASSWORD, sizeof(p.wifi_password) - 1);
	strncpy(p.host, CONFIG_MC_DEV_BROKER_HOST, sizeof(p.host) - 1);
	strncpy(p.device_id, CONFIG_MC_DEV_DEVICE_ID, sizeof(p.device_id) - 1);
	if (hex_to_bytes(CONFIG_MC_DEV_PSK_HEX, p.psk, sizeof(p.psk)) < 0 || p.device_id[0] == '\0') {
		LOG_ERR("MC_DEV_* options are incomplete (device id, 64 hex characters of key)");
		return false;
	}
	if (!stored || memcmp(&b.prov, &p, sizeof(p)) != 0) {
		LOG_WRN("provisioning from the build (MC_DEV_PROVISION)");
		hal_store_save_prov(&p);
	}
	*out = p;
	return true;
#else
	(void)hex_to_bytes;
	if (!stored) {
		return false;
	}
	*out = b.prov;
	return true;
#endif
}

void hal_store_clear_config(void)
{
	settings_delete("mc/cfg");
}

/* Pairing data and config go; the factory partition with the PoP (ble.md) never does. */
void hal_store_factory_reset(void)
{
	settings_delete("mc/cfg");
	settings_delete("mc/prov");
}

/* --- PoP (ble.md §2, §7.7) ------------------------------------------------------------------------- */

bool hal_store_load_pop(uint8_t pop[MC_BLE_POP_LEN])
{
	uint8_t page[MC_FACTORY_SIZE];
	const struct flash_area *fa;

	if (flash_area_open(DT_FIXED_PARTITION_ID(DT_NODELABEL(coredump_partition)), &fa) == 0) {
		int rc = flash_area_read(fa, 0, page, sizeof(page));

		flash_area_close(fa);
		if (rc == 0 && mc_factory_parse(page, pop)) {
			return true;
		}
	}
#ifdef CONFIG_MC_DEV_POP_HEX
	if (sizeof(CONFIG_MC_DEV_POP_HEX) == 2 * MC_BLE_POP_LEN + 1) {
		uint8_t dev[32] = {0};

		if (hex_to_bytes(CONFIG_MC_DEV_POP_HEX, dev, MC_BLE_POP_LEN) == 0) {
			LOG_WRN("no factory PoP: using MC_DEV_POP_HEX (development only)");
			memcpy(pop, dev, MC_BLE_POP_LEN);
			return true;
		}
	}
#endif
	return false;
}
