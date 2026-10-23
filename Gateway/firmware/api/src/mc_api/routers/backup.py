import time
from sqlalchemy import text


async def backup_api_db(app) -> dict:
    d = app.settings.data_dir / "backups"
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(app.clock.now()))
    target = d / f"api-{stamp}.db"
    n = 1
    while target.exists():
        target = d / f"api-{stamp}-{n}.db"
        n += 1
    async with app.engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("VACUUM INTO :p"), {"p": str(target)})
    for old in sorted(d.glob("api-*.db"))[:-14]:
        old.unlink()
    return {"file": target.name, "size": target.stat().st_size}
