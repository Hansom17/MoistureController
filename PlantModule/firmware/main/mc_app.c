/* The application task: one queue of events in, mc_core_step() in the middle, the actions executed here. */
#include "mc_app.h"

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "mc_hal.h"
#include "mc_zigbee.h"
#include "sdkconfig.h"

static const char *TAG = "mc_app";

#define BATTERY_PERIOD_MS 30000u

static QueueHandle_t queue;
static mc_core_t core;
static mc_factory_t factory_copy;
static bool factory_ok;
static mc_actions_t actions;

void mc_app_post(const mc_event_t *ev)
{
    if (queue == NULL || xQueueSend(queue, ev, 0) != pdTRUE) {
        ESP_LOGE(TAG, "event queue full, dropped event %d", ev ? (int)ev->kind : -1);
    }
}

static void read_slot(uint8_t slot, uint8_t port)
{
    mc_event_t ev = {.kind = MC_EV_ADC_DONE};
    ev.u.adc.slot = slot;
    uint16_t raw = 0;
    ev.u.adc.ok = mc_hal_adc_read_port(port, core.cfg.slots[slot].samples, &raw);
    ev.u.adc.raw = raw;
    mc_app_post(&ev);
}

static void execute(const mc_action_t *a)
{
    switch (a->kind) {
    case MC_ACT_START_ZIGBEE: {
        mc_zb_params_t p = {.factory = factory_ok ? &factory_copy : NULL,
#ifdef CONFIG_MC_DEV_JOIN
                            .dev_join = true,
#endif
        };
        mc_zb_start(&p);
        break;
    }
    case MC_ACT_START_STEERING:
        mc_zb_start_steering();
        break;
    case MC_ACT_REJOIN:
        mc_zb_rejoin();
        break;
    case MC_ACT_LEAVE_NETWORK:
        mc_zb_leave();
        break;
    case MC_ACT_ERASE_STATE:
        mc_hal_state_erase();
        break;
    case MC_ACT_UPDATE_ATTRS: {
        mc_attrs_t attrs;
        mc_core_attrs(&core, &attrs);
        mc_zb_update_attrs(&attrs);
        break;
    }
    case MC_ACT_REPORT_NOW:
        mc_zb_report_now();
        break;
    case MC_ACT_SEND_CMD_ACK:
        mc_zb_send_ack(a->u.ack.n, a->u.ack.cmd_id, a->u.ack.state, a->u.ack.reason, a->u.ack.ends_in_s);
        break;
    case MC_ACT_SEND_EVENT:
        mc_zb_send_event(a->u.event.n, a->u.event.code, a->u.event.slot, a->u.event.arg);
        break;
    case MC_ACT_DRIVE_PUMP:
        mc_hal_pump_set(a->u.pump.port, a->u.pump.active_high, a->u.pump.on);
        break;
    case MC_ACT_ALL_OUTPUTS_OFF:
        mc_hal_outputs_off(&core.cfg);
        break;
    case MC_ACT_READ_SLOT:
        read_slot(a->u.read.slot, a->u.read.port);
        break;
    case MC_ACT_PERSIST_CONFIG:
        if (!mc_hal_config_store(&core.cfg)) {
            ESP_LOGE(TAG, "configuration not stored");
        }
        mc_hal_outputs_off(&core.cfg); /* a new pump slot starts as an output that is off */
        break;
    case MC_ACT_PERSIST_DIAG:
        mc_hal_diag_store(&core.diag);
        break;
    case MC_ACT_SET_LED:
        mc_hal_led_set(a->u.led);
        break;
    case MC_ACT_ARM_TIMER:
        mc_hal_timer_arm(a->u.timer.id, a->u.timer.arg, a->u.timer.delay_ms);
        break;
    case MC_ACT_CANCEL_TIMER:
        mc_hal_timer_cancel(a->u.timer.id, a->u.timer.arg);
        break;
    case MC_ACT_REBOOT:
        ESP_LOGW(TAG, "reboot requested");
        mc_hal_outputs_off(&core.cfg);
        vTaskDelay(pdMS_TO_TICKS(200)); /* let the acknowledgement leave */
        esp_restart();
        break;
    }
}

static void step(mc_event_t *ev)
{
    ev->now_ms = mc_hal_now_ms();
    mc_core_step(&core, ev, &actions);
    if (actions.overflow) {
        ESP_LOGE(TAG, "the core returned more actions than fit");
    }
    for (size_t i = 0; i < actions.n; i++) {
        execute(&actions.a[i]);
    }
}

static void battery_tick(void *arg)
{
    (void)arg;
    mc_event_t ev = {.kind = MC_EV_BATT_SAMPLE};
    ev.u.mv = mc_hal_battery_mv();
    mc_app_post(&ev);
}

static void app_task(void *arg)
{
    (void)arg;
    mc_event_t ev = {.kind = MC_EV_BOOT};
    mc_hal_boot_info(&ev.u.boot);
    ev.u.boot.factory_valid = factory_ok;
    ESP_LOGI(TAG, "boot reason %u, boot id %u, first boot %d, config %s", ev.u.boot.reset_reason, ev.u.boot.boot_id,
             ev.u.boot.first_boot, ev.u.boot.config_valid ? "ok" : "INVALID");
    step(&ev);

    TickType_t last_battery = 0;
    for (;;) {
        if (xQueueReceive(queue, &ev, pdMS_TO_TICKS(1000)) == pdTRUE) {
            step(&ev);
        }
        if (xTaskGetTickCount() - last_battery >= pdMS_TO_TICKS(BATTERY_PERIOD_MS)) {
            last_battery = xTaskGetTickCount();
            battery_tick(NULL);
        }
    }
}

void mc_app_start(const mc_board_t *board, const mc_factory_t *factory, bool factory_valid)
{
    factory_ok = factory_valid;
    if (factory_valid) {
        factory_copy = *factory;
    }
    queue = xQueueCreate(32, sizeof(mc_event_t));
    configASSERT(queue != NULL);
    mc_core_init(&core, board, 4095);
    if (board != NULL) {
        mc_hal_gpio_init(board);
        mc_hal_adc_init(board);
        mc_hal_button_start();
    }
    mc_hal_timers_init();
    xTaskCreate(app_task, "mc_app", 6144, NULL, 5, NULL);
}
