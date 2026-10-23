"""Errors that become `error` answers on the bus (Gateway/specs.md 3.3)."""

STATUS = {
    "validation": 422, "not_found": 404, "conflict": 409, "busy": 409,
    "device_not_ready": 409, "device_safe_mode": 409, "slot_not_actuator": 422,
    "safety_limit": 422, "unknown_kind": 400, "expired": 408, "unsupported_version": 400,
    "battery_critical": 409,
}


class HubError(Exception):
    def __init__(self, type: str, title: str = "", detail: str = ""):
        super().__init__(title or type)
        self.type = type
        self.status = STATUS.get(type, 500)
        self.title = title or type.replace("_", " ")
        self.detail = detail

    def as_dict(self) -> dict:
        return {"type": self.type, "status": self.status, "title": self.title, "detail": self.detail}
