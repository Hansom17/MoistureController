"""Errors as RFC 9457 problem+json with stable `type`s."""

STATUS = {
    "validation": 422, "not_found": 404, "conflict": 409, "busy": 409, "device_not_ready": 409,
    "device_safe_mode": 409, "battery_critical": 409, "slot_not_actuator": 422, "safety_limit": 422, "unknown_kind": 400,
    "unauthorized": 401, "invalid_credentials": 401, "reauth_required": 401, "forbidden": 403,
    "rate_limited": 429, "hub_unavailable": 503, "hub_timeout": 504, "incompatible_hub": 503,
    "setup_required": 409, "already_set_up": 409, "invalid_setup_code": 403, "invalid_invite": 404,
}


class ApiError(Exception):
    def __init__(self, type: str, title: str = "", detail: str = "", status: int | None = None, **extra):
        super().__init__(title or type)
        self.type = type
        self.status = status or STATUS.get(type, 500)
        self.title = title or type.replace("_", " ").capitalize()
        self.detail = detail
        self.extra = extra

    def body(self) -> dict:
        return {"type": f"https://moisture.local/problems/{self.type}", "code": self.type, "title": self.title,
                "status": self.status, "detail": self.detail, **self.extra}
