#ifndef MC_CORE_H
#define MC_CORE_H

/* The portable core of the PlantModule firmware (PlantModule/specs.md 7): finite state machines without any
 * hardware access. The application task feeds events into mc_core_step() and executes the returned actions;
 * on the host the same code runs with a fake clock and fake I/O. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "mc_board.h"
#include "mc_config.h"
#include "mc_interface.h"

/* ---- lifecycle ---------------------------------------------------------------------------------------- */

typedef enum {
    MC_LC_BOOT,
    MC_LC_STACK_STARTING,
    MC_LC_UNPROVISIONED,
    MC_LC_STEERING,
    MC_LC_INTERVIEWING,
    MC_LC_OPERATIONAL,
    MC_LC_REJOINING,
    MC_LC_FACTORY_RESET,
    MC_LC_SAFE_MODE,
} mc_lc_state_t;

typedef enum {
    MC_SN_IDLE,
    MC_SN_SETTLING, /* the switched sensor supply is on, the sensors settle (PlantModule/specs.md 18.4) */
    MC_SN_SAMPLING,
    MC_SN_REPORTING,
} mc_sn_state_t;

typedef enum {
    MC_PUMP_OFF,
    MC_PUMP_ON,
    MC_PUMP_PAUSE,
} mc_pump_state_t;

/* Small table of codes for the `last_error` attribute. */
enum {
    MC_ERR_NONE = 0,
    MC_ERR_ZIGBEE_START = 1,
    MC_ERR_SENSOR_FAULT = 2,
    MC_ERR_CONFIG_REJECTED = 3,
    MC_ERR_CONFIG_STORED_INVALID = 4,
    MC_ERR_PUMP_HW = 5,
};

/* ---- time budgets (ms) ------------------------------------------------------------------------------------- */

#define MC_ZB_START_TIMEOUT_MS 10000u
#define MC_STEERING_TIMEOUT_MS 180000u
#define MC_INTERVIEW_TIMEOUT_MS 120000u
#define MC_STABLE_MS 300000u
#define MC_CFG_TXN_TIMEOUT_MS 30000u
#define MC_SLOT_READ_TIMEOUT_MS 500u
#define MC_SAMPLE_WINDOW_MS 2000u
#define MC_REPORT_TIMEOUT_MS 5000u
#define MC_FIRST_SAMPLE_MS 1000u
#define MC_IDENTIFY_MS 10000u
#define MC_REJOIN_FIRST_MS 5000u
#define MC_REJOIN_MAX_MS 300000u
#define MC_TOMBSTONE_MS 600000u
#define MC_CRASH_LOOP_COUNT 3
/* The battery tunables (MC_BATT_*) come from the generated mc_interface.h. */

#define MC_MAX_PENDING_MSGS 8
#define MC_MAX_CMD_RECORDS 8
#define MC_MAX_TOMBSTONES 4

/* ---- events -------------------------------------------------------------------------------------------------- */

typedef enum {
    MC_EV_BOOT,
    MC_EV_CRASH_LOOP,
    MC_EV_ZB_STACK_READY,
    MC_EV_ZB_STEERING_DONE,
    MC_EV_ZB_JOINED,
    MC_EV_ZB_CONFIGURED,
    MC_EV_ZB_PARENT_LOST,
    MC_EV_ZB_REJOIN_DONE,
    MC_EV_ZB_LEFT,
    MC_EV_ZB_ATTR_WRITE,
    MC_EV_ZB_CMD,
    MC_EV_ZB_REPORT_RESULT,
    MC_EV_TIMER,
    MC_EV_ADC_DONE,
    MC_EV_BTN_SHORT,
    MC_EV_BTN_HOLD_3S,
    MC_EV_BTN_HOLD_10S,
    MC_EV_BTN_RELEASE,
    MC_EV_BATT_SAMPLE,
} mc_ev_kind_t;

typedef enum {
    MC_TIMER_SAMPLE,
    MC_TIMER_SLOT,
    MC_TIMER_SAMPLE_WINDOW,
    MC_TIMER_REPORT,
    MC_TIMER_FAST_HOLD,
    MC_TIMER_STEERING,
    MC_TIMER_INTERVIEW,
    MC_TIMER_REJOIN,
    MC_TIMER_ZB_START,
    MC_TIMER_PUMP_END,
    MC_TIMER_PUMP_PAUSE,
    MC_TIMER_CFG_TXN,
    MC_TIMER_STABLE,
    MC_TIMER_IDENTIFY,
    MC_TIMER_BATTERY,
    MC_TIMER_SETTLE,
} mc_timer_t;

typedef enum {
    MC_CMD_PUMP_RUN,
    MC_CMD_PUMP_STOP,
    MC_CMD_CANCEL,
    MC_CMD_DEVICE_ACTION,
    MC_CMD_COMMIT_CONFIG,
} mc_cmd_kind_t;

