"""`mc-api seed-dev`: a ready household for local development.

Creates (idempotently) a household owned by the dev user, claims the newest
pending gateway enrollment for it if it has no gateway yet, one device keyed on
that gateway, a plant on slot 0/2 and a rule, and prints the pairing bundle for
`tools/fake_device.py` on stdout. Dev auth mode only.

It runs outside the API process, so it can't see whether the gateway is
connected: the keys and snapshot wait in the downlink and the API's sender
delivers them within a few seconds.
"""

import json
import sys

from sqlalchemy import select

from mc_core.contract.device import ConfigDesired

from .auth.verify import Principal
from .config import Settings
from .context import AppContext
from .crypto import KeyBox
from .db.models import Device, Household, Membership, Plant, User
from .db.session import create_all, make_engine, make_sessionmaker
from .notify.push import PushSender
from .realtime.bus import EventBus
from .services import devices, gateways, households, plants

DEV_CONFIG = ConfigDesired(rev=2, wake_interval_s=600, slots=[
    {"slot": 0, "module": "moisture_capacitive", "pin": 34, "cal": {"dry": 3000, "wet": 1200}},
    {"slot": 1, "module": "moisture_capacitive", "pin": 35, "cal": {"dry": 3050, "wet": 1180}},
    {"slot": 2, "module": "pump_relay", "pin": 25, "active_high": True, "max_run_s": 60,
     "min_pause_s": 60},
])


async def _bundle(uow, ctx: AppContext, device: Device, uid: str) -> dict:
    """The existing key (reusing it keeps a running simulator connected)."""
    if device.psk_enc is None or device.gateway != "gateway":
        bundle = await devices.rekey(uow, device, uid, require_online=False)
    else:
        gw = await gateways.get_gateway(uow, device.household_id)
        host, port = gateways.lan_address(gw)
        bundle = {"device_id": device.id,
                  "mqtt": {"host": host, "port": port, "psk": ctx.keys.decrypt(device.psk_enc)}}
    bundle["mqtt"]["host"] = bundle["mqtt"]["host"] or "localhost"  # state not reported yet
    return bundle


async def seed(uid: str) -> None:
    settings = Settings.from_env()
    if settings.auth_mode != "dev":
        raise SystemExit("seed-dev only runs with MC_AUTH_MODE=dev")
    engine = make_engine(settings.database_url)
    if settings.database_url.startswith("sqlite"):
        await create_all(engine)
    ctx = AppContext(settings=settings, engine=engine, sessionmaker=make_sessionmaker(engine),
                     keys=KeyBox(settings.key_encryption_key), bus=EventBus(), push=PushSender())
    user = Principal(uid, f"{uid}@dev.local", True, 0, "Dev User")
    async with ctx.uow() as uow:
        if await uow.s.get(User, uid) is None:
            uow.s.add(User(uid=uid, email=user.email, display_name=user.name))
            await uow.s.commit()
        existing = await uow.s.scalar(select(Household).join(
            Membership, Membership.household_id == Household.id).where(
            Membership.user_uid == uid, Household.name == "Dev home"))
        household = existing or await households.create(uow, user, "Dev home", "Europe/Berlin")

        if await gateways.get_gateway(uow, household.id) is None:
            enrollment = await gateways.pending_enrollment(uow)
            if enrollment is None:
                raise SystemExit("no gateway: start the gateway stack first so it enrolls, "
                                 "then run seed-dev again")
            gw = await gateways.claim_enrollment(uow, household, enrollment, uid)
            print(f"claimed gateway {gw.id}", file=sys.stderr)

        device = await uow.s.scalar(select(Device).where(
            Device.household_id == household.id, Device.deleted_at.is_(None)))
        if device is None:
            device, bundle = await devices.create_device(uow, household.id, "Sim device", uid,
                                                         require_online=False)
            bundle["mqtt"]["host"] = bundle["mqtt"]["host"] or "localhost"
        else:
            bundle = await _bundle(uow, ctx, device, uid)
        if device.desired_rev < DEV_CONFIG.rev:
            await devices.put_config(uow, device, device.desired_rev, DEV_CONFIG.wake_interval_s,
                                     [s.model_dump(exclude_none=True) for s in DEV_CONFIG.slots],
                                     uid)
        plant = await uow.s.scalar(select(Plant).where(Plant.household_id == household.id))
        if plant is None:
            plant = await plants.create(uow, household.id, {
                "name": "Basil", "sensor_device_id": device.id, "sensor_slot": 0,
                "pump_device_id": device.id, "pump_slot": 2}, uid)
            await plants.create_rule(uow, plant, {
                "threshold": 30, "water_s": 10, "cooldown_s": 3600, "max_per_day": 4}, uid)
            await plants.create(uow, household.id, {
                "name": "Monstera", "sensor_device_id": device.id, "sensor_slot": 1}, uid)

    await engine.dispose()
    # Bundle on stdout (redirect into a file), messages on stderr.
    print(json.dumps(bundle, indent=2))
    print(f"household {household.id} for uid '{uid}' (token 'dev:{uid}'), "
          f"device {bundle['device_id']} at {bundle['mqtt']['host']}:{bundle['mqtt']['port']}",
          file=sys.stderr)
