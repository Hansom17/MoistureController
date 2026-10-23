"""Normalized device messages (Gateway/specs.md Part B)."""
from dataclasses import dataclass, field


@dataclass
class SlotReading:
    slot: int
    type: str
    value: float | None
    raw: int | None
    error: str


@dataclass
class Telemetry:
    seq: int
    boot_id: int | None
    slots: list[SlotReading]
    voltage_mv: int | None
    linkquality: int | None
    batt_mv: int | None = None        # millivolt resolution, 0 without a cell
    batt_state: str | None = None     # absent | ok | low | critical


@dataclass
class Status:
    status: str                      # operational | interviewing | safe_mode
    safe_reason: str | None
    fast_mode: bool
    board: str | None
    interface: str | None
    config_schema: int | None
    diagnostics: dict = field(default_factory=dict)


@dataclass
class Event:
    n: int
    code: str
    slot: int | None
    arg: int | None


@dataclass
class CmdAck:
    n: int
    cmd_id: int
    state: str                       # running | done | failed | rejected | cancelled
    reason: str
    ends_in_s: int | None


@dataclass
class ConfigState:
    cfg_rev: int
    cfg_result: str | None
    cfg_error: object = None
