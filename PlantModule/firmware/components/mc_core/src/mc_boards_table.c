/* GENERATED from the JSON files in PlantModule/firmware/boards by PlantModule/scripts/gen_boards.py. Do not edit. */
#include "mc_board.h"

#include <string.h>

static const mc_board_t board_carrier_v1 = {
    .name = "carrier-v1",
    .hw_version = 1,
    .allow_raw_gpio = false,
    .port_count = 4,
    .led = { .gpio = 20, .active_high = true },
    .button = { .gpio = 21, .active_high = false },
    .battery_gpio = 5,
    .battery_divider_x100 = 200,
    .ports = {
        { .gpio = 1, .roles = MC_ROLE_MOISTURE | MC_ROLE_PUMP },
        { .gpio = 2, .roles = MC_ROLE_MOISTURE | MC_ROLE_PUMP },
        { .gpio = 3, .roles = MC_ROLE_MOISTURE | MC_ROLE_PUMP },
        { .gpio = 4, .roles = MC_ROLE_MOISTURE | MC_ROLE_PUMP },
    },
};

static const mc_board_t board_devkitc_1 = {
    .name = "devkitc-1",
    .hw_version = 0,
    .allow_raw_gpio = true,
    .port_count = 6,
    .led = { .gpio = 8, .active_high = true },
    .button = { .gpio = 9, .active_high = false },
    .battery_gpio = -1,
    .battery_divider_x100 = 100,
    .ports = {
        { .gpio = 1, .roles = MC_ROLE_MOISTURE | MC_ROLE_PUMP },
        { .gpio = 2, .roles = MC_ROLE_MOISTURE | MC_ROLE_PUMP },
        { .gpio = 3, .roles = MC_ROLE_MOISTURE | MC_ROLE_PUMP },
        { .gpio = 4, .roles = MC_ROLE_MOISTURE | MC_ROLE_PUMP },
        { .gpio = 6, .roles = MC_ROLE_MOISTURE | MC_ROLE_PUMP },
        { .gpio = 7, .roles = MC_ROLE_PUMP },
    },
};

static const mc_board_t *const all_boards[] = {
    &board_carrier_v1,
    &board_devkitc_1,
};

const mc_board_t *mc_board_find(const char *name)
{
    for (size_t i = 0; i < sizeof all_boards / sizeof all_boards[0]; i++) {
        if (strcmp(all_boards[i]->name, name) == 0) {
            return all_boards[i];
        }
    }
    return NULL;
}
