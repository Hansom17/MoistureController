"""Hub timestamps are Unix seconds; the REST API speaks ISO 8601 (UTC)."""
from datetime import datetime, timezone

TS_KEYS = {"ts", "exp", "latest_ts", "from", "to"}


def iso(ts: int | float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def to_api(obj):
    """Converts the timestamp fields of hub data (`*_at`, `ts`, `exp`, ...) to ISO strings."""
    if isinstance(obj, list):
        return [to_api(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and (k.endswith("_at") or k in TS_KEYS):
                out[k] = iso(v)
            else:
                out[k] = to_api(v)
        return out
    return obj


def to_unix(value) -> int | None:
    """Query parameters: ISO 8601 or Unix seconds -> Unix seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        return int(value)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())
