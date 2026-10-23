"""Ingest of device messages (Gateway/specs.md section 8) and of Zigbee2MQTT bridge data."""
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ulid import ULID

from mc_hub.bus.transport import Transport
from mc_hub.clock import Clock
from mc_hub.db.models import Device, DeviceEvent, HealthReport, Plant, Reading, Setting
from mc_hub.zigbee import adapter
from mc_hub.zigbee.messages import CmdAck, ConfigState, Event, Status, Telemetry
from mc_hub.zigbee.topics import Z2MTopics

from . import alerts, battery, commands, config_sync, devices as devs, rules
from .join import Join
from .effects import Effects
from .views import alert_view, device_view

log = logging.getLogger("mc_hub.ingest")

MODEL = "MC-PLANT"
OFFLINE_STATES = ("joining", "ready", "late", "offline")


class Ingest:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], transport: Transport,
                 topics: Z2MTopics, clock: Clock) -> None:
        self.sessions, self.t, self.topics, self.clock = sessions, transport, topics, clock
        self.clock_synced = True
        self.join = Join()

    # ---- bridge ----------------------------------------------------------------------------

    async def reconcile(self, devices: list[dict]) -> Effects:
        """Match the Zigbee2MQTT device list with the devices table."""
        fx = Effects()
        now = int(self.clock.now())
        renames: list[tuple[str, str]] = []
        async with self.sessions() as s:
            known = {d.ieee: d for d in (await s.execute(select(Device))).scalars()}
            seen: set[str] = set()
            for e in devices:
                if e.get("type") == "Coordinator":
                    continue
                ieee = e["ieee_address"]
                seen.add(ieee)
                model_id = e.get("model_id") or (e.get("definition") or {}).get("model")
                state = e.get("interview_state", "")
                d = known.get(ieee)
                if d is None:
                    supported = model_id == MODEL
                    d = Device(id="dev-" + str(ULID()).lower()[-12:], ieee=ieee, model=model_id or e.get("model_id"),
                               name=e.get("friendly_name", ""), created_at=now, updated_at=now,
                               status=self._join_status(supported, state))
                    s.add(d)
                    known[ieee] = d
                    if self.join.joined(d.id):
                        fx.emit("join", dict(self.join.state)); fx.touch("join")
                    if supported:
                        await s.flush()
                        low, critical = await self.battery_thresholds(s)
                        config_sync.initial(d, now, s, low, critical)
                elif d.deleted_at is None and d.status in ("joining", "join_failed", "unsupported"):
                    new = self._join_status(model_id == MODEL, state)
                    if new != d.status:
                        d.status, d.updated_at = new, now
                    d.model = model_id or d.model
                if d.deleted_at is not None:
                    d.deleted_at, d.updated_at = None, now   # rejoined
                d.fw = e.get("software_build_id") or d.fw
                if e.get("friendly_name") != d.id:
                    renames.append((e.get("friendly_name", ieee), d.id))
                fx.emit("device", device_view(d))
            for ieee, d in known.items():
                if ieee not in seen and d.deleted_at is None:
                    await devs.soft_delete(s, fx, now, d)
            await s.commit()
        fx.touch("devices")
        for old, new in renames:
            await self.t.publish(self.topics.request("device/rename"),
                                 json.dumps({"from": old, "to": new}).encode())
        return fx

    @staticmethod
    def _join_status(supported: bool, interview_state: str) -> str:
        if not supported:
            return "unsupported"
        if interview_state == "FAILED":
            return "join_failed"
        if interview_state == "SUCCESSFUL":
            return "ready"
        return "joining"

    # ---- availability ----------------------------------------------------------------------

    async def availability(self, dev_id: str, state: str) -> Effects:
        fx = Effects()
        now = int(self.clock.now())
        async with self.sessions() as s:
            d = await s.get(Device, dev_id)
            if d is None or d.deleted_at is not None:
                return fx
            if state == "online":
                fx.kick(d.id)              # the first sign of life under the new name: send what is pending
            if state == "offline" and d.status in ("online", "late", "ready", "safe_mode"):
                d.status, d.updated_at = "offline", now
                a, new = await alerts.open_alert(s, now, "device_offline", "device", d.id, d.name or d.id)
                if new:
                    fx.emit("alert", alert_view(a)); fx.touch("alerts_open")
                    fx.notify(f"{d.name or d.id} is offline", [], "alert", alert_kind="device_offline")
            elif state == "online" and d.status == "offline":
                d.status, d.updated_at = "online", now
                await self._resolve(s, fx, now, "device_offline", d)
            else:
                return fx
            fx.emit("device", device_view(d)); fx.touch("devices")
            await s.commit()
        return fx

    # ---- device state ----------------------------------------------------------------------

    async def state(self, dev_id: str, payload: dict) -> Effects:
        fx = Effects()
        now = int(self.clock.now())
        msgs = adapter.normalize(payload)
        async with self.sessions() as s:
            d = await s.get(Device, dev_id)
            if d is None or d.deleted_at is not None:
                log.debug("drop message for unknown device %s", dev_id)
                return fx
            before = device_view(d)
            has_status = False
            order = {Status: 0, ConfigState: 1, CmdAck: 2, Event: 3, Telemetry: 4}
            for m in sorted(msgs, key=lambda m: order[type(m)]):
                if isinstance(m, Telemetry):
                    await self._telemetry(s, fx, d, m, now)
                elif isinstance(m, Status):
                    has_status = True
                    await self._status(s, fx, d, m, now)
                elif isinstance(m, Event):
                    await self._event(s, fx, d, m, now)
                elif isinstance(m, ConfigState):
                    await config_sync.apply_state(s, fx, now, d, m.cfg_rev, m.cfg_result, m.cfg_error)
                elif isinstance(m, CmdAck):
                    await commands.apply_ack(s, fx, now, d, m)
            if msgs and any(isinstance(m, Telemetry) and m.seq >= 0 for m in msgs):
                d.last_seen_at = now
                if not has_status and d.status in OFFLINE_STATES:
                    d.status = "online"
                if d.status == "online":
                    await self._resolve(s, fx, now, "device_offline", d)
            if msgs:
                fx.kick(d.id)
                fx.returned.add(d.id)
            d.updated_at = now if device_view(d) != before else d.updated_at
            after = device_view(d)
            if after != before:
                fx.emit("device", after); fx.touch("devices")
            await s.commit()
        return fx

    async def _telemetry(self, s: AsyncSession, fx: Effects, d: Device, m: Telemetry, now: int) -> None:
        if m.linkquality is not None:
            d.link_quality = m.linkquality
        mv = m.batt_mv if m.batt_mv is not None else m.voltage_mv
        if mv is not None:
            d.voltage_mv = mv
            low, critical = await self.battery_thresholds(s)
            d.batt_state = m.batt_state or battery.state_from(mv, low, critical)
            if m.seq >= 0 and d.batt_state == "absent":
                d.batt_hist = []
            await self._battery_alerts(s, fx, now, d)
        if m.seq < 0:
            return                                        # link-quality-only update
        same_boot = m.boot_id is None or m.boot_id == d.boot_id
        if same_boot and not adapter.is_newer_u16(m.seq, d.last_seq):
            return                                        # repeat of a reading we have
        d.last_seq, d.boot_id = m.seq, (m.boot_id if m.boot_id is not None else d.boot_id)
        if mv and d.batt_state != "absent":
            d.batt_hist = battery.push(d.batt_hist, mv)   # one point per new sample
        s.add(HealthReport(device_id=d.id, ts=now, voltage_mv=d.voltage_mv, link_quality=d.link_quality,
                           diagnostics=d.diagnostics))
        latest = dict(d.slots or {})
        for r in m.slots:
            latest[str(r.slot)] = {"type": r.type, "value": r.value, "raw": r.raw, "error": r.error, "ts": now}
            if r.type != "moisture":
                continue
            plant = (await s.execute(select(Plant).where(
                Plant.sensor_device_id == d.id, Plant.sensor_slot == r.slot,
                Plant.archived_at.is_(None)))).scalar_one_or_none()
            row = Reading(device_id=d.id, slot=r.slot, plant_id=plant.id if plant else None, type=r.type,
                          value=r.value, raw=r.raw, error=r.error, ts=now, seq=m.seq)
            s.add(row)
            await s.flush()
            fx.emit("reading", {"id": row.id, "device_id": d.id, "slot": r.slot, "plant_id": row.plant_id,
                                "value": r.value, "raw": r.raw, "error": r.error, "ts": now})
            fx.touch("plants")
            await rules.evaluate_reading(s, fx, now, row, self.clock_synced)
        d.slots = latest

    async def _status(self, s: AsyncSession, fx: Effects, d: Device, m: Status, now: int) -> None:
        if m.board:
            d.board = m.board
        d.diagnostics = m.diagnostics or d.diagnostics
        if m.status == "safe_mode":
            d.status, d.safe_reason = "safe_mode", m.safe_reason
            a, new = await alerts.open_alert(s, now, "device_safe_mode", "device", d.id, d.name or d.id,
                                             severity="critical", detail={"safe_reason": m.safe_reason})
            if new:
                fx.emit("alert", alert_view(a)); fx.touch("alerts_open")
                fx.notify(f"{d.name or d.id} is in safe mode ({m.safe_reason})", [], "alert", alert_kind="device_safe_mode")
        elif m.status == "operational":
            was_safe = d.status == "safe_mode"
            if d.status != "online":
                d.status = "online"
            d.safe_reason = None
            if was_safe:
                await self._resolve(s, fx, now, "device_safe_mode", d)
            await self._resolve(s, fx, now, "device_offline", d)
        # "interviewing": the module is still starting; keep the join status

    async def _event(self, s: AsyncSession, fx: Effects, d: Device, m: Event, now: int) -> None:
        if d.last_event_n is not None and m.n == d.last_event_n:
            return
        d.last_event_n = m.n
        s.add(DeviceEvent(device_id=d.id, ts=now, code=m.code, slot=m.slot, arg=m.arg))
        name = d.name or d.id
        if m.code == "low_battery":
            await self._raise(s, fx, now, "battery_low", "device", d.id, name)
        elif m.code == "battery_critical":
            await self._raise(s, fx, now, "battery_critical", "device", d.id, name, {"mv": m.arg}, "critical")
        elif m.code == "sensor_fault":
            await self._raise(s, fx, now, "sensor_error", "device", d.id, name, {"slot": m.slot})
        elif m.code == "sensor_ok":
            await self._resolve(s, fx, now, "sensor_error", d)
        elif m.code == "safety_stop":
            await self._raise(s, fx, now, "safety_stop", "device", d.id, name, {"slot": m.slot}, "critical")

    async def battery_thresholds(self, s: AsyncSession) -> tuple[int, int]:
        low = await s.get(Setting, "battery_low_mv")
        critical = await s.get(Setting, "battery_critical_mv")
        return (low.value if low else battery.DEFAULT_LOW_MV, critical.value if critical else battery.DEFAULT_CRITICAL_MV)

    async def _battery_alerts(self, s, fx: Effects, now: int, d: Device) -> None:
        state = d.batt_state
        if state in ("low", "critical"):
            await self._raise(s, fx, now, "battery_low", "device", d.id, d.name or d.id, {"mv": d.voltage_mv})
        if state == "critical":
            await self._raise(s, fx, now, "battery_critical", "device", d.id, d.name or d.id, {"mv": d.voltage_mv},
                              "critical")
        if state in ("ok", "absent"):
            await self._resolve(s, fx, now, "battery_low", d)
        if state != "critical":
            await self._resolve(s, fx, now, "battery_critical", d)

    async def _raise(self, s, fx: Effects, now, kind, st, sid, name, detail=None, severity="warning") -> None:
        a, new = await alerts.open_alert(s, now, kind, st, sid, name, severity, detail)
        if new:
            fx.emit("alert", alert_view(a)); fx.touch("alerts_open")
            fx.notify(f"{name}: {kind.replace('_', ' ')}", [], "alert", alert_kind=kind)

    async def _resolve(self, s, fx: Effects, now, kind, d: Device) -> None:
        for a in await alerts.resolve_alerts(s, now, kind, "device", d.id):
            fx.emit("alert", alert_view(a)); fx.touch("alerts_open")
