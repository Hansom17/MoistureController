"""Request/response models — the source of contracts/api.yaml (§6.3)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RoleName = Literal["viewer", "member", "admin", "owner"]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- me -------------------------------------------------------------------------------


class MeOut(Out):
    uid: str
    email: str | None
    display_name: str | None
    email_verified: bool


class HubSummary(Out):
    online: bool
    offline_since: datetime | None


class HouseholdOut(Out):
    id: str
    name: str
    timezone: str
    battery_low_mv: int
    role: RoleName
    hub: HubSummary | None = None


class TicketOut(Out):
    ticket: str
    expires_in: int


class PushTokenIn(BaseModel):
    platform: Literal["android", "ios", "web"] | None = None


# --- households, members, invites ------------------------------------------------------


class HouseholdCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = "Europe/Berlin"


class HouseholdPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    timezone: str | None = None
    battery_low_mv: int | None = Field(None, ge=2800, le=4200)


class MemberOut(Out):
    uid: str
    display_name: str | None
    email: str | None
    role: RoleName
    joined_at: datetime


class MemberPatch(BaseModel):
    role: RoleName


class TransferIn(BaseModel):
    uid: str


class InviteCreate(BaseModel):
    role: Literal["admin", "member", "viewer"] = "member"
    expires_in_h: int = 72


class InviteOut(Out):
    id: str
    role: RoleName
    created_at: datetime
    expires_at: datetime


class InviteCreated(InviteOut):
    code: str
    url: str


class InvitePreview(Out):
    household_name: str
    role: RoleName
    invited_by: str | None
    expires_at: datetime


class AuditOut(Out):
    id: str
    actor: str | None
    action: str
    detail: dict | None
    ts: datetime


# --- devices -------------------------------------------------------------------------------


class DeviceOut(Out):
    id: str
    name: str
    board: str
    status: Literal["new", "online", "sleeping", "late", "offline", "service"]
    gateway: Literal["cloud", "hub", "none"]
    fw: str | None
    batt_mv: int | None
    battery_percent: int | None
    rssi: int | None
    last_seen_at: datetime | None
    next_expected_at: datetime | None
    wake_interval_s: int
    sync_state: Literal["in_sync", "pending", "rejected"]
    desired_rev: int
    reported_rev: int
    config_error: dict | None
    created_at: datetime


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DevicePatch(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class MqttBundle(BaseModel):
    host: str
    port: int
    psk: str


class PairingBundle(BaseModel):
    """Returned once; sent to the device over BLE (§8.1)."""

    device_id: str
    mqtt: MqttBundle


class DeviceCreated(BaseModel):
    device: DeviceOut
    bundle: PairingBundle


class ConfigOut(BaseModel):
    device_id: str
    desired: dict | None
    desired_rev: int
    reported: dict | None
    reported_rev: int
    sync_state: Literal["in_sync", "pending", "rejected"]
    rejected_rev: int | None
    error: dict | None
    detected: list[dict]
    limits: dict
    board: str


class ConfigPut(BaseModel):
    base_rev: int
    wake_interval_s: int = Field(ge=60, le=86400)
    slots: list[dict]


class HealthOut(Out):
    ts: datetime
    batt_mv: int
    rssi: int
    wake: str
    cycle_ms: int | None
    wifi_ms: int | None


class DeviceEventOut(Out):
    ts: datetime
    kind: str
    slot: int | None
    detail: str | None


class DeviceActionIn(BaseModel):
    action: Literal["identify", "service", "reboot"]
    args: dict | None = None


# --- plants, readings, rules ------------------------------------------------------------------


class PlantOut(BaseModel):
    id: str
    name: str
    notes: str | None
    sensor_device_id: str | None
    sensor_slot: int | None
    pump_device_id: str | None
    pump_slot: int | None
    moisture: float | None
    moisture_error: str | None
    last_reading_at: datetime | None
    trend: Literal["falling", "steady", "rising"]
    max_run_s: int | None


class PlantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    notes: str | None = None
    sensor_device_id: str | None = None
    sensor_slot: int | None = Field(None, ge=0)
    pump_device_id: str | None = None
    pump_slot: int | None = Field(None, ge=0)


class PlantPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    notes: str | None = None
    sensor_device_id: str | None = None
    sensor_slot: int | None = Field(None, ge=0)
    pump_device_id: str | None = None
    pump_slot: int | None = Field(None, ge=0)


class ReadingOut(BaseModel):
    ts: datetime
    value: float | None
    error: str | None = None
    min: float | None = None
    max: float | None = None


class WaterIn(BaseModel):
    seconds: int = Field(ge=1, le=3600)


class CommandOut(BaseModel):
    id: str
    device_id: str
    plant_id: str | None
    action: str
    args: dict
    seconds: int | None
    status: Literal["queued", "delivered", "done", "failed", "expired", "cancelling", "cancelled"]
    state: Literal["queued", "delivered", "running", "done", "failed", "expired", "cancelling",
                   "cancelled"]
    reason: str | None
    source: Literal["manual", "rule", "local"]
    origin: Literal["cloud", "hub"]
    rule_id: str | None
    created_at: datetime
    exp: datetime
    delivered_at: datetime | None
    ends_at: datetime | None
    finished_at: datetime | None


class WaterOut(BaseModel):
    command: CommandOut
    warnings: list[str]


class RuleIn(BaseModel):
    enabled: bool = True
    threshold: float = Field(ge=0, le=100)
    water_s: int = Field(ge=1, le=3600)
    cooldown_s: int = Field(6 * 3600, ge=0, le=7 * 86400)
    max_per_day: int = Field(2, ge=1, le=48)
    quiet_from: str | None = None
    quiet_to: str | None = None


class RulePatch(BaseModel):
    enabled: bool | None = None
    threshold: float | None = Field(None, ge=0, le=100)
    water_s: int | None = Field(None, ge=1, le=3600)
    cooldown_s: int | None = Field(None, ge=0, le=7 * 86400)
    max_per_day: int | None = Field(None, ge=1, le=48)
    quiet_from: str | None = None
    quiet_to: str | None = None


class RuleOut(Out):
    id: str
    plant_id: str
    enabled: bool
    threshold: float
    water_s: int
    cooldown_s: int
    max_per_day: int
    quiet_from: str | None
    quiet_to: str | None
    updated_at: datetime


class RuleExecutionOut(Out):
    id: str
    rule_id: str
    ts: datetime
    reading_ref: dict | None
    decision: Literal["water", "skip"]
    skip_reason: str | None
    command_id: str | None
    origin: Literal["cloud", "hub"]


# --- alerts, hub ---------------------------------------------------------------------------------


class AlertOut(Out):
    id: str
    kind: str
    subject_type: str
    subject_id: str
    subject_name: str | None
    severity: str
    opened_at: datetime
    resolved_at: datetime | None
    acked_by: str | None
    acked_at: datetime | None
    detail: dict | None


class HubOut(BaseModel):
    id: str
    status: str
    online: bool
    offline_since: datetime | None
    agent_version: str | None
    latest_agent_version: str | None
    arch: str | None
    in_sync: bool
    snapshot_rev: int
    snapshot_rev_applied: int
    keys_rev: int
    keys_rev_applied: int
    queue_depth: int | None
    time_synced: bool | None
    lan_host: str | None
    lan_host_override: str | None
    last_state_at: datetime | None


class HubClaim(BaseModel):
    user_code: str = Field(min_length=8, max_length=12)


class HubPatch(BaseModel):
    lan_host_override: str | None = Field(None, max_length=255)
