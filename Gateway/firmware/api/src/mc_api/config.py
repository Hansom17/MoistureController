import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path = Path("/data")
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_user: str | None = None
    mqtt_password: str | None = None
    mqtt_ca: str | None = None
    instance: str = "api-1"
    bind: str = "0.0.0.0"
    port: int = 8000
    web_dir: Path | None = None
    token_max_age_days: int = 180
    docs: bool = False
    request_timeout_s: float = 10.0

    @property
    def db_path(self) -> Path:
        return self.data_dir / "api.db"

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        return cls(
            data_dir=Path(e.get("MC_DATA_DIR", "/data")),
            mqtt_host=e.get("MC_MQTT_HOST", "mosquitto"), mqtt_port=int(e.get("MC_MQTT_PORT", "1883")),
            mqtt_user=e.get("MC_MQTT_USER"), mqtt_password=e.get("MC_MQTT_PASSWORD"), mqtt_ca=e.get("MC_MQTT_CA"),
            instance=e.get("MC_INSTANCE_ID", "api-1"), bind=e.get("MC_BIND", "0.0.0.0"),
            port=int(e.get("MC_PORT", "8000")),
            web_dir=Path(e["MC_WEB_DIR"]) if e.get("MC_WEB_DIR") else None,
            token_max_age_days=int(e.get("MC_TOKEN_MAX_AGE_DAYS", "180")),
            docs=e.get("MC_DOCS") == "1", request_timeout_s=float(e.get("MC_REQUEST_TIMEOUT_S", "10")),
        )
