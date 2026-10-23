"""Zigbee2MQTT state JSON -> normalized messages (Gateway/specs.md 7.5)."""
import re

from .messages import CmdAck, ConfigState, Event, SlotReading, Status, Telemetry

SLOT = re.compile(r"^slot(\d)_(type|value|raw|error)$")
DIAG = ("uptime_s", "boot_reason", "reset_count", "rejoin_count", "last_error", "free_heap")


def normalize(p: dict) -> list:
    out: list = []
    if "seq" in p and p["seq"] is not None:
        slots: dict[int, dict] = {}
        for k, v in p.items():
            m = SLOT.match(k)
            if m:
                slots.setdefault(int(m.group(1)), {})[m.group(2)] = v
        readings = [
            SlotReading(slot=i, type=str(d.get("type", "empty")), value=d.get("value"),
                        raw=d.get("raw"), error=str(d.get("error", "ok")))
            for i, d in sorted(slots.items()) if d.get("type") not in (None, "empty")
        ]
        out.append(Telemetry(seq=int(p["seq"]), boot_id=p.get("boot_id"), slots=readings,
                             voltage_mv=p.get("voltage_mv"), linkquality=p.get("linkquality"),
                             batt_mv=p.get("batt_mv"), batt_state=p.get("batt_state")))
    elif "linkquality" in p and len(p) <= 2:
        out.append(Telemetry(seq=-1, boot_id=None, slots=[], voltage_mv=p.get("voltage_mv"),
                             linkquality=p.get("linkquality")))
    if "status" in p and isinstance(p["status"], str):
        out.append(Status(status=p["status"], safe_reason=p.get("safe_reason"), fast_mode=bool(p.get("fast_mode")),
                          board=p.get("board"), interface=p.get("interface"), config_schema=p.get("config_schema"),
                          diagnostics={k: p[k] for k in DIAG if k in p}))
    ev = p.get("event")
    if isinstance(ev, dict) and "n" in ev and "code" in ev:
        out.append(Event(n=int(ev["n"]), code=str(ev["code"]), slot=ev.get("slot"), arg=ev.get("arg")))
    ack = p.get("cmd_ack")
    if isinstance(ack, dict) and "n" in ack and "cmd_id" in ack:
        out.append(CmdAck(n=int(ack["n"]), cmd_id=int(ack["cmd_id"]), state=str(ack.get("state", "")),
                          reason=str(ack.get("reason", "none")), ends_in_s=ack.get("ends_in_s")))
    if "cfg_rev" in p and p["cfg_rev"] is not None:
        out.append(ConfigState(cfg_rev=int(p["cfg_rev"]), cfg_result=p.get("cfg_result"), cfg_error=p.get("cfg_error")))
    return out


def is_newer_u16(new: int, old: int | None) -> bool:
    """Serial-number arithmetic for the module's 16-bit sample counter."""
    if old is None:
        return True
    d = (new - old) % 65536
    return 1 <= d < 32768
