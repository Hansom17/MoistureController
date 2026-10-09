from dataclasses import dataclass, field


@dataclass
class Effects:
    """What to publish after a commit."""
    events: list[tuple[str, dict]] = field(default_factory=list)
    snapshots: set[str] = field(default_factory=set)

    def emit(self, kind: str, body: dict) -> None:
        self.events.append((kind, body))

    def touch(self, *names: str) -> None:
        self.snapshots.update(names)
