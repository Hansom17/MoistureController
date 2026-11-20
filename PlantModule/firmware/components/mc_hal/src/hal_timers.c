#include "esp_timer.h"
#include "mc_hal.h"

#define N_IDS 20
#define N_ARGS MC_NUM_SLOTS

typedef struct {
    esp_timer_handle_t h;
    mc_timer_t id;
    uint8_t arg;
} slot_t;

static slot_t timers[N_IDS][N_ARGS];
static void (*wake_at)(uint8_t key, uint32_t ms);
static void (*wake_cancel)(uint8_t key);

static uint8_t key_of(mc_timer_t id, uint8_t arg)
{
    return (uint8_t)((int)id * N_ARGS + arg);
}

void mc_hal_set_wake_hooks(void (*at)(uint8_t, uint32_t), void (*cancel)(uint8_t))
{
    wake_at = at;
    wake_cancel = cancel;
}

static void fired(void *ctx)
{
    const slot_t *s = ctx;
    mc_event_t ev = {.kind = MC_EV_TIMER};
    ev.u.timer.id = s->id;
    ev.u.timer.arg = s->arg;
    mc_app_post(&ev);
}

void mc_hal_timers_init(void)
{
    for (int i = 0; i < N_IDS; i++) {
        for (int a = 0; a < N_ARGS; a++) {
            slot_t *s = &timers[i][a];
            s->id = (mc_timer_t)i;
            s->arg = (uint8_t)a;
            esp_timer_create_args_t args = {.callback = fired, .arg = s, .name = "mc"};
            ESP_ERROR_CHECK(esp_timer_create(&args, &s->h));
        }
    }
}

void mc_hal_timer_arm(mc_timer_t id, uint8_t arg, uint32_t delay_ms)
{
    if ((int)id >= N_IDS || arg >= N_ARGS) {
        return;
    }
    esp_timer_handle_t h = timers[id][arg].h;
    esp_timer_stop(h);
    ESP_ERROR_CHECK(esp_timer_start_once(h, (uint64_t)delay_ms * 1000u));
    if (wake_at != NULL) {
        wake_at(key_of(id, arg), delay_ms);
    }
}

void mc_hal_timer_cancel(mc_timer_t id, uint8_t arg)
{
    if ((int)id < N_IDS && arg < N_ARGS) {
        esp_timer_stop(timers[id][arg].h);
        if (wake_cancel != NULL) {
            wake_cancel(key_of(id, arg));
        }
    }
}

uint32_t mc_hal_now_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}
