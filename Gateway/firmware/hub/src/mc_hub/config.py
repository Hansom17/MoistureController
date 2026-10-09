import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path = Path("/data")
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_user: str | None = None
    mqtt_password: str | None = None
    z2m_base_topic: str = "zigbee2mqtt"
    instance: str = field(default="hub")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "hub.db"

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        return cls(
            data_dir=Path(e.get("MC_DATA_DIR", "/data")),
            mqtt_host=e.get("MC_MQTT_HOST", "mosquitto"),
            mqtt_port=int(e.get("MC_MQTT_PORT", "1883")),
            mqtt_user=e.get("MC_MQTT_USER"),
            mqtt_password=e.get("MC_MQTT_PASSWORD"),
            z2m_base_topic=e.get("MC_Z2M_BASE_TOPIC", "zigbee2mqtt"),
        )