typedef struct {
    mc_cmd_kind_t kind;
    uint32_t cmd_id;
    uint8_t slot;     /* pump_run, pump_stop */
    uint16_t seconds; /* pump_run */
    uint16_t ttl_s;   /* pump_run */
    uint32_t target;  /* cancel */
    uint8_t action;   /* device_action: mc_device_action_t */
    uint16_t arg;
    uint16_t rev; /* commit_config */
} mc_cmd_t;

typedef struct {
    bool factory_valid;
    bool first_boot; /* first start after flashing or a factory reset */
    uint8_t reset_reason; /* mc_boot_reason_t */
    uint8_t crash_count_stored;
    uint16_t reset_count_stored;
    uint16_t rejoin_count_stored;
    uint16_t last_error_stored;
    uint16_t boot_id;
    bool config_valid;
    mc_config_t config;
} mc_boot_t;

typedef struct {
    mc_ev_kind_t kind;
    uint32_t now_ms; /* the clock of the application task; the core never reads a clock itself */
    union {
        mc_boot_t boot;
        bool ok;                                      /* STEERING_DONE, REJOIN_DONE, REPORT_RESULT */
        bool joined;                                  /* STACK_READY */
        struct { uint16_t attr; uint8_t data[24]; uint8_t len; } write;
        mc_cmd_t cmd;
        struct { mc_timer_t id; uint8_t arg; } timer; /* arg: slot of the per-slot timers */
        struct { uint8_t slot; bool ok; uint16_t raw; } adc;
        struct { uint16_t mv; bool ok; } batt;        /* BATT_SAMPLE: millivolts at the ADC pin */
    } u;
} mc_event_t;

/* ---- actions -------------------------------------------------------------------------------------------------- */

typedef enum {
    MC_ACT_START_ZIGBEE,
    MC_ACT_START_STEERING,
    MC_ACT_REJOIN,
    MC_ACT_LEAVE_NETWORK,
    MC_ACT_ERASE_STATE,     /* configuration and network state */
    MC_ACT_UPDATE_ATTRS,    /* write mc_core_attrs() into the attribute store */
    MC_ACT_REPORT_NOW,      /* send the changed attributes at once */
    MC_ACT_SEND_CMD_ACK,
    MC_ACT_SEND_EVENT,
    MC_ACT_DRIVE_PUMP,
    MC_ACT_ALL_OUTPUTS_OFF,
    MC_ACT_READ_SLOT,
    MC_ACT_READ_BATTERY,    /* measure the pin of the battery divider, answer with BATT_SAMPLE */
    MC_ACT_SENSOR_POWER,    /* switch the sensor supply (boards with a switched rail only) */
    MC_ACT_PERSIST_CONFIG,  /* store core->cfg atomically */
    MC_ACT_PERSIST_DIAG,    /* store core->diag */
    MC_ACT_SET_LED,
    MC_ACT_ARM_TIMER,
    MC_ACT_CANCEL_TIMER,
    MC_ACT_REBOOT,
} mc_act_kind_t;

typedef enum {
    MC_LED_OFF,
    MC_LED_SOLID,
    MC_LED_SLOW_BLINK,
    MC_LED_FAST_BLINK,
    MC_LED_DOUBLE_BLINK,
    MC_LED_TRIPLE_BLINK,
    MC_LED_IDENTIFY,
} mc_led_t;

typedef struct {
    mc_act_kind_t kind;
    union {
        struct { uint16_t n; uint32_t cmd_id; uint8_t state; uint8_t reason; uint16_t ends_in_s; } ack;
        struct { uint16_t n; uint8_t code; uint8_t slot; uint16_t arg; } event;
        struct { uint8_t slot; uint8_t port; bool active_high; bool on; } pump;
        struct { uint8_t slot; uint8_t port; } read;
        struct { bool on; } sensor_power;
        mc_led_t led;
        struct { mc_timer_t id; uint8_t arg; uint32_t delay_ms; } timer;
    } u;
} mc_action_t;

#define MC_MAX_ACTIONS 48

typedef struct {
    size_t n;
    bool overflow; /* more actions than fit: a bug, the tests assert it never happens */
    mc_action_t a[MC_MAX_ACTIONS];
} mc_actions_t;

/* ---- state ----------------------------------------------------------------------------------------------------- */

typedef struct {
    uint8_t type; /* mc_module_t */
    uint8_t error; /* mc_sensor_error_t */
    int16_t value; /* percent x 100; INT16_MIN = unknown */
    uint16_t raw;
    uint16_t cfg_rev;
} mc_reading_t;

#define MC_VALUE_UNKNOWN ((int16_t)-32768)

/* Everything the attribute store shows (the HAL adds uptime and free heap). */
typedef struct {
    uint16_t seq;
    uint16_t boot_id;
    mc_reading_t readings[MC_NUM_SLOTS];
    uint8_t status;      /* mc_status_t */
    bool fast_mode;
    uint8_t safe_reason; /* mc_safe_reason_t */
    uint16_t cfg_rev;
    uint8_t cfg_result;  /* mc_cfg_result_t */
    uint16_t cfg_error;  /* mc_cfg_err_wire */
    uint8_t boot_reason;
    uint16_t reset_count;
    uint16_t rejoin_count;
    uint16_t last_error;
    uint16_t voltage_mv; /* filtered cell voltage, 0 without a cell */
    uint8_t batt_state;  /* mc_batt_state_t */
} mc_attrs_t;

