"""Battery interpretation (Gateway/specs.md 13.1): the module measures and classifies, the hub estimates the level."""

from mc_hub.params import BATTERY, CONFIG

DEFAULT_LOW_MV = CONFIG["batt_low_mv"]["default"]
DEFAULT_CRITICAL_MV = CONFIG["batt_critical_mv"]["default"]
CAL_MIN, CAL_MAX = CONFIG["batt_cal_permille"]["min"], CONFIG["batt_cal_permille"]["max"]
CHEMISTRY = BATTERY["chemistry"]
HIST = BATTERY["history_reports"]            # reports the percentage is smoothed over
STALE_FACTOR = BATTERY["stale_factor"]       # a percentage needs a report younger than this many report intervals
PRESENT_MIN_MV = BATTERY["present_min_mv"]
CURVES = BATTERY["percent_curves"]           # rest voltage -> percent, a starting point (interface.yaml)
STATES = ("absent", "ok", "low", "critical")


def percent(mv: int, chemistry: str = CHEMISTRY) -> int:
    curve = CURVES[chemistry]
    if mv >= curve[0][0]:
        return 100
    if mv <= curve[-1][0]:
        return 0
    for (hi_mv, hi_p), (lo_mv, lo_p) in zip(curve, curve[1:]):
        if lo_mv <= mv <= hi_mv:
            return round(lo_p + (hi_p - lo_p) * (mv - lo_mv) / (hi_mv - lo_mv))
    return 0


def median(values: list[int]) -> int:
    v = sorted(values)
    return v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) // 2


def state_from(mv: int | None, low: int, critical: int) -> str:
    """For a module that only reports the standard voltage attribute (no `batt_state`)."""
    if not mv or mv < PRESENT_MIN_MV:
        return "absent"
    if mv <= critical:
        return "critical"
    if mv <= low:
        return "low"
    return "ok"


def push(hist: list[int] | None, mv: int) -> list[int]:
    return ((hist or []) + [mv])[-HIST:]


def view(d, now: int | None = None) -> dict:
    """The `battery` object of a device snapshot."""
    state = d.batt_state or ("absent" if not d.voltage_mv else "ok")
    present = state != "absent" and bool(d.voltage_mv)
    pct = None
    if present and d.batt_hist:
        fresh = True
        interval = d.report_interval_s or 300
        if now is not None and d.last_seen_at is not None:
            fresh = now - d.last_seen_at <= STALE_FACTOR * max(interval, 60)
        if fresh:
            pct = percent(median(d.batt_hist))
    cal = ((d.reported_config or {}).get("batt_cal_permille") or 1000)
    return {"mv": d.voltage_mv if present else 0, "percent": pct, "state": state, "present": present,
            "calibrated": cal != 1000, "cal_permille": cal}


def calibrate_permille(reported_mv: int, current_permille: int, measured_mv: int) -> int:
    """New correction from a multimeter reading. Raises ValueError outside the allowed range."""
    if reported_mv <= 0 or measured_mv <= 0:
        raise ValueError("the module reports no battery voltage to calibrate against")
    uncorrected = reported_mv * 1000 / current_permille
    new = round(measured_mv / uncorrected * 1000)
    if not CAL_MIN <= new <= CAL_MAX:
        raise ValueError("more than 10 % off: check the wiring before calibrating")
    return new
