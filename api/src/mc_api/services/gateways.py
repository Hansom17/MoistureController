"""Gateways: enrollment, snapshot + keys, up messages, removal (Api_Specs §9).

Wire format: contracts/gateway_api.md.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm.attributes import set_committed_value

from mc_core import ids
from mc_core.contract import gateway as g
from mc_core.rules import start_of_day

from ..context import Uow
from ..db.models import (
    CommandRow,
    Device,
    Downlink,
    Gateway,
    GatewayEnrollment,
    Household,
    Plant,
    Rule,
    RuleExecution,
)
from ..db.types import utcnow
from ..errors import Problem, not_found
from . import alerts, commands, ingest
from .common import audit, now_ts, to_dt, to_ts

log = logging.getLogger(__name__)

ENROLL_TTL_S = 900
POLL_INTERVAL_S = 5
OFFLINE_ALERT_AFTER = timedelta(minutes=15)


def _sha256(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


async def get_gateway(uow: Uow, household_id: str) -> Gateway | None:
    return await uow.s.scalar(select(Gateway).where(
        Gateway.household_id == household_id, Gateway.status != "removed"))


def is_online(uow: Uow, gw: Gateway | None) -> bool:
    return gw is not None and uow.ctx.gateways.is_connected(gw.id)


def lan_address(gw: Gateway) -> tuple[str | None, int]:
    state = gw.last_state or {}
    return gw.lan_host_override or state.get("lan_host"), int(state.get("lan_port") or 8883)


# --- down messages ------------------------------------------------------------------


async def send_down(uow: Uow, household_id: str, type_: str, body: dict) -> Downlink | None:
    """Queue for the household's gateway; None if it has none."""
    gw = await get_gateway(uow, household_id)
    if gw is None:
        return None
    return uow.send_down(gw.id, type_, body)


async def _supersede(uow: Uow, gateway_id: str, type_: str) -> None:
    """Only the newest snapshot / key set matters (Api_Specs §9.3)."""
    await uow.s.execute(update(Downlink).where(
        Downlink.gateway_id == gateway_id, Downlink.type == type_,
        Downlink.acked_at.is_(None)).values(acked_at=utcnow(), result="superseded"))


async def _bump(uow: Uow, household: Household, column: str) -> None:
    """Atomic increment: concurrent changes must never publish the same rev.

    The row lock also serializes them, so the set built afterwards includes
    what the other transaction committed.
    """
    await uow.s.flush()
    col = getattr(Household, column)
    rev = await uow.s.scalar(update(Household).where(Household.id == household.id)
                             .values({col: col + 1}).returning(col)
                             .execution_options(synchronize_session=False))
    set_committed_value(household, column, rev)


async def publish_keys(uow: Uow, household_id: str, bump: bool = True) -> None:
    gw = await get_gateway(uow, household_id)
    if gw is None:
        return
    household = await uow.s.get(Household, household_id)
    if bump:
        await _bump(uow, household, "keys_rev")
    await _supersede(uow, gw.id, "keys")
    devices = await uow.s.scalars(select(Device).where(
        Device.household_id == household_id, Device.deleted_at.is_(None),
        Device.gateway == "gateway", Device.psk_enc.is_not(None)))
    uow.send_down(gw.id, "keys", {"rev": household.keys_rev, "devices": [
        {"id": d.id, "adapter": d.adapter, "psk": uow.ctx.keys.decrypt(d.psk_enc)}
        for d in devices]})
    uow.emit(household_id, "gateway", {"keys_rev": household.keys_rev})


async def republish_snapshot(uow: Uow, household_id: str, bump: bool = True) -> None:
    """Call after any change to plants, rules, reported limits, timezone or settings."""
    gw = await get_gateway(uow, household_id)
    if gw is None:
        return
    household = await uow.s.get(Household, household_id)
    if bump:
        await _bump(uow, household, "snapshot_rev")
    await uow.s.flush()
    await _supersede(uow, gw.id, "snapshot")
    uow.send_down(gw.id, "snapshot", await build_snapshot(uow, household))
    uow.emit(household_id, "gateway", {"snapshot_rev": household.snapshot_rev})


