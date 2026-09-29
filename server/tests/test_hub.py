"""Cloud side of hubs: enrollment, bridge, snapshot/keys, reports (§9)."""

import hashlib
import json
import secrets
import time

from mc_core.ids import new_id
from mc_server.services import ingest

from .conftest import FakeDevice, outbox


async def hub_report(ctx, hub_id: str, suffix: str, payload):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    async with ctx.uow() as uow:
        await ingest.handle(uow, f"mc/hub/v1/{hub_id}/{suffix}", body)


async def enroll(client, owner, household_id: str) -> dict:
    secret = secrets.token_bytes(32)
    start = (await client.post("/hub/v1/enroll/start", json={
        "secret_sha256": hashlib.sha256(secret).hexdigest(), "agent_version": "0.1.0",
        "arch": "arm64"})).json()
    assert len(start["user_code"]) == 9 and start["claim_url"].endswith(start["user_code"])

    pending = await client.post("/hub/v1/enroll/poll",
                                json={"enroll_id": start["enroll_id"], "secret": secret.hex()})
    assert pending.status_code == 202

    hub = await owner.post(f"/households/{household_id}/hub",
                           {"user_code": start["user_code"].lower()}, expect=201)
    assert hub["status"] == "enrolling"

    wrong = await client.post("/hub/v1/enroll/poll",
                              json={"enroll_id": start["enroll_id"], "secret": "00" * 32})
    assert wrong.status_code == 403

    # Respect the poll interval.
    from mc_server.db.models import HubEnrollment

    ctx = client._transport.app.state.ctx
    async with ctx.sessionmaker() as s:
        e = await s.get(HubEnrollment, start["enroll_id"])
        e.last_poll_at = None
        await s.commit()
    creds = (await client.post("/hub/v1/enroll/poll", json={
        "enroll_id": start["enroll_id"], "secret": secret.hex()})).json()
    assert creds["hub_id"] == hub["id"] and creds["mqtt"]["identity"] == hub["id"]
    gone = await client.post("/hub/v1/enroll/poll",
                             json={"enroll_id": start["enroll_id"], "secret": secret.hex()})
    assert gone.status_code == 410
    return creds


async def online_hub(client, owner, ctx, household_id: str) -> str:
    creds = await enroll(client, owner, household_id)
    hub_id = creds["hub_id"]
    await hub_report(ctx, hub_id, "up/bridge", b"1")
    await hub_report(ctx, hub_id, "up/state", {
        "agent_version": "0.1.0", "arch": "arm64", "uptime_s": 10, "snapshot_rev": 0,
        "keys_rev": 0, "lan_host": "192.168.1.20", "lan_port": 8883, "queue_depth": 0,
        "time_synced": True})
    return hub_id


async def test_enrollment_publishes_keys_and_snapshot(household, owner, client, ctx):
    hub_id = await online_hub(client, owner, ctx, household["id"])
    topics = {r.topic: r for r in await outbox(ctx)}
    assert topics[f"mc/hub/v1/{hub_id}/down/keys"].retain
    snapshot = json.loads(topics[f"mc/hub/v1/{hub_id}/down/snapshot"].payload)
    assert snapshot["household_id"] == household["id"] and snapshot["timezone"]
    hub = await owner.get(f"/households/{household['id']}/hub")
    assert hub["online"] and hub["lan_host"] == "192.168.1.20" and not hub["in_sync"]
    hh = await owner.get("/me/households")
    assert hh[0]["hub"]["online"] is True


async def test_device_in_hub_household(household, owner, client, ctx):
    h = household["id"]
    hub_id = await online_hub(client, owner, ctx, h)
    created = await owner.post(f"/households/{h}/devices", {"name": "Balcony"}, expect=201)
    assert created["bundle"]["mqtt"]["host"] == "192.168.1.20"
    assert created["device"]["gateway"] == "hub"
    keys = [json.loads(r.payload) for r in await outbox(ctx, "down/keys")]
    assert keys[-1]["devices"] == [{"id": created["device"]["id"],
                                    "psk": created["bundle"]["mqtt"]["psk"]}]

    # The cloud broker ACL lets the hub reach exactly this device.
    await ctx.broker_files_changed.__self__.regenerate()
    acl = (ctx.settings.broker_files_dir / "acl").read_text()
    assert f"user {hub_id}" in acl
    assert f"topic write mc/v1/{created['device']['id']}/telemetry" in acl
    psk = (ctx.settings.broker_files_dir / "psk").read_text()
    assert created["device"]["id"] not in psk  # the hub holds that key, not the cloud

    # Hub acks → in sync.
    household_rev = json.loads((await outbox(ctx, "down/snapshot"))[-1].payload)["rev"]
    await hub_report(ctx, hub_id, "up/ack", {"topic": "down/snapshot", "rev": household_rev,
                                             "result": "applied"})
    await hub_report(ctx, hub_id, "up/ack", {"topic": "down/keys", "rev": keys[-1]["rev"],
                                             "result": "applied"})
    assert (await owner.get(f"/households/{h}/hub"))["in_sync"]


