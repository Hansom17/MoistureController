"""Join window state (Gateway/specs.md 7.3)."""

INSTALL_CODE_HEX = set("0123456789abcdefABCDEF")


def clean_install_code(code: str) -> str:
    c = "".join(ch for ch in str(code) if ch not in " -:")
    if not 16 <= len(c) <= 36 or not set(c) <= INSTALL_CODE_HEX:
        raise ValueError("install code must be 16-36 hex digits")
    return c.upper()


class Join:
    """Mutated in place: the `join` snapshot publishes this same dict."""

    def __init__(self) -> None:
        self.state: dict = {"open": False, "ends_at": None, "devices": [], "error": None}

    def open(self, now: int, seconds: int) -> None:
        self.state.update(open=True, ends_at=now + seconds, devices=[], error=None)

    def close(self, error: str | None = None) -> None:
        self.state.update(open=False, ends_at=None, error=error)

    def joined(self, device_id: str) -> bool:
        if self.state["open"] and device_id not in self.state["devices"]:
            self.state["devices"].append(device_id)
            return True
        return False

    def expired(self, now: int) -> bool:
        return bool(self.state["open"] and self.state["ends_at"] is not None and now >= self.state["ends_at"])
