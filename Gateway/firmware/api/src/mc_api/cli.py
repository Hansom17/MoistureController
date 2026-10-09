import argparse
import asyncio

from sqlalchemy import func, select

from .config import Settings
from .db import migrate
from .db.models import Setting, User
from .db.session import make_engine, make_sessionmaker
from .main import configure_logging, run
from .security import new_code


async def _status(settings: Settings, reset: bool) -> None:
    migrate.upgrade_sync(settings.db_path)
    engine = make_engine(settings.db_path)
    sessions = make_sessionmaker(engine)
    async with sessions() as s:
        owners = (await s.execute(select(func.count()).select_from(User).where(User.role == "owner"))).scalar()
        code = await s.get(Setting, "setup_code")
        if reset:
            code = code or Setting(key="setup_code", value=None)
            code.value = new_code()
            s.add(code)
            flag = await s.get(Setting, "owner_reset") or Setting(key="owner_reset", value=True)
            flag.value = True
            s.add(flag)
            await s.commit()
        reset_flag = await s.get(Setting, "owner_reset")
        if not owners or (reset_flag and reset_flag.value):
            print(f"setup code: {code.value if code and code.value else '(created when the service first starts)'}")
        else:
            print("this gateway is set up")
    await engine.dispose()


def main() -> None:
    ap = argparse.ArgumentParser(prog="mc-api")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run the api service")
    sub.add_parser("migrate", help="apply database migrations and exit")
    sub.add_parser("status", help="show whether the gateway is set up (and the setup code if not)")
    sub.add_parser("reset-owner", help="create a new setup code so a new owner can be set up")
    args = ap.parse_args()
    configure_logging()
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if args.cmd == "run":
        asyncio.run(run(settings))
    elif args.cmd == "migrate":
        migrate.upgrade_sync(settings.db_path)
    else:
        asyncio.run(_status(settings, reset=args.cmd == "reset-owner"))
