"""Hubs: enrollment, snapshot + keys, reports, removal (Server_Specs §9)."""

import hashlib
import hmac
import logging
from datetime import timedelta

from sqlalchemy import func, select

from mc_core import ids
from mc_core.contract import topics
from mc_core.contract.hub import (
    EnrollPollResponse,
    EnrollStartRequest,
    HubAck,
    HubCmd,
    HubState,
    RuleExec,
)

from ..context import Uow
from ..db.models import (
    CommandRow,
    Device,
    Household,
    Hub,
    HubEnrollment,
    Plant,
    Rule,
    RuleExecution,
)
from ..db.types import utcnow
from ..errors import Problem, not_found
from . import alerts
from .common import audit, get_hub, now_ts, to_dt, to_ts

log = logging.getLogger(__name__)

ENROLL_TTL_S = 900
POLL_INTERVAL_S = 5
HUB_OFFLINE_ALERT_AFTER = timedelta(minutes=15)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# --- snapshot + keys (§9.2) ------------------------------------------------------


async def _hub_devices(uow: Uow, household_id: str) -> list[Device]:
    return list(await uow.s.scalars(select(Device).where(
        Device.household_id == household_id, Device.deleted_at.is_(None),
        Device.gateway == "hub")))


async def publish_keys(uow: Uow, household_id: str) -> None:
    hub = await get_hub(uow, household_id)
    if hub is None:
        return
    household = await uow.s.get(Household, household_id)
    household.keys_rev += 1
    await uow.s.flush()
    devices = [{"id": d.id, "psk": uow.ctx.keys.decrypt(d.psk_enc)}
               for d in await _hub_devices(uow, household_id) if d.psk_enc]
    uow.publish(topics.hub(hub.id, "down/keys"),
                {"rev": household.keys_rev, "devices": devices}, retain=True)
    uow.emit(household_id, "hub", {"keys_rev": household.keys_rev})


async def build_snapshot(uow: Uow, household: Household) -> dict:
    from . import devices as devs  # circular: devices publishes snapshots too

    devices = await _hub_devices(uow, household.id)
    plants = list(await uow.s.scalars(select(Plant).where(
        Plant.household_id == household.id, Plant.archived_at.is_(None))))
    rules = list(await uow.s.scalars(select(Rule).where(Rule.household_id == household.id)))
    return {
        "rev": household.snapshot_rev,
        "household_id": household.id,
        "timezone": household.timezone,
        "settings": {"battery_low_mv": household.battery_low_mv},
        "devices": [
            {
                "id": d.id,
                "wake_interval_s": (d.reported_config or {}).get(
                    "wake_interval_s", d.wake_interval_s),
                "actuators": [
                    {"slot": s.slot, "max_run_s": s.max_run_s or 0,
                     "min_pause_s": s.min_pause_s or 0}
                    for s in devs.reported_slots(d) if s.is_actuator
                ],
                "limits": devs.reported_limits(d).model_dump(),
            }
            for d in devices
        ],
        "plants": [
            {
                "id": p.id,
                "sensor": ({"device": p.sensor_device_id, "slot": p.sensor_slot}
                           if p.sensor_device_id else None),
                "pump": ({"device": p.pump_device_id, "slot": p.pump_slot}
                         if p.pump_device_id else None),
            }
            for p in plants
        ],
        "rules": [
            {"id": r.id, "plant_id": r.plant_id, "enabled": r.enabled,
             "threshold": r.threshold, "water_s": r.water_s, "cooldown_s": r.cooldown_s,
             "max_per_day": r.max_per_day, "quiet_from": r.quiet_from, "quiet_to": r.quiet_to}
            for r in rules
        ],
        "rule_state": await _rule_state(uow, household, [p.id for p in plants]),
        "latest_agent_version": uow.ctx.settings.latest_hub_version,
    }


async def _rule_state(uow: Uow, household: Household, plant_ids: list[str]) -> list[dict]:
    from mc_core.rules import start_of_day

    today = to_dt(start_of_day(now_ts(), household.timezone))
    out = []
    for pid in plant_ids:
        last = await uow.s.scalar(select(func.max(CommandRow.created_at)).where(
            CommandRow.plant_id == pid, CommandRow.source == "rule"))
        count = await uow.s.scalar(select(func.count()).where(
            CommandRow.plant_id == pid, CommandRow.source == "rule",
            CommandRow.created_at >= today))
        if last is not None:
            out.append({"plant_id": pid, "last_rule_cmd_at": to_ts(last),
                        "rule_cmds_today": count or 0})
    return out


async def republish_snapshot(uow: Uow, household_id: str) -> None:
    """Call after any change to plants, rules, limits, timezone or settings."""
    hub = await get_hub(uow, household_id)
    if hub is None:
        return
    household = await uow.s.get(Household, household_id)
    household.snapshot_rev += 1
    await uow.s.flush()
    uow.publish(topics.hub(hub.id, "down/snapshot"), await build_snapshot(uow, household),
                retain=True)
    uow.emit(household_id, "hub", {"snapshot_rev": household.snapshot_rev})


