"""Device ↔ backend payloads, contracts/mqtt.md.

Receivers ignore unknown fields (§9); unknown enum values fail validation for
that message only.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --- §8 enumerations -------------------------------------------------------

Module = Literal[
    "moisture_capacitive",
    "moisture_resistive",
    "pump_relay",
    "ds18b20",
    "sht3x",
    "water_level_float",
]
ReadingType = Literal["soil_moisture", "temperature", "air_humidity", "water_level_ok"]
SensorError = Literal["no_signal", "out_of_range", "bus_error", "not_found"]
CommandReason = Literal[
    "expired",
    "no_time",
    "invalid_args",
    "unknown_action",
    "slot_not_actuator",
    "safety_limit",
    "busy",
    "already_done",
    "hw_error",
]
ConfigErrorCode = Literal[
    "pin_reserved", "pin_not_output", "pin_conflict", "unknown_module", "out_of_range"
]
Action = Literal[
    "pump.run", "pump.stop", "cmd.cancel", "device.identify", "device.service", "device.reboot"
]


# --- §4 device → server ----------------------------------------------------


class Status(_Msg):
    state: Literal["online", "sleeping", "offline", "service"]
    fw: str | None = None
    boot: int | None = None
    next_wake_s: int | None = None
    until_s: int | None = None


class Reading(_Msg):
    slot: int = Field(ge=0)
    type: ReadingType
    value: float | None = None
    unit: str | None = None
    raw: int | None = None
    error: SensorError | None = None


class Health(_Msg):
    batt_mv: int
    rssi: int
    wake: Literal["timer", "pump_stop", "button", "power_on", "reset"]
    cycle_ms: int | None = None
    wifi_ms: int | None = None


class Telemetry(_Msg):
    seq: int = Field(ge=0)
    ts: int | None = None
    cfg_rev: int
    readings: list[Reading]
    health: Health


class Event(_Msg):
    seq: int = Field(ge=0)
    ts: int | None = None
    kind: Literal[
        "boot", "safety_stop", "sensor_fault", "low_battery", "config_error", "service_mode"
    ]
    slot: int | None = None
    detail: str | None = None


# --- §5 commands -------------------------------------------------------------


class Command(_Msg):
    id: str = Field(max_length=26)
    action: Action
    exp: int
    args: dict = Field(default_factory=dict)


class CmdAck(_Msg):
    id: str = Field(max_length=26)
    status: Literal["running", "done", "rejected", "failed", "cancelled"]
    ts: int | None = None
    ends_at: int | None = None
    reason: CommandReason | None = None

    @property
    def is_final(self) -> bool:
        return self.status != "running"


# --- §6 configuration --------------------------------------------------------


class SlotConfig(BaseModel):
    """One slot. Module-specific options (e.g. `active_high`) are kept."""

    model_config = ConfigDict(extra="allow")

    slot: int = Field(ge=0)
    module: Module
    pin: int | None = None
    addr: int | None = None
    cal: dict | None = None
    active_high: bool | None = None
    max_run_s: int | None = None
    min_pause_s: int | None = None

    @property
    def is_actuator(self) -> bool:
        return self.module == "pump_relay"


class ConfigDesired(_Msg):
    rev: int = Field(ge=1)
    wake_interval_s: int = Field(ge=60, le=86400)
    slots: list[SlotConfig] = Field(default_factory=list)


class ConfigError(_Msg):
    slot: int | None = None
    code: ConfigErrorCode
    detail: str | None = None


class Detected(_Msg):
    bus: Literal["i2c", "onewire", "adc"]
    addr: int | None = None
    pin: int | None = None
    module: Module | None = None


class Limits(_Msg):
    max_run_s_hard: int
    slots_max: int


class ConfigState(_Msg):
    rev: int = Field(ge=0)
    result: Literal["applied", "rejected", "boot"]
    rejected_rev: int | None = None
    error: ConfigError | None = None
    wake_interval_s: int
    slots: list[SlotConfig] = Field(default_factory=list)
    detected: list[Detected] = Field(default_factory=list)
    limits: Limits | None = None


# Max payload sizes, §9.
MAX_DEVICE_TO_SERVER = 2048
MAX_SERVER_TO_DEVICE = 1024
