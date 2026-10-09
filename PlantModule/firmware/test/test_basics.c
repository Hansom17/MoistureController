/* Leaf modules: moisture conversion, slot tables and configuration validation, factory data, board table,
 * attribute encoding. The byte arrays are the ones the Zigbee2MQTT converter sends and reads
 * (Gateway/firmware/zigbee2mqtt/test/codec.test.mjs): a change on one side fails the other side's tests. */
#include <string.h>

#include "mc_factory.h"
#include "mc_moisture.h"
#include "sim.h"
#include "unity.h"

/* ---- moisture ---- */

static void test_moisture_two_point_calibration(void)
{
    int16_t v = -1;
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OK, mc_moisture_convert(3000, 3000, 1200, 4095, &v));
    TEST_ASSERT_EQUAL_INT16(0, v);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OK, mc_moisture_convert(1200, 3000, 1200, 4095, &v));
    TEST_ASSERT_EQUAL_INT16(10000, v);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OK, mc_moisture_convert(2100, 3000, 1200, 4095, &v));
    TEST_ASSERT_EQUAL_INT16(5000, v);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OK, mc_moisture_convert(2143, 3000, 1200, 4095, &v));
    TEST_ASSERT_INT16_WITHIN(1, 4761, v); /* (3000-2143)/1800 */
}

static void test_moisture_polarity_follows_the_points(void)
{
    int16_t v = 0;
    /* dry < wet: large counts are wetter */
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OK, mc_moisture_convert(1000, 500, 1500, 4095, &v));
    TEST_ASSERT_EQUAL_INT16(5000, v);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OK, mc_moisture_convert(500, 500, 1500, 4095, &v));
    TEST_ASSERT_EQUAL_INT16(0, v);
}

static void test_moisture_clamps_inside_the_tolerance_and_flags_outside(void)
{
    int16_t v = 0;
    /* span 1800, tolerance 270: 3270 is still dry (clamped), 3271 is out of range */
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OK, mc_moisture_convert(3270, 3000, 1200, 4095, &v));
    TEST_ASSERT_EQUAL_INT16(0, v);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OUT_OF_RANGE, mc_moisture_convert(3271, 3000, 1200, 4095, &v));
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OK, mc_moisture_convert(930, 3000, 1200, 4095, &v));
    TEST_ASSERT_EQUAL_INT16(10000, v);
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_OUT_OF_RANGE, mc_moisture_convert(929, 3000, 1200, 4095, &v));
}

static void test_moisture_adc_limits_are_no_signal(void)
{
    int16_t v = 0;
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_NO_SIGNAL, mc_moisture_convert(0, 3000, 1200, 4095, &v));
    TEST_ASSERT_EQUAL_UINT8(MC_SENSOR_ERROR_NO_SIGNAL, mc_moisture_convert(4095, 3000, 1200, 4095, &v));
}

/* ---- slot tables ---- */

static void test_slot_cfg_bytes_as_the_converter_sends_them(void)
{
    mc_slot_cfg_t s;
    const uint8_t moisture[] = {1, 0, 0, 0xb8, 0x0b, 0xb0, 0x04, 16};
    TEST_ASSERT_TRUE(mc_slot_cfg_parse(moisture, sizeof moisture, &s));
    TEST_ASSERT_EQUAL_UINT8(MC_MODULE_MOISTURE, s.module);
    TEST_ASSERT_EQUAL_UINT8(0, s.port);
    TEST_ASSERT_EQUAL_UINT16(3000, s.cal_dry);
    TEST_ASSERT_EQUAL_UINT16(1200, s.cal_wet);
    TEST_ASSERT_EQUAL_UINT8(16, s.samples);

    const uint8_t pump[] = {2, 2, 1, 60, 0, 0x58, 0x02};
    TEST_ASSERT_TRUE(mc_slot_cfg_parse(pump, sizeof pump, &s));
    TEST_ASSERT_EQUAL_UINT8(MC_MODULE_PUMP, s.module);
    TEST_ASSERT_EQUAL_UINT8(2, s.port);
    TEST_ASSERT_TRUE(s.active_high);
    TEST_ASSERT_EQUAL_UINT16(60, s.max_run_s);
    TEST_ASSERT_EQUAL_UINT16(600, s.min_pause_s);

    const uint8_t pump_low[] = {2, 2, 0, 60, 0, 0x58, 0x02};
    TEST_ASSERT_TRUE(mc_slot_cfg_parse(pump_low, sizeof pump_low, &s));
    TEST_ASSERT_FALSE(s.active_high);

    const uint8_t empty[] = {0, 0, 0};
    TEST_ASSERT_TRUE(mc_slot_cfg_parse(empty, sizeof empty, &s));
    TEST_ASSERT_EQUAL_UINT8(MC_MODULE_EMPTY, s.module);
}

