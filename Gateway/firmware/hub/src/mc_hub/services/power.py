"""What the hub needs to know about a module's power mode (PlantModule/specs.md 18)."""
from mc_hub.db.models import Device

DEEP_SLEEP = 2
WINDOW_MARGIN_S = 2        # the module may close its awake window a little before our clock says so
SLEEP_AFTER_MARGIN_S = 5   # status `sleeping` this long after the window should have closed


def settings(d: Device) -> tuple[int, int, int]:
    """(power_mode, awake_s, report_interval_s) of the configuration the module runs (or is meant to run)."""
    cfg = d.reported_config or d.desired_config or {}
    return int(cfg.get("power_mode", 0)), int(cfg.get("awake_s", 5)), int(cfg.get("report_interval_s", 300))


def is_deep(d: Device) -> bool:
    return settings(d)[0] == DEEP_SLEEP


def window_closed(d: Device, now: int, margin_s: int = WINDOW_MARGIN_S) -> bool:
    """A deep-sleep module listens only for `awake_s` after it reported: nothing can be sent after that."""
    mode, awake_s, _ = settings(d)
    if mode != DEEP_SLEEP:
        return False
    return d.last_seen_at is None or now - d.last_seen_at > awake_s + margin_s
