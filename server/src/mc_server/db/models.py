"""Database schema (Api_Specs §4). Every household table has `household_id`."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from mc_core.ids import new_id

from .types import BigIntPK, UTCDateTime, utcnow

ROLES = ("viewer", "member", "admin", "owner")


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTCDateTime, dict: JSON, list: JSON}


def _id() -> Mapped[str]:
    return mapped_column(String(26), primary_key=True, default=new_id)


def _created() -> Mapped[datetime]:
    return mapped_column(default=utcnow)


class User(Base):
    __tablename__ = "users"
    uid: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(200))
    first_seen_at: Mapped[datetime] = _created()


class Household(Base):
    __tablename__ = "households"
    id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Berlin")
    battery_low_mv: Mapped[int] = mapped_column(Integer, default=3500)
    snapshot_rev: Mapped[int] = mapped_column(Integer, default=0)
    keys_rev: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class Membership(Base):
    __tablename__ = "memberships"
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), primary_key=True)
    user_uid: Mapped[str] = mapped_column(
        ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        # Exactly one owner per household.
        Index("uq_one_owner", "household_id", unique=True,
              postgresql_where=text("role = 'owner'"), sqlite_where=text("role = 'owner'")),
        Index("ix_memberships_user", "user_uid"),
    )


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[str] = _id()
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(10))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime]
    used_by: Mapped[str | None] = mapped_column(String(128))
    used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class Gateway(Base):
    """One per household (Api_Specs §4, D30)."""

    __tablename__ = "gateways"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), unique=True)
    credential_hash: Mapped[str] = mapped_column(String(64))
    # enrolling (claimed, credential not fetched) | online | offline | removed
    status: Mapped[str] = mapped_column(String(10), default="enrolling")
    connected_at: Mapped[datetime | None]
    disconnected_at: Mapped[datetime | None]
    last_outage_s: Mapped[int] = mapped_column(Integer, default=0)
    last_state: Mapped[dict | None]
    last_state_at: Mapped[datetime | None]
    lan_host_override: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str | None] = mapped_column(String(32))
    adapters: Mapped[list | None]
    snapshot_rev_applied: Mapped[int] = mapped_column(Integer, default=0)
    keys_rev_applied: Mapped[int] = mapped_column(Integer, default=0)
    last_up_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class GatewayEnrollment(Base):
    __tablename__ = "gateway_enrollments"
    id: Mapped[str] = _id()
    secret_sha256: Mapped[str] = mapped_column(String(64))
    user_code_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime]
    claimed_household_id: Mapped[str | None] = mapped_column(String(26))
    claimed_by: Mapped[str | None] = mapped_column(String(128))
    gateway_id: Mapped[str | None] = mapped_column(String(24))
    credential_enc: Mapped[str | None] = mapped_column(Text)  # until fetched once
    consumed_at: Mapped[datetime | None]
    last_poll_at: Mapped[datetime | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[str | None] = mapped_column(String(32))
    arch: Mapped[str | None] = mapped_column(String(16))
    adapters: Mapped[list | None]
    created_at: Mapped[datetime] = _created()


class Downlink(Base):
    """Messages for a gateway, written in the change's transaction (Api_Specs §9.3)."""

    __tablename__ = "downlink"
    id: Mapped[str] = _id()  # = message `id`
    gateway_id: Mapped[str] = mapped_column(
        ForeignKey("gateways.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    body: Mapped[dict]
    created_at: Mapped[datetime] = _created()
    sent_at: Mapped[datetime | None]
    acked_at: Mapped[datetime | None] = mapped_column(index=True)
    result: Mapped[str | None] = mapped_column(String(12))  # applied | rejected | superseded
    error: Mapped[str | None] = mapped_column(String(200))


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    psk_enc: Mapped[str | None] = mapped_column(Text)
    # gateway = key installed on the household's gateway; none = needs re-pairing
    gateway: Mapped[str] = mapped_column(String(8), default="gateway")
    adapter: Mapped[str] = mapped_column(String(16), default="esp32-mqtt")
    hw_mac: Mapped[str | None] = mapped_column(String(17))
    fw: Mapped[str | None] = mapped_column(String(32))
    board: Mapped[str] = mapped_column(String(64), default="doit_esp32_devkit_v1")
    status: Mapped[str] = mapped_column(String(10), default="new")
    last_seen_at: Mapped[datetime | None]
    next_expected_at: Mapped[datetime | None]
    wake_interval_s: Mapped[int] = mapped_column(Integer, default=600)
    batt_mv: Mapped[int | None] = mapped_column(Integer)
    rssi: Mapped[int | None] = mapped_column(Integer)
    last_seq: Mapped[int | None] = mapped_column(Integer)
    last_boot: Mapped[int | None] = mapped_column(Integer)
    desired_rev: Mapped[int] = mapped_column(Integer, default=0)
    desired_config: Mapped[dict | None]
    reported_rev: Mapped[int] = mapped_column(Integer, default=0)
    reported_config: Mapped[dict | None]
    rejected_rev: Mapped[int | None] = mapped_column(Integer)
    config_error: Mapped[dict | None]
    sensor_error_streak: Mapped[dict | None]
    created_at: Mapped[datetime] = _created()
    deleted_at: Mapped[datetime | None]


class ConfigRevision(Base):
    __tablename__ = "config_revisions"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    rev: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10))  # desired | reported
    body: Mapped[dict]
    result: Mapped[str | None] = mapped_column(String(10))
    error: Mapped[dict | None]
    created_at: Mapped[datetime] = _created()
    created_by: Mapped[str | None] = mapped_column(String(128))


