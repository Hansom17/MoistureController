"""hub.db tables (Gateway/specs.md 4.2). Timestamps are UTC Unix seconds."""
from sqlalchemy import ForeignKey, Index, Integer, String, Text, JSON, Boolean, Float, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)


class RequestRecord(Base):
    __tablename__ = "requests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    answer: Mapped[dict] = mapped_column(JSON)
    ts: Mapped[int] = mapped_column(Integer, index=True)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ieee: Mapped[str] = mapped_column(String, unique=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, default="")
    fw: Mapped[str | None] = mapped_column(String, nullable=True)
    board: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="joining")
    last_seen_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_interval_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voltage_mv: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    boot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_event_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_ack_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    safe_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    desired_rev: Mapped[int] = mapped_column(Integer, default=0)
    desired_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reported_rev: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rejected_rev: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sensor_error_streak: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    slots: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # latest reading per slot
    diagnostics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)
    deleted_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConfigRevision(Base):
    __tablename__ = "config_revisions"
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    rev: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String, default="desired")
    body: Mapped[dict] = mapped_column(JSON)
    result: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)


class Plant(Base):
    __tablename__ = "plants"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    notes: Mapped[str] = mapped_column(Text, default="")
    sensor_device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    sensor_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pump_device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    pump_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)
    archived_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Reading(Base):
    __tablename__ = "readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    slot: Mapped[int] = mapped_column(Integer)
    plant_id: Mapped[str | None] = mapped_column(ForeignKey("plants.id"), nullable=True)
    type: Mapped[str] = mapped_column(String)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(String, default="ok")
    ts: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (Index("ix_readings_plant_ts", "plant_id", "ts"),
                      Index("ix_readings_device_slot_ts", "device_id", "slot", "ts"))


class HealthReport(Base):
    __tablename__ = "health_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    ts: Mapped[int] = mapped_column(Integer)
    voltage_mv: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diagnostics: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DeviceEvent(Base):
    __tablename__ = "device_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    ts: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String)
    slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Command(Base):
    __tablename__ = "commands"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    zb_id: Mapped[int] = mapped_column(Integer, unique=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    plant_id: Mapped[str | None] = mapped_column(ForeignKey("plants.id"), nullable=True)
    action: Mapped[str] = mapped_column(String)
    args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="manual")
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer)
    exp: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivered_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ends_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_of: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[int] = mapped_column(Integer)


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plants.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    threshold: Mapped[int] = mapped_column(Integer)
    water_s: Mapped[int] = mapped_column(Integer)
    cooldown_s: Mapped[int] = mapped_column(Integer)
    max_per_day: Mapped[int] = mapped_column(Integer)
    quiet_from: Mapped[str | None] = mapped_column(String, nullable=True)
    quiet_to: Mapped[str | None] = mapped_column(String, nullable=True)
    notify_channels: Mapped[list] = mapped_column(JSON, default=lambda: ["app"])
    notify_on: Mapped[list] = mapped_column(JSON, default=lambda: ["failed"])
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[int] = mapped_column(Integer)
    deleted_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RuleExecution(Base):
    __tablename__ = "rule_executions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"), index=True)
    plant_id: Mapped[str] = mapped_column(String)
    ts: Mapped[int] = mapped_column(Integer)
    reading_ref: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[str] = mapped_column(String)
    skip_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    command_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    subject_type: Mapped[str] = mapped_column(String)
    subject_id: Mapped[str] = mapped_column(String)
    subject_name: Mapped[str] = mapped_column(String, default="")
    severity: Mapped[str] = mapped_column(String, default="warning")
    opened_at: Mapped[int] = mapped_column(Integer)
    resolved_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acked_by: Mapped[str | None] = mapped_column(String, nullable=True)
    acked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        # one open alert per (kind, subject)
        Index("uq_alerts_open", "kind", "subject_type", "subject_id", unique=True,
              sqlite_where=text("resolved_at IS NULL")),
    )
