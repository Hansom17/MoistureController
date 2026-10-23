#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "mc_hal.h"
#include "mc_ui.h"

static const char *TAG = "mc_gpio";

static const mc_board_t *board;
static mc_led_t led_pattern = MC_LED_OFF;
static uint32_t led_since_ms;
static mc_button_t button;
static bool pump_is_output[GPIO_NUM_MAX];

static int gpio_of_port(uint8_t port)
{
    if (port & MC_PORT_RAW_FLAG) {
        return board->allow_raw_gpio ? (port & 0x7F) : -1;
    }
    return port < board->port_count ? board->ports[port].gpio : -1;
}

static void drive(int gpio, bool active_high, bool on)
{
    if (gpio < 0 || gpio >= GPIO_NUM_MAX) {
        return;
    }
    int level = on ? active_high : !active_high;
    if (!pump_is_output[gpio]) {
        gpio_reset_pin(gpio);
        gpio_set_level(gpio, level); /* level first, so the pin never glitches to the wrong state */
        gpio_set_direction(gpio, GPIO_MODE_OUTPUT);
        pump_is_output[gpio] = true;
    }
    gpio_set_level(gpio, level);
}

void mc_hal_pump_set(uint8_t port, bool active_high, bool on)
{
    int g = gpio_of_port(port);
    if (g < 0) {
        ESP_LOGE(TAG, "pump on unknown port %u", port);
        return;
    }
    drive(g, active_high, on);
}

void mc_hal_outputs_off(const mc_config_t *cfg)
{
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        const mc_slot_cfg_t *s = &cfg->slots[i];
        if (s->module == MC_MODULE_PUMP) {
            drive(gpio_of_port(s->port), s->active_high, false);
        }
    }
}

static void led_apply(uint32_t now_ms)
{
    if (board->led.gpio < 0) {
        return;
    }
    bool lit = mc_led_level(led_pattern, now_ms - led_since_ms);
    gpio_set_level(board->led.gpio, lit == board->led.active_high);
}

/* The switched sensor supply (boards with `sensor_power`; nothing happens without it). */
void mc_hal_sensor_power(bool on)
{
    if (board == NULL || !board->sensor_power.present) {
        return;
    }
    gpio_set_level(board->sensor_power.gpio, on ? board->sensor_power.active_high : !board->sensor_power.active_high);
}

void mc_hal_led_set(mc_led_t pattern)
{
    if (pattern != led_pattern) {
        led_pattern = pattern;
        led_since_ms = mc_hal_now_ms();
        led_apply(led_since_ms);
    }
}

static void poll(void *arg)
{
    (void)arg;
    uint32_t now = mc_hal_now_ms();
    led_apply(now);
    if (board->button.gpio >= 0) {
        bool pressed = (gpio_get_level(board->button.gpio) != 0) == board->button.active_high;
        mc_ev_kind_t kind;
        if (mc_button_poll(&button, now, pressed, &kind)) {
            mc_event_t ev = {.kind = kind};
            mc_app_post(&ev);
        }
    }
}

void mc_hal_gpio_init(const mc_board_t *b)
{
    board = b;
    mc_button_init(&button);
    if (b->led.gpio >= 0) {
        gpio_reset_pin(b->led.gpio);
        gpio_set_direction(b->led.gpio, GPIO_MODE_OUTPUT);
        gpio_set_level(b->led.gpio, !b->led.active_high);
    }
    if (b->sensor_power.present) { /* off until the first sample asks for it */
        gpio_reset_pin(b->sensor_power.gpio);
        gpio_set_level(b->sensor_power.gpio, !b->sensor_power.active_high);
        gpio_set_direction(b->sensor_power.gpio, GPIO_MODE_OUTPUT);
    }
    if (b->button.gpio >= 0) {
        gpio_reset_pin(b->button.gpio);
        gpio_set_direction(b->button.gpio, GPIO_MODE_INPUT);
        if (b->button.active_high) {
            gpio_pulldown_en(b->button.gpio);
        } else {
            gpio_pullup_en(b->button.gpio);
        }
    }
}

void mc_hal_button_start(void)
{
    static esp_timer_handle_t t;
    const esp_timer_create_args_t args = {.callback = poll, .name = "mc_ui"};
    ESP_ERROR_CHECK(esp_timer_create(&args, &t));
    ESP_ERROR_CHECK(esp_timer_start_periodic(t, 10 * 1000));
}
