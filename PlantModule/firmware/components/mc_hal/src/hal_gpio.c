#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/timers.h"
#include "mc_hal.h"
#include "mc_ui.h"

static const char *TAG = "mc_gpio";

static const mc_board_t *board;
static mc_led_t led_pattern = MC_LED_OFF;
static uint32_t led_since_ms;
static mc_button_t button;
static bool pump_is_output[GPIO_NUM_MAX];
static esp_timer_handle_t poll_timer;
static bool poll_running;

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
        gpio_hold_dis(gpio); /* released after a deep sleep that held it */
        gpio_reset_pin(gpio);
        gpio_set_level(gpio, level); /* level first, so the pin never glitches to the wrong state */
        gpio_set_direction(gpio, GPIO_MODE_OUTPUT);
        gpio_sleep_sel_dis(gpio); /* keep the level in light sleep instead of isolating the pad */
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

void mc_hal_outputs_hold(const mc_config_t *cfg, bool hold)
{
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        const mc_slot_cfg_t *s = &cfg->slots[i];
        int g = s->module == MC_MODULE_PUMP ? gpio_of_port(s->port) : -1;
        if (g >= 0 && g < GPIO_NUM_MAX) {
            hold ? gpio_hold_en(g) : gpio_hold_dis(g);
        }
    }
    if (board != NULL && board->sensor_power.present) {
        hold ? gpio_hold_en(board->sensor_power.gpio) : gpio_hold_dis(board->sensor_power.gpio);
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

static void start_poll(void)
{
    if (poll_timer != NULL && !poll_running) {
        poll_running = true;
        esp_timer_start_periodic(poll_timer, 10 * 1000);
    }
}

/* The 10 ms poll only runs while something needs it (a blinking LED pattern, a button that is down or settling):
 * a permanent 100 Hz timer would keep the chip from sleeping. */
static bool poll_needed(void)
{
    bool led_moves = led_pattern != MC_LED_OFF && led_pattern != MC_LED_SOLID;
    return led_moves || button.raw || button.stable;
}

void mc_hal_led_set(mc_led_t pattern)
{
    if (pattern != led_pattern) {
        led_pattern = pattern;
        led_since_ms = mc_hal_now_ms();
        led_apply(led_since_ms);
    }
    if (poll_needed()) {
        start_poll();
    }
}

static bool button_level_is_press(void)
{
    return (gpio_get_level(board->button.gpio) != 0) == board->button.active_high;
}

static void poll(void *arg)
{
    (void)arg;
    uint32_t now = mc_hal_now_ms();
    led_apply(now);
    if (board->button.gpio >= 0) {
        mc_ev_kind_t kind;
        if (mc_button_poll(&button, now, button_level_is_press(), &kind)) {
            mc_event_t ev = {.kind = kind};
            mc_app_post(&ev);
        }
    }
    if (!poll_needed()) {
        esp_timer_stop(poll_timer);
        poll_running = false;
        if (board->button.gpio >= 0) {
            gpio_intr_enable(board->button.gpio); /* the next press wakes us again */
        }
    }
}

/* runs in the timer service task */
static void start_poll_from_isr(void *p, uint32_t u)
{
    (void)p;
    (void)u;
    start_poll();
}

static void IRAM_ATTR button_isr(void *arg)
{
    (void)arg;
    gpio_intr_disable(board->button.gpio); /* a level interrupt: off until the poll has seen the button released */
    BaseType_t woken = pdFALSE;
    xTimerPendFunctionCallFromISR(start_poll_from_isr, NULL, 0, &woken);
    if (woken) {
        portYIELD_FROM_ISR();
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
        gpio_sleep_sel_dis(b->led.gpio);
    }
    if (b->sensor_power.present) { /* off until the first sample asks for it */
        gpio_hold_dis(b->sensor_power.gpio);
        gpio_reset_pin(b->sensor_power.gpio);
        gpio_set_level(b->sensor_power.gpio, !b->sensor_power.active_high);
        gpio_set_direction(b->sensor_power.gpio, GPIO_MODE_OUTPUT);
        gpio_sleep_sel_dis(b->sensor_power.gpio);
    }
    if (b->button.gpio >= 0) {
        gpio_reset_pin(b->button.gpio);
        gpio_set_direction(b->button.gpio, GPIO_MODE_INPUT);
        if (b->button.active_high) {
            gpio_pulldown_en(b->button.gpio);
        } else {
            gpio_pullup_en(b->button.gpio);
        }
        gpio_sleep_sel_dis(b->button.gpio); /* the pull stays on in light sleep, else the pad floats and wakes us */
    }
}

void mc_hal_button_start(void)
{
    const esp_timer_create_args_t args = {.callback = poll, .name = "mc_ui"};
    ESP_ERROR_CHECK(esp_timer_create(&args, &poll_timer));
    if (board->button.gpio >= 0) {
        gpio_int_type_t level = board->button.active_high ? GPIO_INTR_HIGH_LEVEL : GPIO_INTR_LOW_LEVEL;
        gpio_install_isr_service(0);
        gpio_set_intr_type(board->button.gpio, level);
        gpio_isr_handler_add(board->button.gpio, button_isr, NULL);
        gpio_wakeup_enable(board->button.gpio, level); /* a press wakes light sleep */
        esp_sleep_enable_gpio_wakeup();
        gpio_intr_enable(board->button.gpio);
    }
    start_poll(); /* the first run decides whether the poll is needed at all */
}
