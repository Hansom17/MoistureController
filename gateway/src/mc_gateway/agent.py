"""Gateway logic (Gateway_Specs §5), independent of connections.

Everything that goes up to the API (contracts/gateway_api.md) is appended to the SQLite outbox with a `seq` and sent by the uplink (uplink.py);
down messages are applied by the `apply_*` methods, which return the
`down_ack` for the uplink.

Device traffic is `esp32-mqtt` only: MQTT messages come in via `on_message`,
commands and configs go out through the injected `publish` coroutine.
"""

import json
import logging
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import ValidationError

from mc_core import ids
from mc_core.commands import Actuator, CommandRejected, check_pump_run, expiry
from mc_core.contract import topics
from mc_core.contract.device import CmdAck, Command, ConfigDesired, Status, Telemetry
from mc_core.contract.gateway import Keys, Snapshot
from mc_core.rules import RuleContext, RuleSpec, evaluate, start_of_day

from . import broker_files
from .config import VERSION, GatewayConfig
from .store import Store

log = logging.getLogger(__name__)

Publish = Callable[[str, str, bool], Awaitable[None]]
ADAPTER = "esp32-mqtt"

# MQTT topic suffix → `kind` of a normalized device message (gateway_api.md §5.1).
DEVICE_KINDS = {"status": "status", "telemetry": "telemetry", "event": "event",
                "cmd/ack": "cmd_ack", "config/state": "config_state"}

# Command check failures reported with the closest rule skip reason (gateway_api.md §5.3).
_SKIP_FOR = {"busy": "pending_command", "slot_not_actuator": "no_pump", "safety_limit": "cooldown"}


