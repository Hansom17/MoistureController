"""Alembic upgrade at startup (Server_Specs §13.2: migrations on start)."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade(database_url: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")
