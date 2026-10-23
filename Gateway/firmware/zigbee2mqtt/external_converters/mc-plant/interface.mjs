// GENERATED from PlantModule/interface.yaml by Gateway/scripts/gen_converter.py. Do not edit:
// change the interface file and run the generator again (a test fails while they differ).
export default {
  "interfaceVersion": [
    1,
    1
  ],
  "configSchema": 3,
  "identity": {
    "manufacturer": "MoistureController",
    "model": "MC-PLANT",
    "endpoint": 1
  },
  "cluster": {
    "id": 64529,
    "manufacturerCode": 4891
  },
  "attributes": [
    {
      "id": 256,
      "name": "seq",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "seq",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 257,
      "name": "boot_id",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "boot_id",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 272,
      "name": "slot_0",
      "type": "octet8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "slot0",
      "layout": "slot_reading",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 273,
      "name": "slot_1",
      "type": "octet8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "slot1",
      "layout": "slot_reading",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 274,
      "name": "slot_2",
      "type": "octet8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "slot2",
      "layout": "slot_reading",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 275,
      "name": "slot_3",
      "type": "octet8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "slot3",
      "layout": "slot_reading",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 276,
      "name": "slot_4",
      "type": "octet8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "slot4",
      "layout": "slot_reading",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 277,
      "name": "slot_5",
      "type": "octet8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "slot5",
      "layout": "slot_reading",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 288,
      "name": "status",
      "type": "enum8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "status",
      "layout": null,
      "enum": "status",
      "range": null,
      "default": null
    },
    {
      "id": 289,
      "name": "fast_mode",
      "type": "uint8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "fast_mode",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 290,
      "name": "safe_reason",
      "type": "enum8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "safe_reason",
      "layout": null,
      "enum": "safe_reason",
      "range": null,
      "default": null
    },
    {
      "id": 304,
      "name": "uptime_s",
      "type": "uint32",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "uptime_s",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 305,
      "name": "boot_reason",
      "type": "enum8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "boot_reason",
      "layout": null,
      "enum": "boot_reason",
      "range": null,
      "default": null
    },
    {
      "id": 306,
      "name": "reset_count",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "reset_count",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 307,
      "name": "rejoin_count",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "rejoin_count",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 308,
      "name": "last_error",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "last_error",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 309,
      "name": "free_heap",
      "type": "uint32",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "free_heap",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 310,
      "name": "interface_version",
      "type": "uint16",
      "access": [
        "r"
      ],
      "mqtt": "interface",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 311,
      "name": "config_schema",
      "type": "uint8",
      "access": [
        "r"
      ],
      "mqtt": "config_schema",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 312,
      "name": "batt_mv",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "batt_mv",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 313,
      "name": "batt_state",
      "type": "enum8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "batt_state",
      "layout": null,
      "enum": "batt_state",
      "range": null,
      "default": null
    },
    {
      "id": 320,
      "name": "board",
      "type": "char16",
      "access": [
        "r"
      ],
      "mqtt": "board",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 321,
      "name": "wake_reason",
      "type": "enum8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "wake_reason",
      "layout": null,
      "enum": "wake_reason",
      "range": null,
      "default": null
    },
    {
      "id": 322,
      "name": "awake_ms",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "awake_ms",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 323,
      "name": "poll_fail_count",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "poll_fail_count",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 324,
      "name": "next_wake_s",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "next_wake_s",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 48,
      "name": "cfg_rev",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "cfg_rev",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 49,
      "name": "cfg_result",
      "type": "enum8",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "cfg_result",
      "layout": null,
      "enum": "cfg_result",
      "range": null,
      "default": null
    },
    {
      "id": 50,
      "name": "cfg_error",
      "type": "uint16",
      "access": [
        "r",
        "report"
      ],
      "mqtt": "cfg_error",
      "layout": null,
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 1,
      "name": "report_interval_s",
      "type": "uint16",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": null,
      "enum": null,
      "range": [
        10,
        3600
      ],
      "default": 300
    },
    {
      "id": 2,
      "name": "fast_report_interval_s",
      "type": "uint16",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": null,
      "enum": null,
      "range": [
        10,
        300
      ],
      "default": 30
    },
    {
      "id": 3,
      "name": "fast_report_hold_s",
      "type": "uint16",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": null,
      "enum": null,
      "range": [
        0,
        1800
      ],
      "default": 120
    },
    {
      "id": 4,
      "name": "batt_low_mv",
      "type": "uint16",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": null,
      "enum": null,
      "range": [
        3000,
        4000
      ],
      "default": 3600
    },
    {
      "id": 5,
      "name": "batt_critical_mv",
      "type": "uint16",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": null,
      "enum": null,
      "range": [
        3000,
        4000
      ],
      "default": 3400
    },
    {
      "id": 6,
      "name": "batt_cal_permille",
      "type": "uint16",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": null,
      "enum": null,
      "range": [
        900,
        1100
      ],
      "default": 1000
    },
    {
      "id": 7,
      "name": "power_mode",
      "type": "enum8",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": null,
      "enum": "power_mode",
      "range": [
        0,
        2
      ],
      "default": 0
    },
    {
      "id": 8,
      "name": "poll_interval_ms",
      "type": "uint16",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": null,
      "enum": null,
      "range": [
        500,
        5000
      ],
      "default": 3000
    },
    {
      "id": 9,
      "name": "awake_s",
      "type": "uint8",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": null,
      "enum": null,
      "range": [
        2,
        30
      ],
      "default": 5
    },
    {
      "id": 16,
      "name": "slot_cfg_0",
      "type": "octet24",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": "slot_config",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 17,
      "name": "slot_cfg_1",
      "type": "octet24",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": "slot_config",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 18,
      "name": "slot_cfg_2",
      "type": "octet24",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": "slot_config",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 19,
      "name": "slot_cfg_3",
      "type": "octet24",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": "slot_config",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 20,
      "name": "slot_cfg_4",
      "type": "octet24",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": "slot_config",
      "enum": null,
      "range": null,
      "default": null
    },
    {
      "id": 21,
      "name": "slot_cfg_5",
      "type": "octet24",
      "access": [
        "rw"
      ],
      "mqtt": null,
      "layout": "slot_config",
      "enum": null,
      "range": null,
      "default": null
    }
  ],
  "commandsIn": [
    {
      "id": 0,
      "name": "commitConfig",
      "interfaceName": "commit_config",
      "fields": [
        {
          "name": "rev",
          "type": "uint16"
        }
      ],
      "mqtt": "config"
    },
    {
      "id": 1,
      "name": "pumpRun",
      "interfaceName": "pump_run",
      "fields": [
        {
          "name": "cmd_id",
          "type": "uint32"
        },
        {
          "name": "slot",
          "type": "uint8"
        },
        {
          "name": "seconds",
          "type": "uint16"
        },
        {
          "name": "ttl_s",
          "type": "uint16"
        }
      ],
      "mqtt": "pump_run"
    },
    {
      "id": 2,
      "name": "pumpStop",
      "interfaceName": "pump_stop",
      "fields": [
        {
          "name": "cmd_id",
          "type": "uint32"
        },
        {
          "name": "slot",
          "type": "uint8"
        }
      ],
      "mqtt": "pump_stop"
    },
    {
      "id": 3,
      "name": "cancel",
      "interfaceName": "cancel",
      "fields": [
        {
          "name": "cmd_id",
          "type": "uint32"
        },
        {
          "name": "target",
          "type": "uint32"
        }
      ],
      "mqtt": "cancel"
    },
    {
      "id": 4,
      "name": "deviceAction",
      "interfaceName": "device_action",
      "fields": [
        {
          "name": "cmd_id",
          "type": "uint32"
        },
        {
          "name": "action",
          "type": "enum8",
          "enum": "device_action"
        },
        {
          "name": "arg",
          "type": "uint16"
        }
      ],
      "mqtt": "device_action"
    }
  ],
  "commandsOut": [
    {
      "id": 0,
      "name": "cmdAck",
      "interfaceName": "cmd_ack",
      "fields": [
        {
          "name": "n",
          "type": "uint16",
          "note": "module counter, to tell a repeated publication from a new ack"
        },
        {
          "name": "cmd_id",
          "type": "uint32"
        },
        {
          "name": "state",
          "type": "enum8",
          "enum": "ack_state"
        },
        {
          "name": "reason",
          "type": "enum8",
          "enum": "reason"
        },
        {
          "name": "ends_in_s",
          "type": "uint16"
        }
      ],
      "mqtt": "cmd_ack"
    },
    {
      "id": 1,
      "name": "event",
      "interfaceName": "event",
      "fields": [
        {
          "name": "n",
          "type": "uint16"
        },
        {
          "name": "code",
          "type": "enum8",
          "enum": "event_code"
        },
        {
          "name": "slot",
          "type": "uint8"
        },
        {
          "name": "arg",
          "type": "uint16"
        }
      ],
      "mqtt": "event"
    }
  ],
  "enums": {
    "module": {
      "0": "empty",
      "1": "moisture",
      "2": "pump"
    },
    "sensor_error": {
      "0": "ok",
      "1": "no_signal",
      "2": "out_of_range",
      "3": "not_found",
      "4": "hw_error"
    },
    "status": {
      "0": "operational",
      "1": "interviewing",
      "2": "safe_mode"
    },
    "safe_reason": {
      "0": "none",
      "1": "factory_invalid",
      "2": "board_unknown",
      "3": "crash_loop"
    },
    "boot_reason": {
      "0": "power_on",
      "1": "software",
      "2": "panic",
      "3": "watchdog",
      "4": "brownout",
      "5": "other",
      "6": "deep_sleep_wake"
    },
    "power_mode": {
      "0": "always_on",
      "1": "light_sleep",
      "2": "deep_sleep"
    },
    "wake_reason": {
      "0": "none",
      "1": "timer",
      "2": "button",
      "3": "pump_end",
      "4": "radio"
    },
    "cfg_result": {
      "0": "ok",
      "1": "rejected"
    },
    "ack_state": {
      "0": "running",
      "1": "done",
      "2": "failed",
      "3": "rejected",
      "4": "cancelled"
    },
    "reason": {
      "0": "none",
      "1": "expired",
      "2": "busy",
      "3": "limit",
      "4": "min_pause",
      "5": "slot_not_actuator",
      "6": "slot_not_sensor",
      "7": "hw_error",
      "8": "battery_low"
    },
    "device_action": {
      "1": "identify",
      "2": "reboot",
      "3": "clear_safe_mode",
      "4": "report_now"
    },
    "event_code": {
      "1": "boot",
      "2": "low_battery",
      "3": "sensor_fault",
      "4": "sensor_ok",
      "5": "safety_stop",
      "6": "safe_mode",
      "7": "config_rejected",
      "8": "battery_critical"
    },
    "batt_state": {
      "0": "absent",
      "1": "ok",
      "2": "low",
      "3": "critical"
    },
    "cfg_error": {
      "1": "port_invalid",
      "2": "port_conflict",
      "3": "out_of_range",
      "4": "busy",
      "5": "stale_rev",
      "6": "schema_unknown",
      "7": "role_unsupported"
    }
  },
  "reporting": [
    {
      "attributes": [
        "power_config.batteryVoltage"
      ],
      "min_s": 60,
      "max_s": 600,
      "change": "50 mV"
    },
    {
      "attributes": [
        "batt_mv"
      ],
      "min_s": 60,
      "max_s": 600,
      "change": "20 mV",
      "change_value": 20
    },
    {
      "attributes": [
        "status",
        "fast_mode",
        "safe_reason",
        "batt_state",
        "cfg_rev",
        "cfg_result",
        "cfg_error"
      ],
      "min_s": 1,
      "max_s": 600,
      "change": "any"
    },
    {
      "attributes": [
        "uptime_s",
        "boot_reason",
        "reset_count",
        "rejoin_count",
        "last_error",
        "free_heap"
      ],
      "min_s": 10,
      "max_s": 600,
      "change": "any"
    },
    {
      "attributes": [
        "wake_reason",
        "awake_ms",
        "poll_fail_count",
        "next_wake_s"
      ],
      "min_s": 10,
      "max_s": 600,
      "change": "any"
    }
  ]
};