async def test_hub_offline_blocks_new_devices_and_warns_on_water(household, owner, client, ctx):
    h = household["id"]
    hub_id = await online_hub(client, owner, ctx, h)
    created = await owner.post(f"/households/{h}/devices", {"name": "Bed"}, expect=201)
    dev = FakeDevice(ctx, created["device"]["id"])
    await dev.report_config()
    plant = await owner.post(f"/households/{h}/plants", {
        "name": "Roses", "sensor_device_id": dev.id, "sensor_slot": 0,
        "pump_device_id": dev.id, "pump_slot": 2}, expect=201)

    await hub_report(ctx, hub_id, "up/bridge", b"0")
    r = await owner.req("POST", f"/households/{h}/devices", json={"name": "X"})
    assert r.status_code == 409 and r.json()["type"] == "hub_offline"
    res = await owner.post(f"/households/{h}/plants/{plant['id']}/water", {"seconds": 5},
                           expect=202)
    assert res["warnings"] == ["hub_offline"]


async def test_hub_rule_command_and_early_ack(household, owner, client, ctx):
    h = household["id"]
    hub_id = await online_hub(client, owner, ctx, h)
    created = await owner.post(f"/households/{h}/devices", {"name": "Bed"}, expect=201)
    dev = FakeDevice(ctx, created["device"]["id"])
    await dev.report_config()
    plant = await owner.post(f"/households/{h}/plants", {
        "name": "Roses", "sensor_device_id": dev.id, "sensor_slot": 0,
        "pump_device_id": dev.id, "pump_slot": 2}, expect=201)
    rule = await owner.post(f"/households/{h}/plants/{plant['id']}/rules",
                            {"threshold": 30, "water_s": 10}, expect=201)

    # Dry reading: the cloud does NOT decide for hub households.
    await dev.wake(moisture=10)
    assert await owner.get(f"/households/{h}/commands") == []

    cmd_id, now = new_id(), int(time.time())
    # The device's ack overtakes the hub's up/cmd report.
    await dev.ack(cmd_id, "done", ts=now)
    await hub_report(ctx, hub_id, "up/cmd", {
        "id": cmd_id, "device": dev.id, "action": "pump.run", "args": {"slot": 2, "seconds": 10},
        "exp": now + 900, "source": "rule", "rule_id": rule["id"], "created_at": now})
    await hub_report(ctx, hub_id, "up/rule_exec", {
        "id": new_id(), "rule_id": rule["id"], "plant_id": plant["id"], "ts": now,
        "reading": {"device": dev.id, "slot": 0, "seq": 1, "value": 10.0},
        "decision": "water", "command_id": cmd_id})

    cmds = await owner.get(f"/households/{h}/commands")
    assert [(c["id"], c["origin"], c["status"], c["plant_id"]) for c in cmds] == [
        (cmd_id, "hub", "done", plant["id"])]
    execs = await owner.get(f"/households/{h}/plants/{plant['id']}/rules/{rule['id']}/executions")
    assert execs[0]["origin"] == "hub" and execs[0]["command_id"] == cmd_id


async def test_remove_hub(household, owner, client, ctx):
    h = household["id"]
    hub_id = await online_hub(client, owner, ctx, h)
    created = await owner.post(f"/households/{h}/devices", {"name": "Bed"}, expect=201)
    await owner.delete(f"/households/{h}/hub")
    assert (await owner.get(f"/households/{h}/devices"))[0]["gateway"] == "none"
    cleared = {r.topic for r in await outbox(ctx) if r.payload is None}
    assert f"mc/hub/v1/{hub_id}/down/keys" in cleared
    assert created  # device kept, must be re-paired via rekey
    rekey = await owner.req("POST", f"/households/{h}/devices/{created['device']['id']}/rekey")
    assert rekey.status_code == 200 and rekey.json()["mqtt"]["host"] == "mqtt.example.com"


async def test_claim_moves_cloud_devices_to_no_gateway_until_rekey(setup, owner, client, ctx):
    h, dev = setup["h"], setup["device"]
    await online_hub(client, owner, ctx, h)
    assert (await owner.get(f"/households/{h}/devices"))[0]["gateway"] == "none"
    bundle = (await owner.req("POST", f"/households/{h}/devices/{dev.id}/rekey")).json()
    assert bundle["mqtt"]["host"] == "192.168.1.20"
    keys = json.loads((await outbox(ctx, "down/keys"))[-1].payload)
    assert [d["id"] for d in keys["devices"]] == [dev.id]
    snap = json.loads((await outbox(ctx, "down/snapshot"))[-1].payload)
    assert [d["id"] for d in snap["devices"]] == [dev.id]
