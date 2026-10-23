/* Persistence (PlantModule/specs.md 12): configuration in two NVS blob slots, counters, factory partition. */
#include <string.h>

#include "esp_log.h"
#include "esp_partition.h"
#include "esp_system.h"
#include "mc_hal.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "mc_store";

#define NS_CFG "mc_cfg"
#define NS_DIAG "mc_diag"
#define FACTORY_SUBTYPE 0x40

static mc_diag_t stored_diag; /* what is in NVS, to write only on change */
static bool diag_known;

bool mc_hal_store_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS erased (%s)", esp_err_to_name(err));
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
        return false;
    }
    ESP_ERROR_CHECK(err);
    return true;
}

bool mc_hal_factory_read(mc_factory_t *out)
{
    const esp_partition_t *p =
        esp_partition_find_first(ESP_PARTITION_TYPE_DATA, (esp_partition_subtype_t)FACTORY_SUBTYPE, "factory");
    if (p == NULL) {
        ESP_LOGE(TAG, "no factory partition");
        return false;
    }
    uint8_t buf[MC_FACTORY_HEADER_SIZE];
    if (esp_partition_read(p, 0, buf, sizeof buf) != ESP_OK) {
        return false;
    }
    return mc_factory_parse(buf, sizeof buf, out);
}

static uint8_t reset_reason(void)
{
    ESP_LOGI(TAG, "raw reset reason %d", (int)esp_reset_reason());
    switch (esp_reset_reason()) {
    case ESP_RST_POWERON:
        return MC_BOOT_REASON_POWER_ON;
    case ESP_RST_SW:
        return MC_BOOT_REASON_SOFTWARE;
    case ESP_RST_PANIC:
        return MC_BOOT_REASON_PANIC;
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT:
        return MC_BOOT_REASON_WATCHDOG;
    case ESP_RST_BROWNOUT:
        return MC_BOOT_REASON_BROWNOUT;
    default:
        return MC_BOOT_REASON_OTHER;
    }
}

static bool load_slot(nvs_handle_t h, const char *key, mc_config_t *out)
{
    uint8_t blob[MC_CONFIG_BLOB_SIZE];
    size_t len = sizeof blob;
    if (nvs_get_blob(h, key, blob, &len) != ESP_OK) {
        return false;
    }
    return mc_config_decode(blob, len, out);
}

/* No blob at all = a new device (valid default); blobs that are all damaged = invalid. */
static bool config_load(mc_config_t *out)
{
    mc_config_default(out);
    nvs_handle_t h;
    if (nvs_open(NS_CFG, NVS_READONLY, &h) != ESP_OK) {
        return true;
    }
    uint8_t active = 0;
    nvs_get_u8(h, "cfg_active", &active);
    const char *keys[2] = {active ? "cfg_b" : "cfg_a", active ? "cfg_a" : "cfg_b"};
    bool any = false, ok = false;
    for (int i = 0; i < 2 && !ok; i++) {
        size_t len = 0;
        if (nvs_get_blob(h, keys[i], NULL, &len) == ESP_OK) {
            any = true;
            ok = load_slot(h, keys[i], out);
            if (!ok) {
                ESP_LOGW(TAG, "stored configuration %s is damaged", keys[i]);
            }
        }
    }
    nvs_close(h);
    if (!any) {
        return true;
    }
    if (!ok) {
        mc_config_default(out);
    }
    return ok;
}

void mc_hal_boot_info(mc_boot_t *b)
{
    memset(b, 0, sizeof *b);
    b->reset_reason = reset_reason();
    b->config_valid = config_load(&b->config);

    nvs_handle_t h;
    uint8_t booted = 0, crash = 0;
    uint16_t resets = 0, rejoins = 0, last_err = 0, boot_id = 0;
    if (nvs_open(NS_DIAG, NVS_READWRITE, &h) == ESP_OK) {
        nvs_get_u8(h, "booted", &booted);
        nvs_get_u8(h, "crash", &crash);
        nvs_get_u16(h, "resets", &resets);
        nvs_get_u16(h, "rejoins", &rejoins);
        nvs_get_u16(h, "last_err", &last_err);
        nvs_get_u16(h, "boot_id", &boot_id);
        boot_id++;
        nvs_set_u16(h, "boot_id", boot_id);
        nvs_set_u8(h, "booted", 1);
        nvs_commit(h);
        nvs_close(h);
    }
    b->first_boot = booted == 0;
    b->crash_count_stored = crash;
    b->reset_count_stored = resets;
    b->rejoin_count_stored = rejoins;
    b->last_error_stored = last_err;
    b->boot_id = boot_id;
    stored_diag = (mc_diag_t){.crash_count = crash, .reset_count = resets, .rejoin_count = rejoins, .last_error = last_err};
    diag_known = true;
}

bool mc_hal_config_store(const mc_config_t *cfg)
{
    uint8_t blob[MC_CONFIG_BLOB_SIZE];
    size_t len = mc_config_encode(cfg, blob);
    nvs_handle_t h;
    if (nvs_open(NS_CFG, NVS_READWRITE, &h) != ESP_OK) {
        return false;
    }
    uint8_t active = 0;
    nvs_get_u8(h, "cfg_active", &active);
    uint8_t next = active ? 0 : 1; /* write the other slot first, then switch: a power cut keeps the old one */
    bool ok = nvs_set_blob(h, next ? "cfg_b" : "cfg_a", blob, len) == ESP_OK && nvs_commit(h) == ESP_OK &&
              nvs_set_u8(h, "cfg_active", next) == ESP_OK && nvs_commit(h) == ESP_OK;
    nvs_close(h);
    if (!ok) {
        ESP_LOGE(TAG, "storing the configuration failed");
    }
    return ok;
}

void mc_hal_diag_store(const mc_diag_t *d)
{
    if (diag_known && memcmp(&stored_diag, d, sizeof *d) == 0) {
        return;
    }
    nvs_handle_t h;
    if (nvs_open(NS_DIAG, NVS_READWRITE, &h) != ESP_OK) {
        return;
    }
    nvs_set_u8(h, "crash", d->crash_count);
    nvs_set_u16(h, "resets", d->reset_count);
    nvs_set_u16(h, "rejoins", d->rejoin_count);
    nvs_set_u16(h, "last_err", d->last_error);
    if (nvs_commit(h) == ESP_OK) {
        stored_diag = *d;
        diag_known = true;
    }
    nvs_close(h);
}

void mc_hal_state_erase(void)
{
    nvs_handle_t h;
    if (nvs_open(NS_CFG, NVS_READWRITE, &h) == ESP_OK) {
        nvs_erase_all(h);
        nvs_commit(h);
        nvs_close(h);
    }
    if (nvs_open(NS_DIAG, NVS_READWRITE, &h) == ESP_OK) {
        nvs_erase_key(h, "booted");
        nvs_commit(h);
        nvs_close(h);
    }
}