static void test_slot_cfg_truncated_values_are_refused(void)
{
    mc_slot_cfg_t s;
    const uint8_t b[] = {1, 0, 0, 0xb8, 0x0b};
    TEST_ASSERT_FALSE(mc_slot_cfg_parse(b, sizeof b, &s));
    TEST_ASSERT_FALSE(mc_slot_cfg_parse(b, 2, &s));
    TEST_ASSERT_FALSE(mc_slot_cfg_parse(b, 6, &s));
    const uint8_t pump[] = {2, 0, 1, 60};
    TEST_ASSERT_FALSE(mc_slot_cfg_parse(pump, sizeof pump, &s));
}

static void test_the_encoder_of_the_sim_matches_the_converter(void)
{
    mc_config_t c;
    sim_cfg_default(&c);
    uint8_t b[8];
    TEST_ASSERT_EQUAL_UINT8(8, sim_encode_slot(&c.slots[0], b));
    const uint8_t moisture[] = {1, 0, 0, 0xb8, 0x0b, 0xb0, 0x04, 16};
    TEST_ASSERT_EQUAL_UINT8_ARRAY(moisture, b, 8);
    TEST_ASSERT_EQUAL_UINT8(7, sim_encode_slot(&c.slots[2], b));
    const uint8_t pump[] = {2, 2, 1, 60, 0, 0x58, 0x02};
    TEST_ASSERT_EQUAL_UINT8_ARRAY(pump, b, 7);
}

/* ---- validation ---- */

static const mc_board_t *carrier(void)
{
    const mc_board_t *b = mc_board_find("carrier-v1");
    TEST_ASSERT_NOT_NULL(b);
    return b;
}

static void expect_error(const mc_config_t *c, uint8_t code, uint8_t slot)
{
    mc_cfg_err_t e = {0};
    TEST_ASSERT_FALSE(mc_config_validate(c, carrier(), &e));
    TEST_ASSERT_EQUAL_UINT8(code, e.code);
    TEST_ASSERT_EQUAL_UINT8(slot, e.slot);
}

static void test_default_and_demo_configurations_are_valid(void)
{
    mc_config_t c;
    mc_config_default(&c);
    TEST_ASSERT_TRUE(mc_config_validate(&c, carrier(), NULL));
    sim_cfg_default(&c);
    TEST_ASSERT_TRUE(mc_config_validate(&c, carrier(), NULL));
}

static void test_validation_ports_roles_and_conflicts(void)
{
    mc_config_t c;
    sim_cfg_default(&c);
    c.slots[1] = (mc_slot_cfg_t){.module = MC_MODULE_MOISTURE, .port = 4, .cal_dry = 3000, .cal_wet = 1200, .samples = 16};
    expect_error(&c, MC_CFG_ERROR_PORT_INVALID, 1); /* carrier-v1 has P1..P4 */
    c.slots[1].port = 0;
    expect_error(&c, MC_CFG_ERROR_PORT_CONFLICT, 1); /* P1 is slot 0's */
    c.slots[1].port = 3;
    TEST_ASSERT_TRUE(mc_config_validate(&c, carrier(), NULL));
    c.slots[1].port = MC_PORT_RAW_FLAG | 5; /* raw GPIOs only on dev kits */
    expect_error(&c, MC_CFG_ERROR_PORT_INVALID, 1);
    TEST_ASSERT_TRUE(mc_config_validate(&c, mc_board_find("devkitc-1"), NULL));
    c.slots[1].module = 9;
    c.slots[1].port = 3;
    expect_error(&c, MC_CFG_ERROR_ROLE_UNSUPPORTED, 1);
}

