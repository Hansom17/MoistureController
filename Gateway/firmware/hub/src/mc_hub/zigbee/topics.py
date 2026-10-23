"""Zigbee2MQTT topics (Gateway/specs.md 7.1 / 7.2)."""
import json


class Z2MTopics:
    def __init__(self, base: str = "zigbee2mqtt") -> None:
        self.base = base

    @property
    def bridge_state(self) -> str: return f"{self.base}/bridge/state"
    @property
    def bridge_devices(self) -> str: return f"{self.base}/bridge/devices"
    @property
    def bridge_event(self) -> str: return f"{self.base}/bridge/event"
    @property
    def bridge_response(self) -> str: return f"{self.base}/bridge/response/#"
    @property
    def bridge_response_permit_join(self) -> str: return f"{self.base}/bridge/response/permit_join"
    @property
    def device_state(self) -> str: return f"{self.base}/+"
    @property
    def device_availability(self) -> str: return f"{self.base}/+/availability"

    def set(self, name: str) -> str: return f"{self.base}/{name}/set"
    def request(self, what: str) -> str: return f"{self.base}/bridge/request/{what}"

    def parse(self, topic: str) -> tuple[str, str] | None:
        """-> ('state'|'availability', friendly_name) for device topics, else None."""
        if not topic.startswith(self.base + "/"):
            return None
        parts = topic[len(self.base) + 1:].split("/")
        if parts[0] == "bridge":
            return None
        if len(parts) == 1:
            return "state", parts[0]
        if len(parts) == 2 and parts[1] == "availability":
            return "availability", parts[0]
        return None


def parse_state_value(payload: bytes) -> str:
    """bridge/state and availability are `{"state": "online"}` (2.x) or a bare string (older)."""
    text = payload.decode(errors="replace").strip()
    try:
        data = json.loads(text)
    except ValueError:
        return text.strip('"')
    if isinstance(data, dict):
        return str(data.get("state", ""))
    return str(data)