class Plant(Base):
    __tablename__ = "plants"
    id: Mapped[str] = _id()
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    sensor_device_id: Mapped[str | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"))
    sensor_slot: Mapped[int | None] = mapped_column(Integer)
    pump_device_id: Mapped[str | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"))
    pump_slot: Mapped[int | None] = mapped_column(Integer)
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created()


class ReadingRow(Base):
    __tablename__ = "readings"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    slot: Mapped[int] = mapped_column(Integer)
    plant_id: Mapped[str | None] = mapped_column(String(26))
    type: Mapped[str] = mapped_column(String(20))
    value: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(20))
    ts: Mapped[datetime]
    ts_source: Mapped[str] = mapped_column(String(8))  # device | gateway
    seq: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_readings_plant_ts", "plant_id", "ts"),
        Index("ix_readings_device_slot_ts", "device_id", "slot", "ts"),
    )


class HealthReport(Base):
    __tablename__ = "health_reports"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    ts: Mapped[datetime]
    seq: Mapped[int] = mapped_column(Integer)
    batt_mv: Mapped[int] = mapped_column(Integer)
    rssi: Mapped[int] = mapped_column(Integer)
    wake: Mapped[str] = mapped_column(String(12))
    cycle_ms: Mapped[int | None] = mapped_column(Integer)
    wifi_ms: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_health_device_ts", "device_id", "ts"),)


class DeviceEvent(Base):
    __tablename__ = "device_events"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    ts: Mapped[datetime]
    seq: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    slot: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_events_device_ts", "device_id", "ts"),)


class CommandRow(Base):
    __tablename__ = "commands"
    id: Mapped[str] = _id()
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    plant_id: Mapped[str | None] = mapped_column(String(26))
    action: Mapped[str] = mapped_column(String(20))
    args: Mapped[dict] = mapped_column(default=dict)
    # queued | delivered | done | failed | expired | cancelling | cancelled
    status: Mapped[str] = mapped_column(String(10), default="queued")
    reason: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(8))  # manual | rule | local
    origin: Mapped[str] = mapped_column(String(8), default="api")  # api | gateway
    created_by: Mapped[str | None] = mapped_column(String(128))
    rule_id: Mapped[str | None] = mapped_column(String(26))
    created_at: Mapped[datetime] = _created()
    exp: Mapped[datetime]
    sent_at: Mapped[datetime | None]  # handed to the gateway (down_ack applied)
    delivered_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    ends_at: Mapped[datetime | None]
    cancel_of: Mapped[str | None] = mapped_column(String(26))

    __table_args__ = (Index("ix_commands_device_status", "device_id", "status"),)


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[str] = _id()
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    threshold: Mapped[float] = mapped_column(Float)
    water_s: Mapped[int] = mapped_column(Integer)
    cooldown_s: Mapped[int] = mapped_column(Integer, default=6 * 3600)
    max_per_day: Mapped[int] = mapped_column(Integer, default=2)
    quiet_from: Mapped[str | None] = mapped_column(String(5))
    quiet_to: Mapped[str | None] = mapped_column(String(5))
    created_by: Mapped[str | None] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class RuleExecution(Base):
    __tablename__ = "rule_executions"
    id: Mapped[str] = _id()
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(String(26), index=True)
    plant_id: Mapped[str] = mapped_column(String(26))
    ts: Mapped[datetime]
    reading_ref: Mapped[dict | None]
    decision: Mapped[str] = mapped_column(String(5))
    skip_reason: Mapped[str | None] = mapped_column(String(20))
    command_id: Mapped[str | None] = mapped_column(String(26))
    origin: Mapped[str] = mapped_column(String(8), default="gateway")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = _id()
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    subject_type: Mapped[str] = mapped_column(String(10))  # device | plant | hub | command
    subject_id: Mapped[str] = mapped_column(String(26))
    subject_name: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(8), default="warning")
    opened_at: Mapped[datetime] = _created()
    resolved_at: Mapped[datetime | None]
    acked_by: Mapped[str | None] = mapped_column(String(128))
    acked_at: Mapped[datetime | None]
    detail: Mapped[dict | None]

    __table_args__ = (
        # One open alert per (kind, subject).
        Index("uq_open_alert", "household_id", "kind", "subject_id", unique=True,
              postgresql_where=text("resolved_at IS NULL"),
              sqlite_where=text("resolved_at IS NULL")),
    )


class PushToken(Base):
    __tablename__ = "push_tokens"
    token: Mapped[str] = mapped_column(String(512), primary_key=True)
    user_uid: Mapped[str] = mapped_column(ForeignKey("users.uid", ondelete="CASCADE"), index=True)
    platform: Mapped[str | None] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = _id()
    household_id: Mapped[str | None] = mapped_column(String(26), index=True)
    actor: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict | None]
    ts: Mapped[datetime] = _created()
    ip: Mapped[str | None] = mapped_column(String(64))
