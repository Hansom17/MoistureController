"""Gateway ↔ API server payloads, contracts/gateway_api.md."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import device as d
from .device import Action


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --- §3 enrollment (HTTPS) ---------------------------------------------------------


class EnrollStartRequest(_Msg):
    secret_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    version: str
    arch: str
    adapters: list[str] = Field(default_factory=list)


class EnrollStartResponse(_Msg):
    enroll_id: str
    user_code: str
    expires_in: int
    interval: int
    claim_url: str


class EnrollPollRequest(_Msg):
    enroll_id: str
    secret: str


class EnrollPollResponse(_Msg):
    gateway_id: str
    household_name: str
    credential: str
    ws_url: str


# --- §4 session control ---------------------------------------------------------------


class Hello(_Msg):
    t: Literal["hello"] = "hello"
    version: str
    adapters: list[str] = Field(default_factory=list)
    snapshot_rev: int = 0
    keys_rev: int = 0
    last_down_id: str | None = None
    outbox_depth: int = 0
    lan_host: str | None = None
    time_synced: bool = True


class Welcome(_Msg):
    t: Literal["welcome"] = "welcome"
    ack_seq: int
    server_time: int


class Ack(_Msg):
    t: Literal["ack"] = "ack"
    seq: int


class DownAck(_Msg):
    t: Literal["down_ack"] = "down_ack"
    id: str
    result: Literal["applied", "rejected"]
    error: str | None = None


# --- §5 up messages -------------------------------------------------------------------

DeviceKind = Literal["status", "telemetry", "event", "cmd_ack", "config_state"]

# Payload model per `kind` — the mqtt.md shapes are the canonical device model.
DEVICE_PAYLOADS: dict[str, type[BaseModel]] = {
    "status": d.Status,
    "telemetry": d.Telemetry,
    "event": d.Event,
    "cmd_ack": d.CmdAck,
    "config_state": d.ConfigState,
}


class DeviceMessage(_Msg):
    t: Literal["device"] = "device"
    seq: int = Field(ge=1)
    device: str
    adapter: str
    kind: DeviceKind
    received_at: int
    payload: dict

    def parsed(self) -> BaseModel:
        """The payload validated with its mqtt.md model."""
        return DEVICE_PAYLOADS[self.kind].model_validate(self.payload)


class CommandCreated(_Msg):
    t: Literal["command_created"] = "command_created"
    seq: int = Field(ge=1)
    id: str
    device: str
    action: Action
    args: dict = Field(default_factory=dict)
    exp: int
    source: Literal["rule", "local"]
    rule_id: str | None = None
    created_at: int


class ReadingRef(_Msg):
    device: str
    slot: int
    seq: int
    value: float | None = None


SkipReason = Literal[
    "sensor_error", "no_pump", "quiet_hours", "cooldown", "daily_limit", "pending_command",
    "clock_not_synced",
]


class RuleExec(_Msg):
    t: Literal["rule_exec"] = "rule_exec"
    seq: int = Field(ge=1)
    id: str
    rule_id: str
    plant_id: str
    ts: int
    reading: ReadingRef
    decision: Literal["water", "skip"]
    skip_reason: SkipReason | None = None
    command_id: str | None = None


class GatewayState(_Msg):
    t: Literal["gateway_state"] = "gateway_state"
    seq: int = Field(ge=1)
    version: str
    arch: str
    uptime_s: int
    adapters: dict = Field(default_factory=dict)
    snapshot_rev: int
    keys_rev: int
    lan_host: str | None = None
    lan_port: int = 8883
    outbox_depth: int = 0
    outbox_oldest_s: int = 0
    disk_free_mb: int | None = None
    time_synced: bool


class GatewayEvent(_Msg):
    t: Literal["gateway_event"] = "gateway_event"
    seq: int = Field(ge=1)
    kind: Literal["buffer_overflow", "adapter_error", "clock_jump", "restarted"]
    detail: str | None = None
    ts: int


# --- §6 down messages -----------------------------------------------------------------


class SnapshotActuator(_Msg):
    slot: int
    max_run_s: int
    min_pause_s: int = 0


class SnapshotDevice(_Msg):
    id: str
    adapter: str = "esp32-mqtt"
    wake_interval_s: int
    actuators: list[SnapshotActuator] = Field(default_factory=list)
    limits: dict | None = None

    @property
    def max_run_s_hard(self) -> int | None:
        return (self.limits or {}).get("max_run_s_hard")


class SlotRef(_Msg):
    device: str
    slot: int


class SnapshotPlant(_Msg):
    id: str
    sensor: SlotRef | None = None
    pump: SlotRef | None = None


class SnapshotRule(_Msg):
    id: str
    plant_id: str
    enabled: bool
    threshold: float
    water_s: int
    cooldown_s: int
    max_per_day: int
    quiet_from: str | None = None
    quiet_to: str | None = None


class RuleState(_Msg):
    plant_id: str
    last_rule_cmd_at: int | None = None
    rule_cmds_today: int = 0


class Snapshot(_Msg):
    t: Literal["snapshot"] = "snapshot"
    id: str | None = None
    rev: int
    household_id: str
    timezone: str
    settings: dict = Field(default_factory=dict)
    devices: list[SnapshotDevice] = Field(default_factory=list)
    plants: list[SnapshotPlant] = Field(default_factory=list)
    rules: list[SnapshotRule] = Field(default_factory=list)
    rule_state: list[RuleState] = Field(default_factory=list)
    latest_gateway_version: str | None = None


class DeviceKey(_Msg):
    id: str
    adapter: str = "esp32-mqtt"
    psk: str


class Keys(_Msg):
    t: Literal["keys"] = "keys"
    id: str | None = None
    rev: int
    devices: list[DeviceKey] = Field(default_factory=list)


class CommandDown(_Msg):
    t: Literal["command"] = "command"
    id: str
    device: str
    command: d.Command


class ConfigDesiredDown(_Msg):
    t: Literal["config_desired"] = "config_desired"
    id: str
    device: str
    config: d.ConfigDesired


class DeviceRemoved(_Msg):
    t: Literal["device_removed"] = "device_removed"
    id: str
    device: str


class RotateCredential(_Msg):
    t: Literal["rotate_credential"] = "rotate_credential"
    id: str
    credential: str


class Removed(_Msg):
    t: Literal["removed"] = "removed"
    id: str


# Message type (`t`) → model, for both directions.
MESSAGES: dict[str, type[BaseModel]] = {
    m.model_fields["t"].default: m
    for m in (Hello, Welcome, Ack, DownAck, DeviceMessage, CommandCreated, RuleExec,
              GatewayState, GatewayEvent, Snapshot, Keys, CommandDown, ConfigDesiredDown,
              DeviceRemoved, RotateCredential, Removed)
}