static void test_validation_ranges(void)
{
    mc_config_t c;
    sim_cfg_default(&c);
    c.slots[0].cal_wet = c.slots[0].cal_dry;
    expect_error(&c, MC_CFG_ERROR_OUT_OF_RANGE, 0);
    c.slots[0].cal_wet = 1200;
    c.slots[0].samples = 0;
    expect_error(&c, MC_CFG_ERROR_OUT_OF_RANGE, 0);
    c.slots[0].samples = 65;
    expect_error(&c, MC_CFG_ERROR_OUT_OF_RANGE, 0);
    c.slots[0].samples = 64;
    c.slots[2].max_run_s = 301; /* above the firmware ceiling */
    expect_error(&c, MC_CFG_ERROR_OUT_OF_RANGE, 2);
    c.slots[2].max_run_s = 0;
    expect_error(&c, MC_CFG_ERROR_OUT_OF_RANGE, 2);
    c.slots[2].max_run_s = 300;
    TEST_ASSERT_TRUE(mc_config_validate(&c, carrier(), NULL));

    c.report_interval_s = 9;
    expect_error(&c, MC_CFG_ERROR_OUT_OF_RANGE, MC_SLOT_NONE);
    c.report_interval_s = 3601;
    expect_error(&c, MC_CFG_ERROR_OUT_OF_RANGE, MC_SLOT_NONE);
    c.report_interval_s = 3600;
    c.fast_report_interval_s = 301;
    expect_error(&c, MC_CFG_ERROR_OUT_OF_RANGE, MC_SLOT_NONE);
    c.fast_report_interval_s = 10;
    c.fast_report_hold_s = 1801;
    expect_error(&c, MC_CFG_ERROR_OUT_OF_RANGE, MC_SLOT_NONE);
    c.fast_report_hold_s = 0;
    TEST_ASSERT_TRUE(mc_config_validate(&c, carrier(), NULL));
}

static void test_cfg_error_wire_format(void)
{
    mc_cfg_err_t e = {.code = MC_CFG_ERROR_PORT_CONFLICT, .slot = 2};
    TEST_ASSERT_EQUAL_HEX16(0x0202, mc_cfg_err_wire(e));
    e.slot = MC_SLOT_NONE;
    e.code = MC_CFG_ERROR_STALE_REV;
    TEST_ASSERT_EQUAL_HEX16(0x05FF, mc_cfg_err_wire(e));
}

static void test_config_same_ignores_the_revision(void)
{
    mc_config_t a, b;
    sim_cfg_default(&a);
    b = a;
    b.rev = 99;
    TEST_ASSERT_TRUE(mc_config_same(&a, &b));
    b.slots[2].max_run_s = 30;
    TEST_ASSERT_FALSE(mc_config_same(&a, &b));
}

/* ---- boards ---- */

static void test_board_table(void)
{
    const mc_board_t *c = carrier();
    TEST_ASSERT_EQUAL_UINT8(4, c->port_count);
    TEST_ASSERT_FALSE(c->allow_raw_gpio);
    TEST_ASSERT_EQUAL_UINT8(MC_ROLE_MOISTURE | MC_ROLE_PUMP, c->ports[0].roles);
    const mc_board_t *d = mc_board_find("devkitc-1");
    TEST_ASSERT_NOT_NULL(d);
    TEST_ASSERT_EQUAL_UINT8(6, d->port_count);
    TEST_ASSERT_TRUE(d->allow_raw_gpio);
    TEST_ASSERT_EQUAL_UINT8(MC_ROLE_PUMP, d->ports[5].roles);
    TEST_ASSERT_NULL(mc_board_find("carrier-v9"));
}

/* ---- factory data ---- */

