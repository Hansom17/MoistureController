/* Placeholder until the esp-zigbee-sdk layer exists: the radio is not started, the module reports "not joined"
 * and the attributes go to the log. This lets the application, the sensors and the pump logic run on a board
 * without a network. */
#include "esp_log.h"
#include "mc_hal.h"
#include "mc_zigbee.h"

static const char *TAG = "mc_zb_stub";

void mc_zb_start(const mc_zb_params_t *params)
{
    (void)params;
    ESP_LOGW(TAG, "no Zigbee stack in this build");
    mc_event_t ev = {.kind = MC_EV_ZB_STACK_READY};
    ev.u.joined = false;
    mc_app_post(&ev);
}

void mc_zb_start_steering(void)
{
    ESP_LOGI(TAG, "steering requested (not available)");
    mc_event_t ev = {.kind = MC_EV_ZB_STEERING_DONE};
    ev.u.ok = false;
    mc_app_post(&ev);
}

void mc_zb_rejoin(void)
{
    ESP_LOGI(TAG, "rejoin requested (not available)");
}

void mc_zb_leave(void)
{
    mc_event_t ev = {.kind = MC_EV_ZB_LEFT};
    mc_app_post(&ev);
}

void mc_zb_update_attrs(const mc_attrs_t *a)
{
    ESP_LOGI(TAG, "attrs seq=%u status=%u fast=%d cfg_rev=%u vbat=%u mV (state %u)", a->seq, a->status, a->fast_mode,
             a->cfg_rev, a->voltage_mv, a->batt_state);
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        if (a->readings[i].type != MC_MODULE_EMPTY) {
            ESP_LOGI(TAG, "  slot %d type=%u err=%u value=%d raw=%u", i, a->readings[i].type, a->readings[i].error,
                     a->readings[i].value, a->readings[i].raw);
        }
    }
}

void mc_zb_report_now(void)
{
}

void mc_zb_send_ack(uint16_t n, uint32_t cmd_id, uint8_t state, uint8_t reason, uint16_t ends_in_s)
{
    ESP_LOGI(TAG, "ack n=%u cmd=%lu state=%u reason=%u ends_in=%u", n, (unsigned long)cmd_id, state, reason, ends_in_s);
}

void mc_zb_send_event(uint16_t n, uint8_t code, uint8_t slot, uint16_t arg)
{
    ESP_LOGI(TAG, "event n=%u code=%u slot=%u arg=%u", n, code, slot, arg);
}