async def build_snapshot(uow: Uow, household: Household) -> dict:
    from . import devices as devs  # circular: devices sends keys/snapshots too

    devices = list(await uow.s.scalars(select(Device).where(
        Device.household_id == household.id, Device.deleted_at.is_(None),
        Device.gateway == "gateway")))
    plants = list(await uow.s.scalars(select(Plant).where(
        Plant.household_id == household.id, Plant.archived_at.is_(None))))
    rules = list(await uow.s.scalars(select(Rule).where(Rule.household_id == household.id)))
    return {
        "rev": household.snapshot_rev,
        "household_id": household.id,
        "timezone": household.timezone,
        "settings": {"battery_low_mv": household.battery_low_mv},
        "devices": [
            {"id": d.id, "adapter": d.adapter,
             "wake_interval_s": (d.reported_config or {}).get("wake_interval_s",
                                                              d.wake_interval_s),
             "actuators": [{"slot": s.slot, "max_run_s": s.max_run_s or 0,
                            "min_pause_s": s.min_pause_s or 0}
                           for s in devs.reported_slots(d) if s.is_actuator],
             "limits": devs.reported_limits(d).model_dump()}
            for d in devices
        ],
        "plants": [
            {"id": p.id,
             "sensor": ({"device": p.sensor_device_id, "slot": p.sensor_slot}
                        if p.sensor_device_id else None),
             "pump": ({"device": p.pump_device_id, "slot": p.pump_slot}
                      if p.pump_device_id else None)}
            for p in plants
        ],
        "rules": [
            {"id": r.id, "plant_id": r.plant_id, "enabled": r.enabled, "threshold": r.threshold,
             "water_s": r.water_s, "cooldown_s": r.cooldown_s, "max_per_day": r.max_per_day,
             "quiet_from": r.quiet_from, "quiet_to": r.quiet_to}
            for r in rules
        ],
        "rule_state": await _rule_state(uow, household, [p.id for p in plants]),
        "latest_gateway_version": uow.ctx.settings.latest_gateway_version,
    }


async def _rule_state(uow: Uow, household: Household, plant_ids: list[str]) -> list[dict]:
    today = to_dt(start_of_day(now_ts(), household.timezone))
    out = []
    for pid in plant_ids:
        last = await uow.s.scalar(select(func.max(CommandRow.created_at)).where(
            CommandRow.plant_id == pid, CommandRow.source == "rule"))
        if last is None:
            continue
        count = await uow.s.scalar(select(func.count()).where(
            CommandRow.plant_id == pid, CommandRow.source == "rule",
            CommandRow.created_at >= today))
        out.append({"plant_id": pid, "last_rule_cmd_at": to_ts(last),
                    "rule_cmds_today": count or 0})
    return out


# --- enrollment (gateway_api.md §3) --------------------------------------------------------


async def enroll_start(uow: Uow, req: g.EnrollStartRequest, ip: str | None) -> dict:
    code = ids.new_user_code()
    enrollment = GatewayEnrollment(
        secret_sha256=req.secret_sha256.lower(),
        user_code_hash=_sha256(ids.normalize_user_code(code)),
        expires_at=to_dt(now_ts() + ENROLL_TTL_S), ip=ip,
        version=req.version, arch=req.arch, adapters=req.adapters)
    uow.s.add(enrollment)
    await uow.commit()
    return {"enroll_id": enrollment.id, "user_code": code, "expires_in": ENROLL_TTL_S,
            "interval": POLL_INTERVAL_S,
            "claim_url": f"{uow.ctx.settings.app_url}/gateway#u={code}"}


async def claim(uow: Uow, household: Household, user_code: str, uid: str) -> Gateway:
    enrollment = await uow.s.scalar(select(GatewayEnrollment).where(
        GatewayEnrollment.user_code_hash == _sha256(ids.normalize_user_code(user_code)),
        GatewayEnrollment.claimed_household_id.is_(None)))
    if enrollment is None or enrollment.expires_at < utcnow():
        raise Problem(422, "invalid_code")
    return await claim_enrollment(uow, household, enrollment, uid)