static void test_crc32_and_crc16_known_values(void)
{
    TEST_ASSERT_EQUAL_HEX32(0xCBF43926u, mc_crc32((const uint8_t *)"123456789", 9)); /* IEEE check value */
    /* the example install code of the Zigbee Base Device Behavior specification */
    const uint8_t code[16] = {0x83, 0xFE, 0xD3, 0x40, 0x7A, 0x93, 0x97, 0x23, 0xA5, 0xC6, 0x39, 0xB2, 0x69, 0x16, 0xD5, 0x05};
    TEST_ASSERT_EQUAL_HEX16(0xB5C3, mc_crc16_x25(code, 16));
}

static const uint8_t INSTALL_CODE[16] = {0x83, 0xFE, 0xD3, 0x40, 0x7A, 0x93, 0x97, 0x23, 0xA5, 0xC6, 0x39, 0xB2, 0x69, 0x16, 0xD5, 0x05};

static void test_factory_data_round_trip(void)
{
    uint8_t img[4096];
    memset(img, 0xFF, sizeof img);
    mc_factory_build(img, "carrier-v1", "MC0000000042", INSTALL_CODE, true);
    mc_factory_t f;
    TEST_ASSERT_TRUE(mc_factory_parse(img, sizeof img, &f));
    TEST_ASSERT_EQUAL_STRING("carrier-v1", f.board);
    TEST_ASSERT_EQUAL_STRING("MC0000000042", f.serial);
    TEST_ASSERT_TRUE(f.has_install_code);
    TEST_ASSERT_TRUE(f.install_code_required);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(INSTALL_CODE, f.install_code, 16);
    /* the layout the provisioning tool must write */
    TEST_ASSERT_EQUAL_MEMORY("MCF2", img, 4);
    TEST_ASSERT_EQUAL_UINT8(1, img[4]);
    TEST_ASSERT_EQUAL_UINT8(0xC3, img[49]); /* CRC16 little endian */
    TEST_ASSERT_EQUAL_UINT8(0xB5, img[50]);
    TEST_ASSERT_EQUAL_UINT8(1, img[51]);
}

static void test_factory_data_without_install_code_for_development(void)
{
    uint8_t img[64];
    mc_factory_build(img, "devkitc-1", "DEV000000001", NULL, false);
    mc_factory_t f;
    TEST_ASSERT_TRUE(mc_factory_parse(img, sizeof img, &f));
    TEST_ASSERT_FALSE(f.has_install_code);
    TEST_ASSERT_FALSE(f.install_code_required);
}

static void test_invalid_factory_data(void)
{
    uint8_t good[64], img[64];
    mc_factory_t f;
    mc_factory_build(good, "carrier-v1", "MC0000000042", INSTALL_CODE, true);

    memcpy(img, good, 64);
    img[0] = 'X';
    TEST_ASSERT_FALSE_MESSAGE(mc_factory_parse(img, 64, &f), "magic");
    memcpy(img, good, 64);
    img[4] = 2;
    TEST_ASSERT_FALSE_MESSAGE(mc_factory_parse(img, 64, &f), "version");
    memcpy(img, good, 64);
    img[10] ^= 0x01;
    TEST_ASSERT_FALSE_MESSAGE(mc_factory_parse(img, 64, &f), "crc32");
    memcpy(img, good, 64);
    TEST_ASSERT_FALSE_MESSAGE(mc_factory_parse(img, 63, &f), "too short");
    memset(img, 0xFF, 64);
    TEST_ASSERT_FALSE_MESSAGE(mc_factory_parse(img, 64, &f), "blank partition");

    /* a wrong install code CRC, with a valid CRC32 over it */
    memcpy(img, good, 64);
    img[34] ^= 0x01;
    uint32_t crc = mc_crc32(img, 60);
    for (int i = 0; i < 4; i++) {
        img[60 + i] = (uint8_t)(crc >> (8 * i));
    }
    TEST_ASSERT_FALSE_MESSAGE(mc_factory_parse(img, 64, &f), "install code crc");

    /* required but absent */
    mc_factory_build(img, "carrier-v1", "MC0000000042", NULL, true);
    TEST_ASSERT_FALSE_MESSAGE(mc_factory_parse(img, 64, &f), "required install code missing");
}

/* ---- attributes ---- */