class Agent:
    def __init__(self, cfg: GatewayConfig, store: Store, publish: Publish | None = None,
                 clock: Callable[[], float] = time.time):
        self.cfg = cfg
        self.store = store
        self._publish = publish
        self.clock = clock
        self.started = clock()
        self._snapshot: Snapshot | None = None
        self.on_report: Callable[[], None] | None = None  # uplink: new outbox entry
        raw = store.snapshot()
        if raw:
            self._snapshot = Snapshot.model_validate(raw)

    # --- plumbing -------------------------------------------------------------------

    @property
    def gateway_id(self) -> str | None:
        return self.store.get("gateway_id")

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snapshot

    def set_publisher(self, publish: Publish | None) -> None:
        self._publish = publish

    def now(self) -> int:
        return int(self.clock())

    def time_synced(self) -> bool:
        # A container can't query NTP state; trust the host and reject
        # obviously wrong clocks.
        return self.cfg.assume_time_synced and self.now() > 1_767_225_600  # 2026-01-01

    async def publish(self, topic: str, payload: dict | str, retain: bool = False) -> None:
        if self._publish is None:
            raise RuntimeError("not connected to the local broker")
        body = payload if isinstance(payload, str) else json.dumps(payload, separators=(",", ":"))
        await self._publish(topic, body, retain)

    def report(self, message: dict) -> int:
        """Append an up message to the outbox; returns its `seq`."""
        seq = self.store.outbox_append(message)
        if self.on_report is not None:
            self.on_report()
        return seq

    @staticmethod
    def _down_ack(msg_id: str | None, result: str = "applied", error: str | None = None) -> dict:
        ack = {"t": "down_ack", "id": msg_id, "result": result}
        if error:
            ack["error"] = error
        return ack

    # --- enrollment result -------------------------------------------------------------

    @property
    def credential(self) -> str | None:
        path = self.cfg.data_dir / "secrets" / "credential"
        return path.read_text().strip() if path.exists() else None

    def enrolled(self, gateway_id: str, credential: str) -> None:
        self.store.set("gateway_id", gateway_id)
        self.store_credential(credential)

    def store_credential(self, credential: str) -> None:
        secrets_dir = self.cfg.data_dir / "secrets"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        key_file = secrets_dir / "credential"
        tmp = secrets_dir / "credential.tmp"
        tmp.write_text(credential)
        tmp.chmod(0o600)
        tmp.replace(key_file)

    def reset(self) -> None:
        """Forget enrollment, keys and snapshot (removed in the app, or `reset`)."""
        broker_files.clear_psk(self.cfg.broker_dir)
        (self.cfg.data_dir / "secrets" / "credential").unlink(missing_ok=True)
        self.store.reset()
        self._snapshot = None

    # --- device traffic from the local broker (§5.1) -------------------------------------

    async def on_message(self, topic: str, payload: bytes, retained: bool = False) -> None:
        t = topics.parse(topic)
        # Retained messages are old state replayed by the broker on (re)subscribe.
        if t is None or not payload or retained:
            return
        try:
            if t.suffix in DEVICE_KINDS:
                body = json.loads(payload)
                self.report({"t": "device", "device": t.id, "adapter": ADAPTER,
                             "kind": DEVICE_KINDS[t.suffix], "received_at": self.now(),
                             "payload": body})
            match t.suffix:
                case "telemetry":
                    await self.on_telemetry(t.id, Telemetry.model_validate_json(payload))
                case "status":
                    msg = Status.model_validate_json(payload)
                    if msg.state == "sleeping" and msg.next_wake_s:
                        self.store.set(f"next_wake:{t.id}", self.now() + msg.next_wake_s)
                    self.store.set(f"last_seen:{t.id}", self.now())
                case "cmd":
                    self._track_command(t.id, Command.model_validate_json(payload))
                case "cmd/ack":
                    self.on_ack(CmdAck.model_validate_json(payload))
        except (ValidationError, ValueError) as e:
            log.warning("ignoring invalid %s: %s", topic, str(e)[:200])

    def _track_command(self, device: str, cmd: Command) -> None:
        """Commands published on the local broker, for busy/cooldown checks."""
        self.store.upsert_command(cmd.id, device, cmd.action, cmd.args, source="api",
                                  status="queued", created_at=self.now(), exp=cmd.exp)

    def on_ack(self, ack: CmdAck) -> None:
        status = {"running": "delivered", "done": "done", "cancelled": "cancelled"}.get(
            ack.status, "expired" if ack.reason == "expired" else "failed")
        finished = (ack.ts or self.now()) if ack.is_final else None
        self.store.set_command_status(ack.id, status, finished)

    async def on_telemetry(self, device: str, msg: Telemetry) -> None:
        last = self.store.get(f"seq:{device}")
        if last is not None and msg.seq <= int(last) and msg.health.wake != "power_on":
            return  # duplicate
        self.store.set(f"seq:{device}", msg.seq)
        ts = msg.ts or self.now()
        for r in msg.readings:
            self.store.add_reading(device, r.slot, msg.seq, ts, r.type, r.value, r.error)
        if self._snapshot is None:
            return
        for r in msg.readings:
            if r.type != "soil_moisture":
                continue
            for plant in self._snapshot.plants:
                if plant.sensor and plant.sensor.device == device and plant.sensor.slot == r.slot:
                    await self.run_rules(plant, r.value, r.error,
                                         {"device": device, "slot": r.slot, "seq": msg.seq,
                                          "value": r.value})

    # --- down messages (§5.2) -------------------------------------------------------------

    def apply_keys(self, msg: dict) -> dict:
        try:
            keys = Keys.model_validate(msg)
        except ValidationError as e:
            return self._down_ack(msg.get("id"), "rejected", str(e)[:200])
        if keys.rev > self.store.get_int("keys_rev"):
            broker_files.write_psk(self.cfg.broker_dir, [d.model_dump() for d in keys.devices])
            self.store.set("keys_rev", keys.rev)
            self.store.set("devices", json.dumps(sorted(d.id for d in keys.devices)))
            log.info("applied keys rev %s (%d devices)", keys.rev, len(keys.devices))
            self.publish_state()
        return self._down_ack(keys.id)  # older/equal rev: duplicate after reconnect

    def apply_snapshot(self, msg: dict) -> dict:
        try:
            snap = Snapshot.model_validate(msg)
        except ValidationError as e:
            return self._down_ack(msg.get("id"), "rejected", str(e)[:200])
        if snap.rev > self.store.get_int("snapshot_rev"):
            self.store.save_snapshot(snap.rev, snap.model_dump())
            self.store.set("snapshot_rev", snap.rev)
            self.store.set("snapshot_applied_at", self.now())
            self._snapshot = snap  # atomic swap of the rule set
            log.info("applied snapshot rev %s (%d plants, %d rules)", snap.rev, len(snap.plants),
                     len(snap.rules))
            self.publish_state()
        return self._down_ack(snap.id)

    async def apply_command(self, msg: dict) -> dict:
        """`command` from the API: same checks again, then to the device (§5.2)."""
        cmd = Command.model_validate(msg["command"])
        device = msg["device"]
        if cmd.action == "pump.run":
            actuator, _ = self._actuator(device, cmd.args.get("slot"))
            try:
                check_pump_run(cmd.args.get("seconds", 0), actuator, now=self.now(),
                               last_run_ended_at=self.store.last_run_end(device,
                                                                         cmd.args.get("slot")),
                               pending=self.store.pending_pump(device, cmd.args.get("slot")))
            except CommandRejected as e:
                return self._down_ack(msg.get("id"), "rejected", e.code)
        self._track_command(device, cmd)
        await self.publish(topics.device(device, "cmd"), cmd.model_dump(exclude_none=True))
        return self._down_ack(msg.get("id"))

    async def apply_config(self, msg: dict) -> dict:
        cfg = ConfigDesired.model_validate(msg["config"])
        await self.publish(topics.device(msg["device"], "config/desired"),
                           cfg.model_dump(exclude_none=True), retain=True)
        return self._down_ack(msg.get("id"))

    async def apply_device_removed(self, msg: dict) -> dict:
        for suffix in ("status", "config/desired", "config/state"):
            await self.publish(topics.device(msg["device"], suffix), "", retain=True)
        return self._down_ack(msg.get("id"))

    def publish_state(self) -> None:
        if not self.gateway_id:
            return
        depth, oldest = self.store.outbox_depth()
        free = shutil.disk_usage(self.cfg.data_dir).free // (1024 * 1024) \
            if Path(self.cfg.data_dir).exists() else None
        self.report({
            "t": "gateway_state", "version": VERSION, "arch": self.cfg.arch,
            "uptime_s": self.now() - int(self.started),
            "adapters": {a: {"ok": True} for a in self.cfg.adapters},
            "snapshot_rev": self.store.get_int("snapshot_rev"),
            "keys_rev": self.store.get_int("keys_rev"),
            "lan_host": self.cfg.lan_host, "lan_port": self.cfg.lan_port,
            "outbox_depth": depth, "outbox_oldest_s": self.now() - oldest if oldest else 0,
            "disk_free_mb": free, "time_synced": self.time_synced(),
        })

    # --- rules (§5.3) ---------------------------------------------------------------------------

    def _actuator(self, device_id: str, slot: int | None) -> tuple[Actuator | None, int]:
        for d in (self._snapshot.devices if self._snapshot else []):
            if d.id == device_id:
                for a in d.actuators:
                    if a.slot == slot:
                        return Actuator(slot, a.max_run_s, a.min_pause_s, d.max_run_s_hard), \
                            d.wake_interval_s
                return None, d.wake_interval_s
        return None, 600

    def _rule_counts(self, plant_id: str) -> tuple[int | None, int]:
        """max(snapshot rule_state, local history)."""
        snap = self._snapshot
        now = self.now()
        today = start_of_day(now, snap.timezone)
        last, count = self.store.rule_commands(plant_id, today)
        state = next((s for s in snap.rule_state if s.plant_id == plant_id), None)
        if state is not None:
            if state.last_rule_cmd_at and (last is None or state.last_rule_cmd_at > last):
                last = state.last_rule_cmd_at
            applied = self.store.get_int("snapshot_applied_at")
            if start_of_day(applied, snap.timezone) == today:  # counts are "today" of then
                count = max(count, state.rule_cmds_today)
        return last, count

    async def run_rules(self, plant, value: float | None, error: str | None,
                        reading: dict) -> None:
        now = self.now()
        for rule in self._snapshot.rules:
            if rule.plant_id != plant.id:
                continue
            pump = plant.pump
            last, count = self._rule_counts(plant.id)
            ctx = RuleContext(
                now=now, timezone=self._snapshot.timezone, has_pump=pump is not None,
                last_rule_cmd_at=last, rule_cmds_today=count,
                pending_command=pump is not None and self.store.pending_pump(pump.device,
                                                                             pump.slot))
            spec = RuleSpec(id=rule.id, plant_id=rule.plant_id, enabled=rule.enabled,
                            threshold=rule.threshold, water_s=rule.water_s,
                            cooldown_s=rule.cooldown_s, max_per_day=rule.max_per_day,
                            quiet_from=rule.quiet_from, quiet_to=rule.quiet_to)
            decision = evaluate(spec, value, error, ctx)
            if decision is None:
                continue
            verdict, skip_reason, command_id = decision.decision, decision.skip_reason, None
            if decision.water and not self.time_synced():
                verdict, skip_reason = "skip", "clock_not_synced"
            elif decision.water:
                try:
                    command_id = await self.create_pump_command(
                        pump.device, pump.slot, rule.water_s, source="rule", rule_id=rule.id,
                        plant_id=plant.id)
                except CommandRejected as e:
                    verdict, skip_reason = "skip", _SKIP_FOR.get(e.code, "pending_command")
            exec_id = ids.new_id()
            self.store.add_decision(exec_id, rule.id, plant.id, now, value, verdict, skip_reason,
                                    command_id)
            self.report({"t": "rule_exec", "id": exec_id, "rule_id": rule.id,
                         "plant_id": plant.id, "ts": now, "reading": reading,
                         "decision": verdict, "skip_reason": skip_reason,
                         "command_id": command_id})
            log.info("rule %s for plant %s: %s%s", rule.id, plant.id, verdict,
                     f" ({skip_reason})" if skip_reason else "")

    async def create_pump_command(self, device: str, slot: int, seconds: int, *, source: str,
                                  rule_id: str | None = None, plant_id: str | None = None) -> str:
        """Same checks as the API; `command_created` first, then to the device."""
        now = self.now()
        actuator, wake_interval = self._actuator(device, slot)
        check_pump_run(seconds, actuator, now=now,
                       last_run_ended_at=self.store.last_run_end(device, slot),
                       pending=self.store.pending_pump(device, slot))
        cmd_id = ids.new_id()
        exp = expiry(now, wake_interval)
        args = {"slot": slot, "seconds": seconds}
        self.store.upsert_command(cmd_id, device, "pump.run", args, source=source,
                                  status="queued", created_at=now, exp=exp, rule_id=rule_id,
                                  plant_id=plant_id)
        report = {"t": "command_created", "id": cmd_id, "device": device, "action": "pump.run",
                  "args": args, "exp": exp, "source": source, "created_at": now}
        if rule_id:
            report["rule_id"] = rule_id
        self.report(report)
        await self.publish(topics.device(device, "cmd"),
                           {"id": cmd_id, "action": "pump.run", "exp": exp, "args": args})
        return cmd_id

    async def water_plant(self, plant_id: str, seconds: int) -> str:
        """CLI: a local manual command, e.g. while the internet is down."""
        if self._snapshot is None:
            raise CommandRejected("no_snapshot", status=409)
        plant = next((p for p in self._snapshot.plants if p.id == plant_id), None)
        if plant is None or plant.pump is None:
            raise CommandRejected("slot_not_actuator", "plant has no pump")
        return await self.create_pump_command(plant.pump.device, plant.pump.slot, seconds,
                                              source="local", plant_id=plant.id)

    def housekeeping(self) -> None:
        self.store.expire_commands(self.now())
        self.store.cleanup(self.now())
