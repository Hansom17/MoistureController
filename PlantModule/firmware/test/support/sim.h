#ifndef SIM_H
#define SIM_H

/* A fake world for mc_core: clock, timers, pump pins, LED, radio log and a scripted ADC. The core is driven
 * only through sim_send() and sim_advance(); every action it returns is executed here. */

#include <stdbool.h>
#include <stdint.h>

#include "mc_core.h"
#include "unity.h"

#define SIM_MAX_TIMERS 48
#define SIM_MAX_LOG 256

typedef struct {
    bool used;
    uint32_t fire_ms;
    mc_event_t ev;
} sim_pending_t;

typedef struct {
    uint32_t t;
    uint16_t n;
    uint32_t cmd_id;
    uint8_t state, reason;
    uint16_t ends_in_s;
} sim_ack_t;

typedef struct {
    uint32_t t;
    uint16_t n;
    uint8_t code, slot;
    uint16_t arg;
} sim_event_t;

typedef struct {
    mc_core_t core;
    uint32_t now;
    sim_pending_t timers[SIM_MAX_TIMERS];

    /* outputs */
    bool pump_on[MC_NUM_SLOTS];
    uint32_t pump_on_since[MC_NUM_SLOTS];
    uint32_t longest_pump_run_ms;
    int pump_edges[MC_NUM_SLOTS];
    mc_led_t led;

    /* radio */
    sim_ack_t acks[SIM_MAX_LOG];
    int n_acks;
    sim_event_t events[SIM_MAX_LOG];
    int n_events;
    int reports, attr_updates;
    uint32_t last_report_ms;
    mc_attrs_t attrs;
    bool link_up_in_sim; /* what the radio would do: acks while this is false are a bug */
    int acks_sent_while_down;

    /* platform */
    bool zigbee_started, steering_started, left, erased;
    int reboots, rejoin_calls, persist_config_calls, persist_diag_calls, read_slot_calls;
    mc_config_t persisted_config;
    mc_diag_t persisted_diag;
    mc_led_t led_history[16];
    int n_led;

    /* scripted ADC: raw value per slot, ok flag, silent = never answers (timeout) */
    uint16_t adc_raw[MC_NUM_SLOTS];
    bool adc_ok[MC_NUM_SLOTS];
    bool adc_silent[MC_NUM_SLOTS];
    uint32_t adc_delay_ms;
    uint16_t batt_pin_mv; /* what the battery divider pin reads */
    bool batt_ok, batt_silent;
    int read_battery_calls;

    /* switched sensor supply */
    bool rail_on;
    uint32_t rail_on_since;
    int rail_on_calls, rail_off_calls;
    int reads_without_power;     /* slot reads while the rail was off on a board that switches it */
    int reads_before_settled;    /* ... or before the settle time was over */
    mc_board_t custom_board;     /* sim_init_board: a copy of the board the core runs on */

    /* all action kinds in order, for ordering assertions */
    mc_act_kind_t kinds[SIM_MAX_LOG * 4];
    int n_kinds;
    bool overflow_seen;
    mc_actions_t last;
} sim_t;

typedef struct {
    bool factory_invalid;
    bool first_boot;
    uint8_t reset_reason; /* mc_boot_reason_t, default power on */
    uint8_t crash_count_stored;
    bool config_invalid;
    const mc_config_t *config;
    uint16_t boot_id;
} sim_boot_opts_t;

/* ---- setup ---- */
void sim_init(sim_t *s, const char *board_name);
void sim_init_board(sim_t *s, const mc_board_t *board); /* a board description built by the test */
void sim_boot(sim_t *s, const sim_boot_opts_t *opts);
/* boot, stack ready (joined): the module is in the Operational state with the given configuration */
void sim_to_operational(sim_t *s, const mc_config_t *cfg);
/* A carrier-v1 configuration with a moisture sensor on slot 0 (P1) and a pump on slot 2 (P3). */
void sim_cfg_default(mc_config_t *c);

/* ---- driving ---- */
void sim_send(sim_t *s, mc_event_t ev);
void sim_advance(sim_t *s, uint32_t ms);

mc_event_t ev_simple(mc_ev_kind_t kind);
mc_event_t ev_bool(mc_ev_kind_t kind, bool v);
mc_event_t ev_pump_run(uint32_t id, uint8_t slot, uint16_t seconds, uint16_t ttl_s);
mc_event_t ev_pump_stop(uint32_t id, uint8_t slot);
mc_event_t ev_cancel(uint32_t id, uint32_t target);
mc_event_t ev_action(uint32_t id, uint8_t action);
mc_event_t ev_commit(uint16_t rev);
mc_event_t ev_write_u16(uint16_t attr, uint16_t v);
mc_event_t ev_write_bytes(uint16_t attr, const uint8_t *b, uint8_t n);
mc_event_t ev_write_slot(uint8_t idx, const mc_slot_cfg_t *cfg);
mc_event_t ev_timer(mc_timer_t id, uint8_t arg);
mc_event_t ev_battery(uint16_t pin_mv); /* a BATT_SAMPLE with this pin voltage */

/* ---- inspection ---- */
const sim_ack_t *sim_last_ack(const sim_t *s);
const sim_ack_t *sim_find_ack(const sim_t *s, uint32_t cmd_id, int nth); /* nth answer to a command id */
int sim_count_acks(const sim_t *s, uint32_t cmd_id);
int sim_count_events(const sim_t *s, uint8_t code);
int sim_count_kind(const sim_t *s, mc_act_kind_t kind);
bool sim_timer_armed(const sim_t *s, mc_timer_t id, uint8_t arg);
void sim_clear_logs(sim_t *s);

/* The `slot_cfg_n` bytes a configuration slot is written as (what the converter sends). */
uint8_t sim_encode_slot(const mc_slot_cfg_t *c, uint8_t out[8]);

#define ASSERT_LC(sim, state) TEST_ASSERT_EQUAL_INT_MESSAGE((state), (sim)->core.lc, "lifecycle state")
#define ASSERT_ACK(sim, id, st, rs)                                                                                   \
    do {                                                                                                              \
        const sim_ack_t *a_ = sim_find_ack((sim), (id), -1);                                                          \
        TEST_ASSERT_NOT_NULL_MESSAGE(a_, "no answer for the command");                                                \
        TEST_ASSERT_EQUAL_INT_MESSAGE((st), a_->state, "ack state");                                                  \
        TEST_ASSERT_EQUAL_INT_MESSAGE((rs), a_->reason, "ack reason");                                                \
    } while (0)

#endif
