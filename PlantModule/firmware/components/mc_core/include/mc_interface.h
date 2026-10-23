/* GENERATED from PlantModule/interface.yaml by PlantModule/scripts/gen_interface_h.py. Do not edit:
 * change the interface file and run the generator again (the host tests fail while they differ). */
#ifndef MC_INTERFACE_H
#define MC_INTERFACE_H

#define MC_MODEL "MC-PLANT"
#define MC_MANUFACTURER "MoistureController"
#define MC_ENDPOINT 1
#define MC_CLUSTER_ID 0xFC11
#define MC_MANUFACTURER_CODE 0x131B
#define MC_INTERFACE_VERSION 0x0100
#define MC_CONFIG_SCHEMA 2

/* attribute ids of the custom cluster */
#define MC_ATTR_SEQ 0x0100
#define MC_ATTR_BOOT_ID 0x0101
#define MC_ATTR_SLOT_0 0x0110
#define MC_ATTR_SLOT_1 0x0111
#define MC_ATTR_SLOT_2 0x0112
#define MC_ATTR_SLOT_3 0x0113
#define MC_ATTR_SLOT_4 0x0114
#define MC_ATTR_SLOT_5 0x0115
#define MC_ATTR_STATUS 0x0120
#define MC_ATTR_FAST_MODE 0x0121
#define MC_ATTR_SAFE_REASON 0x0122
#define MC_ATTR_UPTIME_S 0x0130
#define MC_ATTR_BOOT_REASON 0x0131
#define MC_ATTR_RESET_COUNT 0x0132
#define MC_ATTR_REJOIN_COUNT 0x0133
#define MC_ATTR_LAST_ERROR 0x0134
#define MC_ATTR_FREE_HEAP 0x0135
#define MC_ATTR_INTERFACE_VERSION 0x0136
#define MC_ATTR_CONFIG_SCHEMA 0x0137
#define MC_ATTR_BATT_MV 0x0138
#define MC_ATTR_BATT_STATE 0x0139
#define MC_ATTR_BOARD 0x0140
#define MC_ATTR_CFG_REV 0x0030
#define MC_ATTR_CFG_RESULT 0x0031
#define MC_ATTR_CFG_ERROR 0x0032
#define MC_ATTR_REPORT_INTERVAL_S 0x0001
#define MC_ATTR_FAST_REPORT_INTERVAL_S 0x0002
#define MC_ATTR_FAST_REPORT_HOLD_S 0x0003
#define MC_ATTR_BATT_LOW_MV 0x0004
#define MC_ATTR_BATT_CRITICAL_MV 0x0005
#define MC_ATTR_BATT_CAL_PERMILLE 0x0006
#define MC_ATTR_SLOT_CFG_0 0x0010
#define MC_ATTR_SLOT_CFG_1 0x0011
#define MC_ATTR_SLOT_CFG_2 0x0012
#define MC_ATTR_SLOT_CFG_3 0x0013
#define MC_ATTR_SLOT_CFG_4 0x0014
#define MC_ATTR_SLOT_CFG_5 0x0015

/* limits and defaults of the writable configuration attributes */
#define MC_CFG_REPORT_INTERVAL_S_MIN 10
#define MC_CFG_REPORT_INTERVAL_S_MAX 3600
#define MC_CFG_REPORT_INTERVAL_S_DEFAULT 300
#define MC_CFG_FAST_REPORT_INTERVAL_S_MIN 10
#define MC_CFG_FAST_REPORT_INTERVAL_S_MAX 300
#define MC_CFG_FAST_REPORT_INTERVAL_S_DEFAULT 30
#define MC_CFG_FAST_REPORT_HOLD_S_MIN 0
#define MC_CFG_FAST_REPORT_HOLD_S_MAX 1800
#define MC_CFG_FAST_REPORT_HOLD_S_DEFAULT 120
#define MC_CFG_BATT_LOW_MV_MIN 3000
#define MC_CFG_BATT_LOW_MV_MAX 4000
#define MC_CFG_BATT_LOW_MV_DEFAULT 3600
#define MC_CFG_BATT_CRITICAL_MV_MIN 3000
#define MC_CFG_BATT_CRITICAL_MV_MAX 4000
#define MC_CFG_BATT_CRITICAL_MV_DEFAULT 3400
#define MC_CFG_BATT_CAL_PERMILLE_MIN 900
#define MC_CFG_BATT_CAL_PERMILLE_MAX 1100
#define MC_CFG_BATT_CAL_PERMILLE_DEFAULT 1000

/* battery detection tunables (interface.yaml, section battery) */
#define MC_BATT_ADC_CONVERSIONS 8
#define MC_BATT_FILTER_SAMPLES 3
#define MC_BATT_QUIET_MS 5000u
#define MC_BATT_READ_TIMEOUT_MS 500u
#define MC_BATT_PRESENT_MV 500u
#define MC_BATT_HYSTERESIS_MV 100u
#define MC_BATT_DEBOUNCE 3

/* reporting the module sets up itself when its attribute set changed (the stack keeps the records of the old
 * set otherwise): X(attribute id, min s, max s, reportable change). Zigbee2MQTT configures the same values. */
