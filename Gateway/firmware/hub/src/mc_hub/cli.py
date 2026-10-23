import argparse
import asyncio

from .config import Settings
from .db import migrate
from .main import configure_logging, run


def main() -> None:
    ap = argparse.ArgumentParser(prog="mc-hub")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run the hub service")
    sub.add_parser("migrate", help="apply database migrations and exit")
    args = ap.parse_args()
    configure_logging()
    settings = Settings.from_env()
    if args.cmd == "migrate":
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        migrate.upgrade_sync(settings.db_path)
    else:
        asyncio.run(run(settings))
