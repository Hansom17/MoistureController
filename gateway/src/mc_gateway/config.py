"""Agent settings from environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "0.1.0"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is not None:
        return value
    file = os.environ.get(f"{name}_FILE")
    return Path(file).read_text().strip() if file else default


@dataclass
class GatewayConfig:
    data_dir: Path = Path("/data")
    api_url: str = "https://api.example.com"
    # Local broker, internal listener (Broker_Specs §4).
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_username: str = "mc-agent"
    mqtt_password: str | None = None
    # What devices store at pairing (gateway_api.md §5.4). The service can't see
    # the host's LAN address from inside its container, so it is configured.
    lan_host: str | None = None
    lan_port: int = 8883
    adapters: tuple[str, ...] = ("esp32-mqtt",)
    arch: str = field(default_factory=lambda: os.uname().machine)
    state_interval_s: int = 600
    assume_time_synced: bool = True

    @property
    def broker_dir(self) -> Path:
        return self.data_dir / "broker"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "gateway.db"

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        c = cls()
        c.data_dir = Path(_env("MC_GATEWAY_DATA", str(c.data_dir)))
        c.api_url = _env("MC_API_URL", c.api_url).rstrip("/")
        c.mqtt_host = _env("MC_MQTT_HOST", c.mqtt_host)
        c.mqtt_port = int(_env("MC_MQTT_PORT", str(c.mqtt_port)))
        c.mqtt_username = _env("MC_MQTT_USERNAME", c.mqtt_username)
        c.mqtt_password = _env("MC_MQTT_PASSWORD")
        c.lan_host = _env("MC_LAN_HOST")
        c.lan_port = int(_env("MC_LAN_PORT", str(c.lan_port)))
        c.state_interval_s = int(_env("MC_STATE_INTERVAL_S", str(c.state_interval_s)))
        c.assume_time_synced = _env("MC_ASSUME_TIME_SYNCED", "1") == "1"
        return c
