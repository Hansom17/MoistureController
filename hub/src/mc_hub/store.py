"""Local SQLite state (Hub_Specs §5.4). Not a history store: 7 days max."""

import json
import sqlite3
import time
from pathlib import Path

RETENTION_S = 7 * 86400

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK (id = 1), rev INTEGER, body TEXT);
CREATE TABLE IF NOT EXISTS readings_recent (
    device TEXT, slot INTEGER, seq INTEGER, ts INTEGER, type TEXT, value REAL, error TEXT);
CREATE INDEX IF NOT EXISTS ix_readings ON readings_recent (device, slot, ts);
CREATE TABLE IF NOT EXISTS commands (
    id TEXT PRIMARY KEY, device TEXT, slot INTEGER, action TEXT, seconds INTEGER,
    source TEXT, rule_id TEXT, plant_id TEXT, status TEXT, created_at INTEGER,
    exp INTEGER, finished_at INTEGER);
CREATE TABLE IF NOT EXISTS rule_decisions (
    id TEXT PRIMARY KEY, rule_id TEXT, plant_id TEXT, ts INTEGER, value REAL,
    decision TEXT, skip_reason TEXT, command_id TEXT);
"""

OPEN = ("queued", "delivered")


class Store:
    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(str(path), isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    # --- meta ----------------------------------------------------------------------

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return default if row is None else row["value"]

    def set(self, key: str, value: str | int | None) -> None:
        if value is None:
            self.db.execute("DELETE FROM meta WHERE key = ?", (key,))
        else:
            self.db.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) "
                            "DO UPDATE SET value = excluded.value", (key, str(value)))

    def get_int(self, key: str) -> int:
        return int(self.get(key, "0"))

    # --- snapshot -----------------------------------------------------------------------

    def snapshot(self) -> dict | None:
        row = self.db.execute("SELECT body FROM snapshot WHERE id = 1").fetchone()
        return None if row is None else json.loads(row["body"])

    def save_snapshot(self, rev: int, body: dict) -> None:
        self.db.execute("INSERT INTO snapshot (id, rev, body) VALUES (1, ?, ?) ON CONFLICT(id) "
                        "DO UPDATE SET rev = excluded.rev, body = excluded.body",
                        (rev, json.dumps(body)))

    # --- readings ----------------------------------------------------------------------

    def add_reading(self, device: str, slot: int, seq: int, ts: int, type_: str,
                    value: float | None, error: str | None) -> None:
        self.db.execute("INSERT INTO readings_recent VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (device, slot, seq, ts, type_, value, error))

    def latest_reading(self, device: str, slot: int) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM readings_recent WHERE device = ? AND slot = ? ORDER BY ts DESC LIMIT 1",
            (device, slot)).fetchone()

    # --- commands -----------------------------------------------------------------------

    def upsert_command(self, id_: str, device: str, action: str, args: dict, *, source: str,
                       status: str, created_at: int, exp: int, rule_id: str | None = None,
                       plant_id: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO commands (id, device, slot, action, seconds, source, rule_id, plant_id, "
            "status, created_at, exp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            (id_, device, args.get("slot"), action, args.get("seconds"), source, rule_id,
             plant_id, status, created_at, exp))

    def set_command_status(self, id_: str, status: str, finished_at: int | None = None) -> bool:
        cur = self.db.execute(
            "UPDATE commands SET status = ?, finished_at = COALESCE(?, finished_at) WHERE id = ?",
            (status, finished_at, id_))
        return cur.rowcount > 0

    def expire_commands(self, now: int) -> None:
        self.db.execute("UPDATE commands SET status = 'expired' WHERE status = 'queued' "
                        "AND exp < ?", (now,))

    def pending_pump(self, device: str, slot: int) -> bool:
        return self.db.execute(
            "SELECT 1 FROM commands WHERE device = ? AND slot = ? AND action = 'pump.run' "
            "AND status IN ('queued', 'delivered')", (device, slot)).fetchone() is not None

    def last_run_end(self, device: str, slot: int) -> int | None:
        row = self.db.execute(
            "SELECT MAX(finished_at) AS t FROM commands WHERE device = ? AND slot = ? "
            "AND action = 'pump.run' AND status = 'done'", (device, slot)).fetchone()
        return row["t"]

    def rule_commands(self, plant_id: str, since: int) -> tuple[int | None, int]:
        """(last rule command time, rule commands since `since`) for a plant."""
        last = self.db.execute("SELECT MAX(created_at) AS t FROM commands WHERE plant_id = ? "
                               "AND source = 'rule'", (plant_id,)).fetchone()["t"]
        count = self.db.execute("SELECT COUNT(*) AS n FROM commands WHERE plant_id = ? "
                                "AND source = 'rule' AND created_at >= ?",
                                (plant_id, since)).fetchone()["n"]
        return last, count

    def recent_commands(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM commands ORDER BY created_at DESC LIMIT ?",
                               (limit,)).fetchall()

    # --- decisions ------------------------------------------------------------------------

    def add_decision(self, id_: str, rule_id: str, plant_id: str, ts: int, value: float | None,
                     decision: str, skip_reason: str | None, command_id: str | None) -> None:
        self.db.execute("INSERT INTO rule_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (id_, rule_id, plant_id, ts, value, decision, skip_reason, command_id))

    def recent_decisions(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM rule_decisions ORDER BY ts DESC LIMIT ?",
                               (limit,)).fetchall()

    # --- housekeeping -------------------------------------------------------------------------

    def cleanup(self, now: int | None = None) -> None:
        cutoff = (now or int(time.time())) - RETENTION_S
        self.db.execute("DELETE FROM readings_recent WHERE ts < ?", (cutoff,))
        self.db.execute("DELETE FROM commands WHERE created_at < ?", (cutoff,))
        self.db.execute("DELETE FROM rule_decisions WHERE ts < ?", (cutoff,))

    def reset(self) -> None:
        """Forget enrollment, keys and snapshot (Hub_Specs §3 "Removed", `mc-hub reset`)."""
        for table in ("meta", "snapshot", "readings_recent", "commands", "rule_decisions"):
            self.db.execute(f"DELETE FROM {table}")  # noqa: S608 — fixed names
