#ifndef MC_UI_H
#define MC_UI_H

/* Pure helpers of the HAL, kept here so they run in the host tests: LED patterns and the button decoder. */

#include <stdbool.h>
#include <stdint.h>

#include "mc_core.h"

/* LED level (true = lit) of a pattern at time t_ms since the pattern started (PlantModule/specs.md 9). */
bool mc_led_level(mc_led_t pattern, uint32_t t_ms);

/* Button: debounce and hold detection. Feed the raw pressed state every poll (about every 10-20 ms). */
#define MC_BTN_DEBOUNCE_MS 40u
#define MC_BTN_HOLD_3S_MS 3000u
#define MC_BTN_HOLD_10S_MS 10000u

typedef struct {
    bool stable;        /* debounced pressed state */
    bool raw;           /* last raw state */
    uint32_t raw_since; /* when raw last changed */
    uint32_t pressed_at;
    bool sent_3s, sent_10s;
} mc_button_t;

void mc_button_init(mc_button_t *b);

/* Returns true and sets *kind when the poll produced an event: HOLD_3S, HOLD_10S while held; SHORT when
 * released before 3 s; RELEASE when released after a hold event. */
bool mc_button_poll(mc_button_t *b, uint32_t now_ms, bool pressed, mc_ev_kind_t *kind);

#endif