static void test_slot_reading_bytes_as_the_converter_reads_them(void)
{
    /* the converter test decodes [1,0,0x16,0x10,0x5f,0x08,0x08,0x00] as moisture 41.18 % raw 2143 rev 8 */
    mc_reading_t r = {.type = MC_MODULE_MOISTURE, .error = MC_SENSOR_ERROR_OK, .value = 4118, .raw = 2143, .cfg_rev = 8};
    uint8_t b[8];
    mc_encode_slot_reading(&r, b);
    const uint8_t expect[] = {1, 0, 0x16, 0x10, 0x5f, 0x08, 0x08, 0x00};
    TEST_ASSERT_EQUAL_UINT8_ARRAY(expect, b, 8);

    r.value = MC_VALUE_UNKNOWN;
    r.error = MC_SENSOR_ERROR_NO_SIGNAL;
    mc_encode_slot_reading(&r, b);
    TEST_ASSERT_EQUAL_UINT8(0x00, b[2]);
    TEST_ASSERT_EQUAL_UINT8(0x80, b[3]); /* 0x8000 = unknown */

    r.type = MC_MODULE_PUMP;
    r.value = 10000;
    mc_encode_slot_reading(&r, b);
    TEST_ASSERT_EQUAL_UINT8(0x10, b[2]);
    TEST_ASSERT_EQUAL_UINT8(0x27, b[3]); /* 100.00 */
}

static void test_the_generated_interface_matches_the_hub_and_converter(void)
{
    TEST_ASSERT_EQUAL_HEX16(0xFC11, MC_CLUSTER_ID);
    TEST_ASSERT_EQUAL_HEX16(0x0100, MC_INTERFACE_VERSION);
    TEST_ASSERT_EQUAL_HEX16(0x0110, MC_ATTR_SLOT_0);
    TEST_ASSERT_EQUAL_HEX16(0x0015, MC_ATTR_SLOT_CFG_5);
    TEST_ASSERT_EQUAL_INT(0, MC_CMD_IN_COMMIT_CONFIG);
    TEST_ASSERT_EQUAL_INT(1, MC_CMD_IN_PUMP_RUN);
    TEST_ASSERT_EQUAL_INT(0, MC_CMD_OUT_CMD_ACK);
    TEST_ASSERT_EQUAL_INT(1, MC_CMD_OUT_EVENT);
    TEST_ASSERT_EQUAL_INT(3, MC_DEVICE_ACTION_CLEAR_SAFE_MODE);
    TEST_ASSERT_EQUAL_INT(2, MC_ACK_STATE_FAILED);
    TEST_ASSERT_EQUAL_INT(4, MC_REASON_MIN_PAUSE);
    TEST_ASSERT_EQUAL_INT(300, MC_CFG_REPORT_INTERVAL_S_DEFAULT);
    TEST_ASSERT_EQUAL_INT(30, MC_CFG_FAST_REPORT_INTERVAL_S_DEFAULT);
}

void run_basics_tests(void)
{
    RUN_TEST(test_moisture_two_point_calibration);
    RUN_TEST(test_moisture_polarity_follows_the_points);
    RUN_TEST(test_moisture_clamps_inside_the_tolerance_and_flags_outside);
    RUN_TEST(test_moisture_adc_limits_are_no_signal);
    RUN_TEST(test_slot_cfg_bytes_as_the_converter_sends_them);
    RUN_TEST(test_slot_cfg_truncated_values_are_refused);
    RUN_TEST(test_the_encoder_of_the_sim_matches_the_converter);
    RUN_TEST(test_default_and_demo_configurations_are_valid);
    RUN_TEST(test_validation_ports_roles_and_conflicts);
    RUN_TEST(test_validation_ranges);
    RUN_TEST(test_cfg_error_wire_format);
    RUN_TEST(test_config_same_ignores_the_revision);
    RUN_TEST(test_board_table);
    RUN_TEST(test_crc32_and_crc16_known_values);
    RUN_TEST(test_factory_data_round_trip);
    RUN_TEST(test_factory_data_without_install_code_for_development);
    RUN_TEST(test_invalid_factory_data);
    RUN_TEST(test_slot_reading_bytes_as_the_converter_reads_them);
    RUN_TEST(test_the_generated_interface_matches_the_hub_and_converter);
}
