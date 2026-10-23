#ifndef MC_BOARD_H
#define MC_BOARD_H

#include <stdbool.h>
#include <stdint.h>

/* What a logical port can be (PlantModule/specs.md 2.1). */
#define MC_ROLE_MOISTURE 0x01u
#define MC_ROLE_PUMP 0x02u

#define MC_MAX_PORTS 6

typedef struct {
    uint8_t gpio;  /* informational for the core; the HAL resolves pins from its own table */
    uint8_t roles; /* MC_ROLE_* bits */
} mc_board_port_t;

/* One PCB revision. The table is generated from firmware/boards/<name>.json (scripts/gen_boards.py). */
/* A fixed pin of the board; gpio -1 = not present. */
typedef struct {
    int8_t gpio;
    bool active_high; /* LED: on = high; button: pressed = high (false: pressed = low) */
} mc_board_pin_t;

typedef struct {
    const char *name;
    uint8_t hw_version;
    bool allow_raw_gpio;
    uint8_t port_count;
    mc_board_pin_t led;
    mc_board_pin_t button;
    int8_t battery_gpio;      /* -1: no battery divider */
    uint16_t battery_divider_x100; /* Vbat = Vpin * divider / 100 */
    mc_board_port_t ports[MC_MAX_PORTS];
} mc_board_t;

/* NULL for a name the firmware does not know. */
const mc_board_t *mc_board_find(const char *name);

#endif
