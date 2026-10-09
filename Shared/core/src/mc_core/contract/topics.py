"""MQTT topic names of ESP32 devices (mqtt.md §3)."""

from dataclasses import dataclass

DEVICE_PREFIX = "mc/v1/"

# Device → server suffixes, in the order a wake cycle sends them.
DEVICE_UP = ("status", "telemetry", "event", "cmd/ack", "config/state")
DEVICE_DOWN = ("cmd", "config/desired")


def device(device_id: str, suffix: str) -> str:
    return f"{DEVICE_PREFIX}{device_id}/{suffix}"


@dataclass(frozen=True)
class Topic:
    id: str
    suffix: str


def parse(topic: str) -> Topic | None:
    """Split a device topic into device id and suffix; None for foreign topics."""
    if not topic.startswith(DEVICE_PREFIX):
        return None
    ident, _, suffix = topic[len(DEVICE_PREFIX) :].partition("/")
    if not ident or not suffix:
        return None
    return Topic(ident, suffix)