# --- enrollment (§9.1, hub.md §3) ------------------------------------------------------


async def enroll_start(uow: Uow, req: EnrollStartRequest, ip: str | None) -> dict:
    code = ids.new_user_code()
    enrollment = HubEnrollment(
        secret_sha256=req.secret_sha256.lower(),
        user_code_hash=_sha256(ids.normalize_user_code(code)),
        expires_at=to_dt(now_ts() + ENROLL_TTL_S), ip=ip,
        agent_version=req.agent_version, arch=req.arch)
    uow.s.add(enrollment)
    await uow.commit()
    return {"enroll_id": enrollment.id, "user_code": code, "expires_in": ENROLL_TTL_S,
            "interval": POLL_INTERVAL_S,
            "claim_url": f"{uow.ctx.settings.app_url}/hub#u={code}"}


async def claim(uow: Uow, household: Household, user_code: str, uid: str) -> Hub:
    if await get_hub(uow, household.id) is not None:
        raise Problem(409, "hub_exists")
    enrollment = await uow.s.scalar(select(HubEnrollment).where(
        HubEnrollment.user_code_hash == _sha256(ids.normalize_user_code(user_code)),
        HubEnrollment.claimed_household_id.is_(None)))
    if enrollment is None or enrollment.expires_at < utcnow():
        raise Problem(422, "invalid_code")
    hub = Hub(id=ids.new_hub_id(), household_id=household.id,
              psk_enc=uow.ctx.keys.encrypt(ids.new_psk()), status="enrolling")
    uow.s.add(hub)
    enrollment.claimed_household_id = household.id
    enrollment.claimed_by = uid
    enrollment.hub_id = hub.id
    # Gateway change (§8.1): devices on the cloud broker must be re-paired to
    # the hub (rekey); their cloud keys are removed from the broker files.
    for d in await uow.s.scalars(select(Device).where(
            Device.household_id == household.id, Device.deleted_at.is_(None))):
        d.gateway = "none"
    uow.emit(household.id, "device", {})
    await uow.s.flush()
    # Waiting for the bridge as retained messages (§9.1).
    await publish_keys(uow, household.id)
    await republish_snapshot(uow, household.id)
    uow.broker_files_changed()
    audit(uow, household.id, uid, "hub.add", {"hub_id": hub.id})
    uow.emit(household.id, "hub", {"id": hub.id, "status": "enrolling"})
    await uow.commit()
    return hub


async def enroll_poll(uow: Uow, enroll_id: str, secret: str) -> EnrollPollResponse | None:
    """None = still pending (202). Raises 410 / 429 / 404."""
    enrollment = await uow.s.get(HubEnrollment, enroll_id)
    if enrollment is None:
        raise not_found("enrollment")
    if not hmac.compare_digest(_sha256_bytes_hex(secret), enrollment.secret_sha256):
        raise Problem(403, "invalid_secret")
    now = utcnow()
    if enrollment.consumed_at is not None or enrollment.expires_at < now:
        raise Problem(410, "enrollment_gone")
    if enrollment.last_poll_at and now - enrollment.last_poll_at < timedelta(
            seconds=POLL_INTERVAL_S - 1):
        raise Problem(429, "slow_down")
    enrollment.last_poll_at = now
    if enrollment.hub_id is None:
        await uow.commit()
        return None
    hub = await uow.s.get(Hub, enrollment.hub_id)
    household = await uow.s.get(Household, enrollment.claimed_household_id)
    enrollment.consumed_at = now
    hub.status = "connecting"
    s = uow.ctx.settings
    resp = EnrollPollResponse(
        hub_id=hub.id, household_name=household.name,
        mqtt={"host": s.broker_public_host, "port": s.broker_public_port,
              "identity": hub.id, "psk": uow.ctx.keys.decrypt(hub.psk_enc)})
    uow.emit(household.id, "hub", {"id": hub.id, "status": hub.status})
    await uow.commit()
    return resp


def _sha256_bytes_hex(secret_hex: str) -> str:
    """The hub sends the secret as hex; `secret_sha256` is over its bytes."""
    try:
        return hashlib.sha256(bytes.fromhex(secret_hex)).hexdigest()
    except ValueError:
        return ""


async def remove(uow: Uow, household_id: str, uid: str) -> None:
    hub = await get_hub(uow, household_id)
    if hub is None:
        raise not_found("hub")
    for suffix in ("down/snapshot", "down/keys", "up/state", "up/bridge"):
        uow.publish(topics.hub(hub.id, suffix), None, retain=True)
    for d in await uow.s.scalars(select(Device).where(
            Device.household_id == household_id, Device.deleted_at.is_(None))):
        d.gateway = "none"  # must be re-paired (§8.1 gateway change)
    await alerts.resolve_alert(uow, household_id, "hub_offline", hub.id)
    await uow.s.delete(hub)
    uow.broker_files_changed()
    audit(uow, household_id, uid, "hub.remove", {"hub_id": hub.id})
    uow.emit(household_id, "hub", {"removed": True})
    uow.emit(household_id, "device", {})
    await uow.commit()


