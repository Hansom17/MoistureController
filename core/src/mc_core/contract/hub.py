"""Hub ↔ cloud payloads, contracts/hub.md."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .device import Action


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --- §3 enrollment (HTTPS) ---------------------------------------------------


class EnrollStartRequest(_Msg):
    secret_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    agent_version: str
    arch: str


class EnrollStartResponse(_Msg):
    enroll_id: str
    user_code: str
    expires_in: int
    interval: int
    claim_url: str


class EnrollPollRequest(_Msg):
    enroll_id: str
    secret: str


class BridgeCredentials(_Msg):
    host: str
    port: int
    identity: str
    psk: str


class EnrollPollResponse(_Msg):
    hub_id: str
    household_name: str
    mqtt: BridgeCredentials


# --- §5 hub topics -------------------------------------------------------------


class SnapshotActuator(_Msg):
    slot: int
    max_run_s: int
    min_pause_s: int = 0


class SnapshotDevice(_Msg):
    id: str
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
    rev: int
    household_id: str
    timezone: str
    settings: dict = Field(default_factory=dict)
    devices: list[SnapshotDevice] = Field(default_factory=list)
    plants: list[SnapshotPlant] = Field(default_factory=list)
    rules: list[SnapshotRule] = Field(default_factory=list)
    rule_state: list[RuleState] = Field(default_factory=list)
    latest_agent_version: str | None = None


class DeviceKey(_Msg):
    id: str
    psk: str


class Keys(_Msg):
    rev: int
    devices: list[DeviceKey] = Field(default_factory=list)


class HubState(_Msg):
    agent_version: str
    arch: str
    uptime_s: int
    snapshot_rev: int
    keys_rev: int
    lan_host: str | None = None
    lan_port: int = 8883
    queue_depth: int = 0
    disk_free_mb: int | None = None
    time_synced: bool


class ReadingRef(_Msg):
    device: str
    slot: int
    seq: int
    value: float | None = None


SkipReason = Literal[
    "sensor_error", "no_pump", "quiet_hours", "cooldown", "daily_limit", "pending_command"
]


class RuleExec(_Msg):
    id: str
    rule_id: str
    plant_id: str
    ts: int
    reading: ReadingRef
    decision: Literal["water", "skip"]
    skip_reason: SkipReason | None = None
    command_id: str | None = None


class HubCmd(_Msg):
    id: str
    device: str
    action: Action
    args: dict = Field(default_factory=dict)
    exp: int
    source: Literal["rule", "local"]
    rule_id: str | None = None
    created_at: int


class HubAck(_Msg):
    topic: Literal["down/snapshot", "down/keys"]
    rev: int
    result: Literal["applied", "rejected"]
    error: str | None = None