async def pending_enrollment(uow: Uow) -> GatewayEnrollment | None:
    """Newest unclaimed, unexpired enrollment (dev seeding only)."""
    return await uow.s.scalar(select(GatewayEnrollment).where(
        GatewayEnrollment.claimed_household_id.is_(None),
        GatewayEnrollment.expires_at > utcnow()).order_by(GatewayEnrollment.created_at.desc()))


async def claim_enrollment(uow: Uow, household: Household, enrollment: GatewayEnrollment,
                           uid: str) -> Gateway:
    if await get_gateway(uow, household.id) is not None:
        raise Problem(409, "gateway_exists", "remove the current gateway first")
    credential = secrets.token_urlsafe(32)
    gw = Gateway(id=ids.new_gateway_id(), household_id=household.id,
                 credential_hash=_sha256(credential), status="enrolling",
                 version=enrollment.version, adapters=enrollment.adapters)
    uow.s.add(gw)
    enrollment.claimed_household_id = household.id
    enrollment.claimed_by = uid
    enrollment.gateway_id = gw.id
    enrollment.credential_enc = uow.ctx.keys.encrypt(credential)
    # Existing devices must be re-paired to this gateway (Api_Specs §8.1).
    for d in await uow.s.scalars(select(Device).where(
            Device.household_id == household.id, Device.deleted_at.is_(None))):
        d.gateway = "none"
    await uow.s.flush()
    # Waiting in the downlink for the first connection.
    await publish_keys(uow, household.id)
    await republish_snapshot(uow, household.id)
    audit(uow, household.id, uid, "gateway.add", {"gateway_id": gw.id})
    uow.emit(household.id, "gateway", {"id": gw.id, "status": gw.status})
    uow.emit(household.id, "device", {})
    await uow.commit()
    return gw


async def enroll_poll(uow: Uow, enroll_id: str, secret_hex: str) -> g.EnrollPollResponse | None:
    """None = still pending (202). Raises 403 / 404 / 410 / 429."""
    enrollment = await uow.s.get(GatewayEnrollment, enroll_id)
    if enrollment is None:
        raise not_found("enrollment")
    try:
        secret_hash = _sha256(bytes.fromhex(secret_hex))
    except ValueError:
        secret_hash = ""
    if not hmac.compare_digest(secret_hash, enrollment.secret_sha256):
        raise Problem(403, "invalid_secret")
    now = utcnow()
    if enrollment.consumed_at is not None or enrollment.expires_at < now:
        raise Problem(410, "enrollment_gone")
    if enrollment.last_poll_at and now - enrollment.last_poll_at < timedelta(
            seconds=POLL_INTERVAL_S - 1):
        raise Problem(429, "slow_down")
    enrollment.last_poll_at = now
    if enrollment.gateway_id is None:
        await uow.commit()
        return None
    household = await uow.s.get(Household, enrollment.claimed_household_id)
    credential = uow.ctx.keys.decrypt(enrollment.credential_enc)
    enrollment.consumed_at, enrollment.credential_enc = now, None
    s = uow.ctx.settings
    ws_url = s.public_api_url.replace("https://", "wss://").replace("http://", "ws://")
    resp = g.EnrollPollResponse(gateway_id=enrollment.gateway_id, household_name=household.name,
                                credential=credential, ws_url=f"{ws_url}/gateway/v1/connect")
    await uow.commit()
    return resp


async def remove(uow: Uow, household_id: str, uid: str) -> None:
    gw = await get_gateway(uow, household_id)
    if gw is None:
        raise not_found("gateway")
    uow.send_down(gw.id, "removed", {})
    gw.status = "removed"
    for d in await uow.s.scalars(select(Device).where(
            Device.household_id == household_id, Device.deleted_at.is_(None))):
        d.gateway = "none"  # must be re-paired to a new gateway
    await alerts.resolve_alert(uow, household_id, "gateway_offline", gw.id)
    audit(uow, household_id, uid, "gateway.remove", {"gateway_id": gw.id})
    uow.emit(household_id, "gateway", {"removed": True})
    uow.emit(household_id, "device", {})
    await uow.commit()
    # The live session sends `removed` and then closes with 4001.