typedef struct {
    uint8_t crash_count;
    uint16_t reset_count;
    uint16_t rejoin_count;
    uint16_t last_error;
} mc_diag_t;

typedef struct {
    mc_pump_state_t state;
    uint8_t rec; /* index of the running command record */
} mc_pump_t;

typedef struct {
    bool used;
    uint32_t cmd_id;
    uint8_t kind;
    uint8_t state; /* mc_ack_state_t of the last answer */
    uint8_t reason;
    uint16_t ends_in_s;
    bool running;
} mc_cmd_rec_t;

typedef struct {
    bool used;
    uint32_t cmd_id;
    uint32_t expires_ms;
} mc_tombstone_t;

typedef struct {
    bool is_event;
    uint16_t n;
    uint32_t cmd_id;
    uint8_t state, reason, code, slot;
    uint16_t value; /* ends_in_s or event arg */
} mc_msg_t;

typedef struct {
    uint8_t error;
    int16_t value;
    uint16_t raw;
} mc_sample_t;

typedef struct mc_core {
    const mc_board_t *board; /* NULL: unknown board */
    uint16_t adc_max;
    uint32_t now_ms;

    mc_lc_state_t lc;
    uint8_t safe_reason;
    bool first_boot;
    bool joined;
    bool link_up;
    uint8_t rejoin_attempt;
    uint8_t boot_reason;
    uint16_t boot_id;
    mc_diag_t diag;

    mc_led_t led;
    bool identify;
    bool cue;

    mc_config_t cfg;
    struct {
        bool active;
        bool bad;
        mc_cfg_err_t bad_err;
        mc_config_t cfg;
    } stage;
    uint8_t cfg_result;
    uint16_t cfg_error;

    mc_sn_state_t sn;
    bool sn_active;
    uint8_t sn_cur, sn_next;
    bool fast;
    uint16_t seq;
    mc_reading_t readings[MC_NUM_SLOTS];
    mc_sample_t sample[MC_NUM_SLOTS];
    uint8_t err_streak[MC_NUM_SLOTS];
    bool fault[MC_NUM_SLOTS];
    uint16_t voltage_mv;      /* filtered cell voltage in mV, 0 when absent */
    uint8_t batt_state;       /* mc_batt_state_t */
    uint16_t bat_hist[MC_BATT_FILTER_SAMPLES]; /* last calibrated samples */
    uint8_t bat_n;            /* how many of them are valid */
    uint8_t bat_bad_streak;   /* consecutive samples at or below the threshold of the next worse state */
    bool bat_pending;         /* a READ_BATTERY is out and the sample waits for it */
    bool sensor_rail_on;      /* the switched sensor supply is on */
    bool have_pump_end;
    uint32_t last_pump_end_ms;

    mc_pump_t pump[MC_NUM_SLOTS];
    mc_cmd_rec_t recs[MC_MAX_CMD_RECORDS];
    uint8_t rec_next;
    mc_tombstone_t tombs[MC_MAX_TOMBSTONES];

    uint16_t ack_n, event_n;
    mc_msg_t pending[MC_MAX_PENDING_MSGS];
    uint8_t pending_n;
} mc_core_t;

/* A core that has not seen BOOT yet. `board` may be NULL (unknown board -> safe mode). */
void mc_core_init(mc_core_t *c, const mc_board_t *board, uint16_t adc_max);

/* The one entry point: apply an event, return the actions to execute (in order). */
void mc_core_step(mc_core_t *c, const mc_event_t *ev, mc_actions_t *out);

/* Read-only views for the HAL. */
void mc_core_attrs(const mc_core_t *c, mc_attrs_t *out);
void mc_encode_slot_reading(const mc_reading_t *r, uint8_t out[8]);
bool mc_core_pump_running(const mc_core_t *c);

/* ---- sleeping (PlantModule/specs.md 18.4); the core never sleeps itself, the HAL asks ---------------------- */

typedef enum {
    MC_SLEEP_NONE,  /* stay awake with the receiver on */
    MC_SLEEP_LIGHT, /* radio off between parent polls, RAM and timers kept */
    MC_SLEEP_DEEP,  /* chip off until the next wake */
} mc_sleep_t;

/* What the HAL may do right now: NONE while anything is going on (not operational, sampling or settling, a report in
 * flight, a configuration transaction, messages waiting for the link, the LED showing a state of its own) and in
 * `always_on`; with a pump running or in fast mode a configured deep sleep is only light sleep (rule L7). */
mc_sleep_t mc_core_sleep_allowed(const mc_core_t *c);

/* The parent poll interval to use in light sleep: the configured one, at most 1000 ms while a pump runs so a stop
 * arrives quickly. */
uint16_t mc_core_poll_ms(const mc_core_t *c);

#endif
