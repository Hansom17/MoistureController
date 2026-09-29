"""Settings from environment variables (Api_Specs §13.1)."""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is not None:
        return value
    file = os.environ.get(f"{name}_FILE")  # Docker secrets
    if file:
        return Path(file).read_text().strip()
    return default


@dataclass
class Settings:
    database_url: str = "sqlite+aiosqlite:///./mc-dev.db"


    # 32 bytes hex; encrypts device PSKs in the database.
    key_encryption_key: str = field(default_factory=lambda: secrets.token_hex(32))

    # "firebase" in every real deployment. "dev" accepts `Bearer dev:<uid>`
    # tokens and must never be enabled on a public server.
    auth_mode: str = "dev"
    firebase_credentials: str | None = None
    firebase_project_id: str | None = None

    public_api_url: str = "http://localhost:8000"
    app_url: str = "http://localhost:8420"
    cors_origins: list[str] = field(default_factory=list)
    max_households_per_user: int = 10
    min_app_version: str | None = None
    latest_gateway_version: str = "0.1.0"
    docs_enabled: bool = True
    jobs_interval_s: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        s.database_url = _env("MC_DATABASE_URL", s.database_url)
        db_password = _env("MC_DATABASE_PASSWORD")
        if db_password and "{password}" in s.database_url:
            from urllib.parse import quote

            s.database_url = s.database_url.replace("{password}", quote(db_password, safe=""))
        s.auth_mode = _env("MC_AUTH_MODE", "firebase")
        key = _env("MC_KEY_ENCRYPTION_KEY")
        if key:
            s.key_encryption_key = key
        elif s.auth_mode == "dev":
            # Stable across restarts so stored PSKs stay readable in dev.
            key_file = Path(".mc-dev-key")
            if not key_file.exists():
                key_file.write_text(s.key_encryption_key)
            s.key_encryption_key = key_file.read_text().strip()
        else:
            raise RuntimeError("MC_KEY_ENCRYPTION_KEY is required")
        s.firebase_credentials = _env("MC_FIREBASE_CREDENTIALS")
        s.firebase_project_id = _env("MC_FIREBASE_PROJECT_ID")
        s.public_api_url = _env("MC_PUBLIC_API_URL", s.public_api_url)
        s.app_url = _env("MC_APP_URL", s.app_url)
        s.cors_origins = [o for o in (_env("MC_CORS_ORIGINS", "") or "").split(",") if o]
        s.max_households_per_user = int(
            _env("MC_MAX_HOUSEHOLDS_PER_USER", str(s.max_households_per_user)))
        s.min_app_version = _env("MC_MIN_APP_VERSION")
        s.latest_gateway_version = _env("MC_LATEST_GATEWAY_VERSION", s.latest_gateway_version)
        s.docs_enabled = _env("MC_DOCS", "1" if s.auth_mode == "dev" else "0") == "1"
        return s
