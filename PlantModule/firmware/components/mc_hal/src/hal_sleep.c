/* Sleeping (PlantModule/specs.md 18): the HAL side of the power modes. The core says what is allowed
 * (mc_core_sleep_allowed), this file does it: automatic light sleep through the power management, deep sleep with a
 * timer wake-up, and the few values that have to survive a deep sleep (RTC memory). */
#include <string.h>

#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_pm.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "mc_hal.h"
#include "sdkconfig.h"

static const char *TAG = "mc_sleep";

#define RTC_MAGIC 0x4D435331u

typedef struct {
    uint32_t magic;
    uint16_t seq;
    uint16_t wake_count;
    uint32_t sleep_total_s;
    uint32_t sleep_s;        /* what the sleep that is under way will have taken */
    uint16_t last_awake_ms;
} rtc_state_t;

/* survives deep sleep and software resets, undefined after a power-on: the magic tells */
static RTC_NOINIT_ATTR rtc_state_t rtc;
static bool decided, deep_wake, light_on;

bool mc_hal_sleep_is_deep_wake(void)
{
    if (!decided) {
        decided = true;
        deep_wake = esp_reset_reason() == ESP_RST_DEEPSLEEP && rtc.magic == RTC_MAGIC;
        if (!deep_wake) {
            memset(&rtc, 0, sizeof rtc);
            rtc.magic = RTC_MAGIC;
        }
    }
    return deep_wake;
}

void mc_hal_sleep_boot(mc_boot_t *b)
{
    if (!mc_hal_sleep_is_deep_wake()) {
        return;
    }
    rtc.wake_count++;
    rtc.sleep_total_s += rtc.sleep_s;
    b->deep_sleep_wake = true;
    b->reset_reason = MC_BOOT_REASON_DEEP_SLEEP_WAKE;
    b->wake_reason = (esp_sleep_get_wakeup_causes() & BIT(ESP_SLEEP_WAKEUP_TIMER)) ? MC_WAKE_REASON_TIMER : MC_WAKE_REASON_NONE;
    b->rtc_seq = rtc.seq;
    b->rtc_wake_count = rtc.wake_count;
    b->rtc_sleep_total_s = rtc.sleep_total_s;
    b->rtc_last_awake_ms = rtc.last_awake_ms;
    ESP_LOGI(TAG, "deep-sleep wake %u, slept %lu s in total", (unsigned)rtc.wake_count, (unsigned long)rtc.sleep_total_s);
}

void mc_hal_sleep_apply(mc_sleep_t allowed)
{
    bool want = allowed != MC_SLEEP_NONE;
    if (want == light_on) {
        return;
    }
    /* automatic light sleep between events; the clock stays at 160 MHz so the radio timing never changes */
    esp_pm_config_t pm = {.max_freq_mhz = 160, .min_freq_mhz = 160, .light_sleep_enable = want};
    esp_err_t err = esp_pm_configure(&pm);
    if (err == ESP_OK) {
        light_on = want;
    } else {
        ESP_LOGE(TAG, "power management: %s", esp_err_to_name(err));
    }
}

void mc_hal_deep_sleep(uint32_t ms, uint16_t seq, const mc_config_t *cfg)
{
    rtc.magic = RTC_MAGIC;
    rtc.seq = seq;
    rtc.sleep_s = ms / 1000u;
    uint32_t awake = mc_hal_now_ms();
    rtc.last_awake_ms = (uint16_t)(awake > 65535u ? 65535u : awake);
    mc_hal_outputs_hold(cfg, true); /* on the C6 a held pad keeps its level through deep sleep; hal_gpio releases it at boot */
    esp_sleep_enable_timer_wakeup((uint64_t)ms * 1000u);
    ESP_LOGI(TAG, "deep sleep for %lu ms (awake %lu ms)", (unsigned long)ms, (unsigned long)awake);
    esp_deep_sleep_start(); /* does not return: the next thing is a boot */
}
