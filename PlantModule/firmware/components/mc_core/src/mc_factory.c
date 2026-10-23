#include "mc_factory.h"

#include <string.h>

uint32_t mc_crc32(const uint8_t *data, size_t len)
{
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int k = 0; k < 8; k++) {
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
        }
    }
    return ~crc;
}

uint16_t mc_crc16_x25(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int k = 0; k < 8; k++) {
            crc = (uint16_t)((crc >> 1) ^ (0x8408u & (0u - (crc & 1u))));
        }
    }
    return (uint16_t)~crc;
}

static uint32_t rd32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void copy_text(char *dst, size_t dst_size, const uint8_t *src, size_t n)
{
    size_t i = 0;
    for (; i < n && i + 1 < dst_size && src[i] != 0 && src[i] != 0xFF; i++) {
        dst[i] = (char)src[i];
    }
    dst[i] = 0;
}

bool mc_factory_parse(const uint8_t *buf, size_t len, mc_factory_t *out)
{
    memset(out, 0, sizeof *out);
    if (len < MC_FACTORY_HEADER_SIZE || memcmp(buf, "MCF2", 4) != 0 || buf[4] != MC_FACTORY_VERSION) {
        return false;
    }
    if (mc_crc32(buf, 60) != rd32(buf + 60)) {
        return false;
    }
    copy_text(out->board, sizeof out->board, buf + 5, 16);
    copy_text(out->serial, sizeof out->serial, buf + 21, 12);
    out->install_code_required = (buf[51] & MC_FACTORY_FLAG_INSTALL_CODE_REQUIRED) != 0;

    bool blank = true;
    for (int i = 33; i < 51; i++) {
        if (buf[i] != 0xFF) {
            blank = false;
        }
    }
    if (!blank) {
        uint16_t stored = (uint16_t)(buf[49] | (buf[50] << 8));
        if (mc_crc16_x25(buf + 33, 16) != stored) {
            return false;
        }
        memcpy(out->install_code, buf + 33, 16);
        out->has_install_code = true;
    }
    if (out->install_code_required && !out->has_install_code) {
        return false;
    }
    return out->board[0] != 0;
}

void mc_factory_build(uint8_t out[MC_FACTORY_HEADER_SIZE], const char *board, const char *serial,
                      const uint8_t *install_code_or_null, bool required)
{
    memset(out, 0, MC_FACTORY_HEADER_SIZE);
    memcpy(out, "MCF2", 4);
    out[4] = MC_FACTORY_VERSION;
    strncpy((char *)out + 5, board, 16);
    strncpy((char *)out + 21, serial, 12);
    if (install_code_or_null) {
        memcpy(out + 33, install_code_or_null, 16);
        uint16_t crc = mc_crc16_x25(install_code_or_null, 16);
        out[49] = (uint8_t)(crc & 0xFF);
        out[50] = (uint8_t)(crc >> 8);
    } else {
        memset(out + 33, 0xFF, 18);
    }
    out[51] = required ? MC_FACTORY_FLAG_INSTALL_CODE_REQUIRED : 0;
    uint32_t crc = mc_crc32(out, 60);
    for (int i = 0; i < 4; i++) {
        out[60 + i] = (uint8_t)(crc >> (8 * i));
    }
}
