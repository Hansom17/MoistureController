"""Consistent copies of hub.db (Gateway/specs.md section 14)."""
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

KEEP = 14


class Backup:
    def __init__(self, engine: AsyncEngine, directory: Path | None) -> None:
        self.engine, self.dir = engine, directory

    async def run(self, now: int) -> dict:
        if self.dir is None:
            raise RuntimeError("no backup directory configured")
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now))
        target = self.dir / f"hub-{stamp}.db"
        n = 1
        while target.exists():
            target = self.dir / f"hub-{stamp}-{n}.db"
            n += 1
        async with self.engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text("VACUUM INTO :p"), {"p": str(target)})
        for old in sorted(self.dir.glob("hub-*.db"))[:-KEEP]:
            old.unlink()
        return {"file": target.name, "size": target.stat().st_size}