# --- authentication and sessions (Api_Specs §5.5, §9.2) --------------------------------------


async def authenticate(uow: Uow, header: str) -> Gateway | None:
    scheme, _, value = header.partition(" ")
    gateway_id, _, credential = value.partition(":")
    if scheme != "Gateway" or not gateway_id or not credential:
        return None
    gw = await uow.s.get(Gateway, gateway_id)
    if gw is None or gw.status == "removed":
        return None
    if not hmac.compare_digest(_sha256(credential), gw.credential_hash):
        return None
    return gw


async def connected(uow: Uow, gw: Gateway, hello: g.Hello) -> None:
    now = utcnow()
    if gw.disconnected_at is not None:
        gw.last_outage_s = int((now - gw.disconnected_at).total_seconds())
    gw.status, gw.connected_at = "online", now
    gw.version, gw.adapters = hello.version, hello.adapters
    household = await uow.s.get(Household, gw.household_id)
    await alerts.resolve_alert(uow, gw.household_id, "gateway_offline", gw.id)
    # A gateway that is behind (e.g. restored from a backup) gets the current sets.
    pending = set((await uow.s.scalars(select(Downlink.type).where(
        Downlink.gateway_id == gw.id, Downlink.acked_at.is_(None)))).all())
    if hello.snapshot_rev < household.snapshot_rev and "snapshot" not in pending:
        await republish_snapshot(uow, gw.household_id, bump=False)
    if hello.keys_rev < household.keys_rev and "keys" not in pending:
        await publish_keys(uow, gw.household_id, bump=False)
    uow.emit(gw.household_id, "gateway", {"online": True})
    await uow.commit()


async def disconnected(uow: Uow, gateway_id: str) -> None:
    gw = await uow.s.get(Gateway, gateway_id)
    if gw is None or gw.status == "removed":
        return
    gw.status, gw.disconnected_at = "offline", utcnow()
    uow.emit(gw.household_id, "gateway", {"online": False})
    await uow.commit()


# --- up messages (Api_Specs §9.5) ---------------------------------------------------------------


async def process_up(uow: Uow, gw: Gateway, msg: dict) -> None:
    """One sequenced up message; the caller has checked `seq` > last_up_seq."""
    gw_id, hid = gw.id, gw.household_id  # stay valid after a rollback
    t = msg.get("t")
    try:
        match t:
            case "device":
                outage = gw.last_outage_s or 0
                await ingest.handle_device(uow, hid, g.DeviceMessage.model_validate(msg), outage,
                                           commit=False)
            case "command_created":
                await commands.record_gateway_command(uow, hid,
                                                      g.CommandCreated.model_validate(msg))
            case "rule_exec":
                await _rule_exec(uow, hid, g.RuleExec.model_validate(msg))
            case "gateway_state":
                state = g.GatewayState.model_validate(msg)
                gw.last_state, gw.last_state_at = state.model_dump(), utcnow()
                gw.version = state.version
                uow.emit(hid, "gateway", {"state": True})
            case "gateway_event":
                event = g.GatewayEvent.model_validate(msg)
                if event.kind == "buffer_overflow":
                    await alerts.open_alert(uow, hid, "gateway_buffer_overflow", "gateway",
                                            gw.id, "Gateway", {"detail": event.detail})
            case _:
                log.info("gateway %s: unknown up message %r", gw_id, t)
    except ValidationError as e:
        await uow.rollback()
        log.warning("gateway %s: invalid %s: %s", gw_id, t, str(e)[:200])
    # Every message moves the ack forward, even an invalid one (gateway_api.md §4.2).
    fresh = await uow.s.get(Gateway, gw_id)
    fresh.last_up_seq = max(fresh.last_up_seq, int(msg["seq"]))
    await uow.commit()


