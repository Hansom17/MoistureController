"""Hub agent logic (Hub_Specs §5), independent of the MQTT connection.

`Agent.on_message` handles every message seen on the local broker; outgoing
messages go through the injected `publish` coroutine. That keeps the logic
testable without a broker.
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
from mc_core.contract.device import CmdAck, Command, Status, Telemetry
from mc_core.contract.hub import Keys, Snapshot
from mc_core.rules import RuleContext, RuleSpec, evaluate, start_of_day

from . import broker_files
from .config import VERSION, HubConfig
from .store import Store

log = logging.getLogger(__name__)

Publish = Callable[[str, str, bool], Awaitable[None]]

# Command check failures reported with the closest rule skip reason (hub.md §5.4).
_SKIP_FOR = {"busy": "pending_command", "slot_not_actuator": "no_pump", "safety_limit": "cooldown"}


class Agent:
    def __init__(self, cfg: HubConfig, store: Store, publish: Publish | None = None,
                 clock: Callable[[], float] = time.time):
        self.cfg = cfg
        self.store = store
        self._publish = publish
        self.clock = clock
        self.started = clock()
        self._snapshot: Snapshot | None = None
        raw = store.snapshot()
        if raw:
            self._snapshot = Snapshot.model_validate(raw)

    # --- plumbing -------------------------------------------------------------------

    @property
    def hub_id(self) -> str | None:
        return self.store.get("hub_id")

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snapshot

    def set_publisher(self, publish: Publish | None) -> None:
        self._publish = publish

    def now(self) -> int:
        return int(self.clock())

    def time_synced(self) -> bool:
        # A container can't query NTP state; trust the host (Hub_Specs §1) and
        # reject obviously wrong clocks.
        return self.cfg.assume_time_synced and self.now() > 1_767_225_600  # 2026-01-01

    async def publish(self, topic: str, payload: dict | str, retain: bool = False) -> None:
        if self._publish is None:
            raise RuntimeError("not connected")
        body = payload if isinstance(payload, str) else json.dumps(payload, separators=(",", ":"))
        await self._publish(topic, body, retain)

    async def up(self, suffix: str, payload: dict, retain: bool = False) -> None:
        await self.publish(topics.hub(self.hub_id, f"up/{suffix}"), payload, retain)

    # --- enrollment result -------------------------------------------------------------

    def enrolled(self, hub_id: str, host: str, port: int, psk: str) -> None:
        self.store.set("hub_id", hub_id)
        self.store.set("cloud_host", host)
        self.store.set("cloud_port", port)
        key_file = self.cfg.data_dir / "bridge.psk"
        key_file.write_text(psk)
        key_file.chmod(0o600)
        self.write_bridge([])

    def write_bridge(self, device_ids: list[str]) -> bool:
        host = self.cfg.cloud_mqtt_host_override or self.store.get("cloud_host")
        psk = (self.cfg.data_dir / "bridge.psk").read_text().strip()
        conf = broker_files.render_bridge(self.hub_id, host, int(self.store.get("cloud_port")),
                                          psk, device_ids)
        return broker_files.write_bridge(self.cfg.broker_dir, conf)

    def reset(self) -> None:
        """Forget everything (removed in the app, or `mc-hub reset`)."""
        broker_files.remove_bridge(self.cfg.broker_dir)
        (self.cfg.data_dir / "bridge.psk").unlink(missing_ok=True)
        self.store.reset()
        self._snapshot = None

    # --- dispatch -------------------------------------------------------------------------

    async def on_message(self, topic: str, payload: bytes) -> None:
        t = topics.parse(topic)
        if t is None:
            return
        try:
            if t.kind == "hub":
                if t.id != self.hub_id:
                    return
                if t.suffix == "down/keys":
                    await self.apply_keys(payload)
                elif t.suffix == "down/snapshot":
                    await self.apply_snapshot(payload)
                elif t.suffix == "up/bridge":
                    self.store.set("bridge_connected", 1 if payload.strip() == b"1" else 0)
                    if payload.strip() == b"1":
                        await self.publish_state()
                return
            if not payload:
                return
            match t.suffix:
                case "telemetry":
                    await self.on_telemetry(t.id, Telemetry.model_validate_json(payload))
                case "status":
                    msg = Status.model_validate_json(payload)
                    if msg.state == "sleeping" and msg.next_wake_s:
                        self.store.set(f"next_wake:{t.id}", self.now() + msg.next_wake_s)
                    self.store.set(f"last_seen:{t.id}", self.now())
                case "cmd":
                    self.on_cloud_command(t.id, Command.model_validate_json(payload))
                case "cmd/ack":
                    self.on_ack(CmdAck.model_validate_json(payload))
        except (ValidationError, ValueError) as e:
            log.warning("ignoring invalid %s: %s", topic, str(e)[:200])

    # --- down/keys, down/snapshot (§5.1) --------------------------------------------------------

    async def apply_keys(self, payload: bytes) -> None:
        if not payload:
            return
        try:
            keys = Keys.model_validate_json(payload)
        except ValidationError as e:
            await self._ack("down/keys", _rev(payload), "rejected", str(e)[:200])
            return
        if keys.rev > self.store.get_int("keys_rev"):
            broker_files.write_psk(self.cfg.broker_dir, [d.model_dump() for d in keys.devices])
            self.store.set("keys_rev", keys.rev)
            device_ids = sorted(d.id for d in keys.devices)
            self.store.set("devices", json.dumps(device_ids))
            log.info("applied keys rev %s (%d devices)", keys.rev, len(device_ids))
            await self._ack("down/keys", keys.rev, "applied")
            await self.publish_state()
            # Last: a changed device list restarts the broker (and this connection).
            if self.write_bridge(device_ids):
                log.info("bridge topics changed; the broker restarts")
        else:
            await self._ack("down/keys", keys.rev, "applied")  # duplicate after reconnect

    async def apply_snapshot(self, payload: bytes) -> None:
        if not payload:
            return
        try:
            snap = Snapshot.model_validate_json(payload)
        except ValidationError as e:
            await self._ack("down/snapshot", _rev(payload), "rejected", str(e)[:200])
            return
        if snap.rev > self.store.get_int("snapshot_rev"):
            self.store.save_snapshot(snap.rev, snap.model_dump())
            self.store.set("snapshot_rev", snap.rev)
            self.store.set("snapshot_applied_at", self.now())
            self._snapshot = snap  # atomic swap of the rule set
            log.info("applied snapshot rev %s (%d plants, %d rules)", snap.rev, len(snap.plants),
                     len(snap.rules))
            await self._ack("down/snapshot", snap.rev, "applied")
            await self.publish_state()
        else:
            await self._ack("down/snapshot", snap.rev, "applied")

    async def _ack(self, topic: str, rev: int, result: str, error: str | None = None) -> None:
        body = {"topic": topic, "rev": rev, "result": result}
        if error:
            body["error"] = error
        await self.up("ack", body)

    async def publish_state(self) -> None:
        if self._publish is None or not self.hub_id:
            return
        free = shutil.disk_usage(self.cfg.data_dir).free // (1024 * 1024) \
            if Path(self.cfg.data_dir).exists() else None
        await self.up("state", {
            "agent_version": VERSION, "arch": self.cfg.arch,
            "uptime_s": self.now() - int(self.started),
            "snapshot_rev": self.store.get_int("snapshot_rev"),
            "keys_rev": self.store.get_int("keys_rev"),
            "lan_host": self.cfg.lan_host, "lan_port": self.cfg.lan_port,
            "queue_depth": 0, "disk_free_mb": free, "time_synced": self.time_synced(),
        }, retain=True)

    # --- device traffic (§5.2) ------------------------------------------------------------------

    def on_cloud_command(self, device: str, cmd: Command) -> None:
        """A command from the cloud passing through: track it for busy/cooldown checks."""
        self.store.upsert_command(cmd.id, device, cmd.action, cmd.args, source="cloud",
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

    # --- rules (§5.3) ---------------------------------------------------------------------------

    def _actuator(self, device_id: str, slot: int) -> tuple[Actuator | None, int]:
        for d in self._snapshot.devices:
            if d.id == device_id:
                for a in d.actuators:
                    if a.slot == slot:
                        return Actuator(slot, a.max_run_s, a.min_pause_s, d.max_run_s_hard), \
                            d.wake_interval_s
                return None, d.wake_interval_s
        return None, 600

    def _rule_counts(self, plant_id: str) -> tuple[int | None, int]:
        """max(snapshot rule_state, local history) (§5.3.4)."""
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
        if not self.time_synced():
            log.warning("clock not synced: no rule commands")
            return
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
            if decision.water:
                try:
                    command_id = await self.create_pump_command(
                        pump.device, pump.slot, rule.water_s, source="rule", rule_id=rule.id,
                        plant_id=plant.id)
                except CommandRejected as e:
                    verdict, skip_reason = "skip", _SKIP_FOR.get(e.code, "pending_command")
            exec_id = ids.new_id()
            self.store.add_decision(exec_id, rule.id, plant.id, now, value, verdict, skip_reason,
                                    command_id)
            await self.up("rule_exec", {
                "id": exec_id, "rule_id": rule.id, "plant_id": plant.id, "ts": now,
                "reading": reading, "decision": verdict, "skip_reason": skip_reason,
                "command_id": command_id})
            log.info("rule %s for plant %s: %s%s", rule.id, plant.id, verdict,
                     f" ({skip_reason})" if skip_reason else "")

    async def create_pump_command(self, device: str, slot: int, seconds: int, *, source: str,
                                  rule_id: str | None = None, plant_id: str | None = None) -> str:
        """Same checks as the cloud; report via `up/cmd` first, then send locally (§5.3.2)."""
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
        report = {"id": cmd_id, "device": device, "action": "pump.run", "args": args,
                  "exp": exp, "source": source, "created_at": now}
        if rule_id:
            report["rule_id"] = rule_id
        await self.up("cmd", report)
        await self.publish(topics.device(device, "cmd"),
                           {"id": cmd_id, "action": "pump.run", "exp": exp, "args": args})
        return cmd_id

    async def water_plant(self, plant_id: str, seconds: int) -> str:
        """`mc-hub water` (§7): a local manual command, e.g. while the internet is down."""
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


def _rev(payload: bytes) -> int:
    try:
        return int(json.loads(payload).get("rev", 0))
    except (ValueError, AttributeError):
        return 0
