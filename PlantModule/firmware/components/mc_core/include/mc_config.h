#ifndef MC_CONFIG_H
#define MC_CONFIG_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "mc_board.h"
#include "mc_interface.h"

#define MC_NUM_SLOTS 6
#define MC_PUMP_HARD_MAX_S 300 /* firmware ceiling of one pump run (specs 6) */
#define MC_SAMPLES_MAX 64
#define MC_PORT_RAW_FLAG 0x80u /* port byte 0x80 + n = raw GPIO n, only on boards that allow it */
#define MC_SLOT_NONE 0xFFu     /* "the device as a whole" in an error */

/* One entry of the slot table (attribute slot_cfg_n, PlantModule/interface.yaml layout slot_config). */
typedef struct {
    uint8_t module; /* mc_module_t */
    uint8_t port;   /* 0..5 = P1..P6, or MC_PORT_RAW_FLAG + gpio */
    bool active_high;
    uint16_t cal_dry; /* moisture */
    uint16_t cal_wet;
    uint8_t samples;
    uint16_t max_run_s; /* pump */
    uint16_t min_pause_s;
} mc_slot_cfg_t;

typedef struct {
    uint16_t rev;
    uint16_t report_interval_s;
    uint16_t fast_report_interval_s;
    uint16_t fast_report_hold_s;
    uint16_t batt_low_mv;
    mc_slot_cfg_t slots[MC_NUM_SLOTS];
} mc_config_t;

/* The first error of a configuration: mc_cfg_error_t code and the slot (MC_SLOT_NONE for the device). */
typedef struct {
    uint8_t code;
    uint8_t slot;
} mc_cfg_err_t;

/* Empty slot table, default intervals (a new device: nothing is driven without a configuration). */
void mc_config_default(mc_config_t *c);

/* Decodes an slot_cfg_n value. False when the bytes are too short for the module. */
bool mc_slot_cfg_parse(const uint8_t *bytes, size_t len, mc_slot_cfg_t *out);

/* Validation of a whole configuration against the board (specs 7.6). */
bool mc_config_validate(const mc_config_t *c, const mc_board_t *board, mc_cfg_err_t *err);

/* Same content, revision ignored. */
bool mc_config_same(const mc_config_t *a, const mc_config_t *b);
bool mc_slot_cfg_same(const mc_slot_cfg_t *a, const mc_slot_cfg_t *b);

/* cfg_error attribute value: error code in the high byte, slot in the low byte. */
static inline uint16_t mc_cfg_err_wire(mc_cfg_err_t e)
{
    return (uint16_t)((e.code << 8) | e.slot);
}

/* Stored form of a configuration (NVS blob): schema byte, fields little endian, CRC32 last. Independent of the
 * struct layout so that a firmware update can read what an older one wrote. */
#define MC_CONFIG_BLOB_SIZE 87

size_t mc_config_encode(const mc_config_t *c, uint8_t out[MC_CONFIG_BLOB_SIZE]);

/* False for a wrong length, an unknown schema or a bad CRC. */
bool mc_config_decode(const uint8_t *buf, size_t len, mc_config_t *out);

#endif
