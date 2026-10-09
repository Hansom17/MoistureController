from dataclasses import dataclass, field


@dataclass
class Effects:
    """What to do after a commit: publish events and snapshots, wake the sender, notify."""
    events: list[tuple[str, dict]] = field(default_factory=list)
    snapshots: set[str] = field(default_factory=set)
    wake: set[str] = field(default_factory=set)             # device ids the sender should look at
    returned: set[str] = field(default_factory=set)         # devices that just reported (reset retry counters)
    out: list[tuple[str, bytes]] = field(default_factory=list)  # raw publishes (Zigbee2MQTT requests) after commit
    notes: list[dict] = field(default_factory=list)         # {"text", "channels", "kind", ...}

    def emit(self, kind: str, body: dict) -> None:
        self.events.append((kind, body))

    def touch(self, *names: str) -> None:
        self.snapshots.update(names)

    def publish(self, topic: str, payload: bytes) -> None:
        self.out.append((topic, payload))

    def kick(self, device_id: str) -> None:
        self.wake.add(device_id)

    def notify(self, text: str, channels: list[str], kind: str, **extra) -> None:
        self.notes.append({"text": text, "channels": channels, "kind": kind, **extra})
