"""MQTT topic names (mqtt.md §3, hub.md §4–5)."""

from dataclasses import dataclass
from typing import Literal

DEVICE_PREFIX = "mc/v1/"
HUB_PREFIX = "mc/hub/v1/"

# Device → server suffixes, in the order a wake cycle sends them.
DEVICE_UP = ("status", "telemetry", "event", "cmd/ack", "config/state")
DEVICE_DOWN = ("cmd", "config/desired")


def device(device_id: str, suffix: str) -> str:
    return f"{DEVICE_PREFIX}{device_id}/{suffix}"


def hub(hub_id: str, suffix: str) -> str:
    return f"{HUB_PREFIX}{hub_id}/{suffix}"


@dataclass(frozen=True)
class Topic:
    kind: Literal["device", "hub"]
    id: str
    suffix: str


def parse(topic: str) -> Topic | None:
    """Split a topic into device/hub id and suffix; None for foreign topics."""
    if topic.startswith(HUB_PREFIX):
        rest = topic[len(HUB_PREFIX) :]
        kind: Literal["device", "hub"] = "hub"
    elif topic.startswith(DEVICE_PREFIX):
        rest = topic[len(DEVICE_PREFIX) :]
        kind = "device"
    else:
        return None
    ident, _, suffix = rest.partition("/")
    if not ident or not suffix:
        return None
    return Topic(kind, ident, suffix)
