import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

HERE = Path(__file__).resolve().parent.parent


def _config(db_path: Path | str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(HERE / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def upgrade_sync(db_path: Path | str) -> None:
    command.upgrade(_config(db_path), "head")


async def upgrade(db_path: Path | str) -> None:
    await asyncio.to_thread(upgrade_sync, db_path)