async def _rule_exec(uow: Uow, household_id: str, msg: g.RuleExec) -> None:
    if await uow.s.get(RuleExecution, msg.id) is not None:
        return
    uow.s.add(RuleExecution(
        id=msg.id, household_id=household_id, rule_id=msg.rule_id, plant_id=msg.plant_id,
        ts=to_dt(msg.ts), reading_ref=msg.reading.model_dump(), decision=msg.decision,
        skip_reason=msg.skip_reason, command_id=msg.command_id, origin="gateway"))
    uow.emit(household_id, "rule", {"plant_id": msg.plant_id, "rule_id": msg.rule_id})


async def process_down_ack(uow: Uow, gw: Gateway, ack: g.DownAck) -> None:
    row = await uow.s.scalar(select(Downlink).where(
        Downlink.id == ack.id, Downlink.gateway_id == gw.id))
    if row is None or row.result == "superseded":
        return
    row.acked_at, row.result, row.error = utcnow(), ack.result, ack.error
    household = await uow.s.get(Household, gw.household_id)
    if row.type in ("snapshot", "keys"):
        if ack.result == "rejected":
            await alerts.open_alert(uow, household.id, "gateway_sync_failed", "gateway", gw.id,
                                    "Gateway", {"type": row.type, "error": ack.error})
        elif row.type == "snapshot":
            gw.snapshot_rev_applied = max(gw.snapshot_rev_applied, row.body["rev"])
        else:
            gw.keys_rev_applied = max(gw.keys_rev_applied, row.body["rev"])
        if in_sync(gw, household):
            await alerts.resolve_alert(uow, household.id, "gateway_sync_failed", gw.id)
        uow.emit(household.id, "gateway", {"in_sync": in_sync(gw, household)})
    elif row.type == "command":
        await commands.gateway_ack(uow, row.body["command"]["id"], ack.result, ack.error)
    await uow.commit()


# --- views and jobs -------------------------------------------------------------------------------


def in_sync(gw: Gateway, household: Household) -> bool:
    return (gw.snapshot_rev_applied >= household.snapshot_rev
            and gw.keys_rev_applied >= household.keys_rev)


def view(uow: Uow, gw: Gateway, household: Household) -> dict:
    state = gw.last_state or {}
    online = is_online(uow, gw)
    host, port = lan_address(gw)
    return {
        "id": gw.id, "status": gw.status if gw.status != "online" or online else "offline",
        "online": online, "offline_since": None if online else gw.disconnected_at,
        "version": gw.version, "latest_version": uow.ctx.settings.latest_gateway_version,
        "arch": state.get("arch"), "adapters": gw.adapters or [],
        "in_sync": in_sync(gw, household),
        "snapshot_rev": household.snapshot_rev, "snapshot_rev_applied": gw.snapshot_rev_applied,
        "keys_rev": household.keys_rev, "keys_rev_applied": gw.keys_rev_applied,
        "outbox_depth": state.get("outbox_depth"), "time_synced": state.get("time_synced"),
        "lan_host": host, "lan_port": port, "lan_host_override": gw.lan_host_override,
        "last_state_at": gw.last_state_at,
    }


async def offline_households(uow: Uow) -> set[str]:
    """Households whose gateway is enrolled but not connected right now."""
    rows = await uow.s.execute(select(Gateway.id, Gateway.household_id).where(
        Gateway.status.in_(("online", "offline"))))
    return {hid for gid, hid in rows if not uow.ctx.gateways.is_connected(gid)}


async def raise_offline_alerts(uow: Uow) -> None:
    """Job: `gateway_offline` after 15 min without a connection."""
    cutoff = utcnow() - OFFLINE_ALERT_AFTER
    for gw in await uow.s.scalars(select(Gateway).where(
            Gateway.status == "offline", Gateway.disconnected_at < cutoff)):
        if not uow.ctx.gateways.is_connected(gw.id):
            await alerts.open_alert(uow, gw.household_id, "gateway_offline", "gateway", gw.id,
                                    "Gateway")
    await uow.commit()