#define MC_REPORTING_LIST(X) \
    X(0x0138, 60, 600, 20) \
    X(0x0120, 1, 600, 0) \
    X(0x0121, 1, 600, 0) \
    X(0x0122, 1, 600, 0) \
    X(0x0139, 1, 600, 0) \
    X(0x0030, 1, 600, 0) \
    X(0x0031, 1, 600, 0) \
    X(0x0032, 1, 600, 0) \
    X(0x0130, 10, 600, 0) \
    X(0x0131, 10, 600, 0) \
    X(0x0132, 10, 600, 0) \
    X(0x0133, 10, 600, 0) \
    X(0x0134, 10, 600, 0) \
    X(0x0135, 10, 600, 0)
#define MC_REPORTING_POWER_MIN_S 60
#define MC_REPORTING_POWER_MAX_S 600
#define MC_REPORTING_POWER_CHANGE 1 /* 100 mV steps, as Zigbee2MQTT configures it */

/* cluster commands, coordinator to module */
#define MC_CMD_IN_COMMIT_CONFIG 0x00
#define MC_CMD_IN_PUMP_RUN 0x01
#define MC_CMD_IN_PUMP_STOP 0x02
#define MC_CMD_IN_CANCEL 0x03
#define MC_CMD_IN_DEVICE_ACTION 0x04
#define MC_CMD_IN_SENSOR_SAMPLE 0x05

/* cluster commands, module to coordinator */
#define MC_CMD_OUT_CMD_ACK 0x00
#define MC_CMD_OUT_EVENT 0x01

/* enumerations (values as on the air) */
typedef enum {
    MC_MODULE_EMPTY = 0,
    MC_MODULE_MOISTURE = 1,
    MC_MODULE_PUMP = 2,
} mc_module_t;

typedef enum {
    MC_SENSOR_ERROR_OK = 0,
    MC_SENSOR_ERROR_NO_SIGNAL = 1,
    MC_SENSOR_ERROR_OUT_OF_RANGE = 2,
    MC_SENSOR_ERROR_NOT_FOUND = 3,
    MC_SENSOR_ERROR_HW_ERROR = 4,
} mc_sensor_error_t;

typedef enum {
    MC_STATUS_OPERATIONAL = 0,
    MC_STATUS_INTERVIEWING = 1,
    MC_STATUS_SAFE_MODE = 2,
} mc_status_t;

typedef enum {
    MC_SAFE_REASON_NONE = 0,
    MC_SAFE_REASON_FACTORY_INVALID = 1,
    MC_SAFE_REASON_BOARD_UNKNOWN = 2,
    MC_SAFE_REASON_CRASH_LOOP = 3,
} mc_safe_reason_t;

typedef enum {
    MC_BOOT_REASON_POWER_ON = 0,
    MC_BOOT_REASON_SOFTWARE = 1,
    MC_BOOT_REASON_PANIC = 2,
    MC_BOOT_REASON_WATCHDOG = 3,
    MC_BOOT_REASON_BROWNOUT = 4,
    MC_BOOT_REASON_OTHER = 5,
} mc_boot_reason_t;

typedef enum {
    MC_CFG_RESULT_OK = 0,
    MC_CFG_RESULT_REJECTED = 1,
} mc_cfg_result_t;

typedef enum {
    MC_ACK_STATE_RUNNING = 0,
    MC_ACK_STATE_DONE = 1,
    MC_ACK_STATE_FAILED = 2,
    MC_ACK_STATE_REJECTED = 3,
    MC_ACK_STATE_CANCELLED = 4,
} mc_ack_state_t;

typedef enum {
    MC_REASON_NONE = 0,
    MC_REASON_EXPIRED = 1,
    MC_REASON_BUSY = 2,
    MC_REASON_LIMIT = 3,
    MC_REASON_MIN_PAUSE = 4,
    MC_REASON_SLOT_NOT_ACTUATOR = 5,
    MC_REASON_SLOT_NOT_SENSOR = 6,
    MC_REASON_HW_ERROR = 7,
    MC_REASON_BATTERY_LOW = 8,
} mc_reason_t;

typedef enum {
    MC_DEVICE_ACTION_IDENTIFY = 1,
    MC_DEVICE_ACTION_REBOOT = 2,
    MC_DEVICE_ACTION_CLEAR_SAFE_MODE = 3,
    MC_DEVICE_ACTION_REPORT_NOW = 4,
} mc_device_action_t;

typedef enum {
    MC_EVENT_CODE_BOOT = 1,
    MC_EVENT_CODE_LOW_BATTERY = 2,
    MC_EVENT_CODE_SENSOR_FAULT = 3,
    MC_EVENT_CODE_SENSOR_OK = 4,
    MC_EVENT_CODE_SAFETY_STOP = 5,
    MC_EVENT_CODE_SAFE_MODE = 6,
    MC_EVENT_CODE_CONFIG_REJECTED = 7,
    MC_EVENT_CODE_BATTERY_CRITICAL = 8,
} mc_event_code_t;

typedef enum {
    MC_BATT_STATE_ABSENT = 0,
    MC_BATT_STATE_OK = 1,
    MC_BATT_STATE_LOW = 2,
    MC_BATT_STATE_CRITICAL = 3,
} mc_batt_state_t;

typedef enum {
    MC_CFG_ERROR_PORT_INVALID = 1,
    MC_CFG_ERROR_PORT_CONFLICT = 2,
    MC_CFG_ERROR_OUT_OF_RANGE = 3,
    MC_CFG_ERROR_BUSY = 4,
    MC_CFG_ERROR_STALE_REV = 5,
    MC_CFG_ERROR_SCHEMA_UNKNOWN = 6,
    MC_CFG_ERROR_ROLE_UNSUPPORTED = 7,
} mc_cfg_error_t;

#endif /* MC_INTERFACE_H */