# --- reports (§9.3) ----------------------------------------------------------------


async def handle_report(uow: Uow, hub_id: str, suffix: str, payload: bytes) -> None:
    hub = await uow.s.get(Hub, hub_id)
    if hub is None:
        log.info("report from unknown hub %s", hub_id)
        return
    hid = hub.household_id
    if suffix == "up/bridge":
        connected = payload.strip() == b"1"
        if connected != hub.bridge_connected:
            now = utcnow()
            if connected and hub.bridge_changed_at is not None:
                hub.last_outage_s = int((now - hub.bridge_changed_at).total_seconds())
            hub.bridge_connected, hub.bridge_changed_at = connected, now
            if connected:
                hub.status = "online"
                await alerts.resolve_alert(uow, hid, "hub_offline", hub.id)
            else:
                hub.status = "offline"
            uow.emit(hid, "hub", {"online": connected})
        await uow.commit()
        return

    import json

    from pydantic import ValidationError

    try:
        body = json.loads(payload)
    except ValueError:
        log.warning("invalid JSON from hub %s on %s", hub_id, suffix)
        return
    try:
        if suffix == "up/state":
            state = HubState.model_validate(body)
            hub.last_state, hub.last_state_at = state.model_dump(), utcnow()
            uow.emit(hid, "hub", {"state": True})
        elif suffix == "up/cmd":
            from .commands import record_hub_command

            await record_hub_command(uow, hid, HubCmd.model_validate(body))
        elif suffix == "up/rule_exec":
            msg = RuleExec.model_validate(body)
            if await uow.s.get(RuleExecution, msg.id) is None:
                uow.s.add(RuleExecution(
                    id=msg.id, household_id=hid, rule_id=msg.rule_id, plant_id=msg.plant_id,
                    ts=to_dt(msg.ts), reading_ref=msg.reading.model_dump(),
                    decision=msg.decision, skip_reason=msg.skip_reason,
                    command_id=msg.command_id, origin="hub"))
        elif suffix == "up/ack":
            await _apply_hub_ack(uow, hub, HubAck.model_validate(body))
        else:
            return
    except ValidationError:
        log.warning("invalid %s from hub %s", suffix, hub_id, exc_info=True)
        return
    await uow.commit()


async def _apply_hub_ack(uow: Uow, hub: Hub, ack: HubAck) -> None:
    household = await uow.s.get(Household, hub.household_id)
    if ack.result == "rejected":
        await alerts.open_alert(uow, household.id, "hub_sync_failed", "hub", hub.id, "Hub",
                                {"topic": ack.topic, "rev": ack.rev, "error": ack.error})
    elif ack.topic == "down/snapshot":
        hub.snapshot_rev_applied = max(hub.snapshot_rev_applied, ack.rev)
    else:
        hub.keys_rev_applied = max(hub.keys_rev_applied, ack.rev)
    if (hub.snapshot_rev_applied >= household.snapshot_rev
            and hub.keys_rev_applied >= household.keys_rev):
        await alerts.resolve_alert(uow, household.id, "hub_sync_failed", hub.id)
    uow.emit(household.id, "hub", {"in_sync": view_in_sync(hub, household)})


def view_in_sync(hub: Hub, household: Household) -> bool:
    return (hub.snapshot_rev_applied >= household.snapshot_rev
            and hub.keys_rev_applied >= household.keys_rev)


def view(hub: Hub, household: Household, latest_version: str) -> dict:
    state = hub.last_state or {}
    return {
        "id": hub.id,
        "status": hub.status,
        "online": hub.bridge_connected,
        "offline_since": None if hub.bridge_connected else hub.bridge_changed_at,
        "agent_version": state.get("agent_version"),
        "latest_agent_version": latest_version,
        "arch": state.get("arch"),
        "in_sync": view_in_sync(hub, household),
        "snapshot_rev": household.snapshot_rev,
        "snapshot_rev_applied": hub.snapshot_rev_applied,
        "keys_rev": household.keys_rev,
        "keys_rev_applied": hub.keys_rev_applied,
        "queue_depth": state.get("queue_depth"),
        "time_synced": state.get("time_synced"),
        "lan_host": hub.lan_host_override or state.get("lan_host"),
        "lan_host_override": hub.lan_host_override,
        "last_state_at": hub.last_state_at,
    }


async def raise_offline_alerts(uow: Uow) -> None:
    """Job: `hub_offline` after 15 min with the bridge down (§9.3)."""
    cutoff = utcnow() - HUB_OFFLINE_ALERT_AFTER
    for hub in await uow.s.scalars(select(Hub).where(
            Hub.bridge_connected.is_(False), Hub.bridge_changed_at.is_not(None),
            Hub.bridge_changed_at < cutoff)):
        await alerts.open_alert(uow, hub.household_id, "hub_offline", "hub", hub.id, "Hub")
    await uow.commit()
