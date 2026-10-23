#ifndef MC_FACTORY_H
#define MC_FACTORY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* The raw 4 KB `factory` partition (PlantModule/specs.md 10). The first 64 bytes carry the data:
 *   0..3 magic "MCF2" · 4 version · 5..20 board (16, NUL padded) · 21..32 serial (12, ASCII)
 *   33..50 install code (16 bytes + CRC16 LE; all 0xFF when absent) · 51 flags (bit 0: install code required)
 *   52..59 reserved (zero) · 60..63 CRC32 (IEEE, little endian) over bytes 0..59. The rest is 0xFF. */
#define MC_FACTORY_HEADER_SIZE 64
#define MC_FACTORY_VERSION 1
#define MC_FACTORY_FLAG_INSTALL_CODE_REQUIRED 0x01

typedef struct {
    char board[17];
    char serial[13];
    bool has_install_code;
    uint8_t install_code[16];
    bool install_code_required;
} mc_factory_t;

uint32_t mc_crc32(const uint8_t *data, size_t len);

/* CRC-16/X-25 as used for Zigbee install codes (Base Device Behavior spec). */
uint16_t mc_crc16_x25(const uint8_t *data, size_t len);

/* False when magic, version, CRC32 or the install code CRC is wrong, or the code is required but missing. */
bool mc_factory_parse(const uint8_t *buf, size_t len, mc_factory_t *out);

/* The image the provisioning tool writes (host tests and scripts/make_label.py share the layout). */
void mc_factory_build(uint8_t out[MC_FACTORY_HEADER_SIZE], const char *board, const char *serial,
                      const uint8_t *install_code_or_null, bool required);

#endif
