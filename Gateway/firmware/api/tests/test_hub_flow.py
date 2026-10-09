import io
import json
import zipfile

from .conftest import CFG, Stack, join_device, start_sim


async def test_device_plant_water_flow_through_the_hub(stack: Stack):
    owner = await stack.setup_owner()
    member, _ = await stack.user(owner, "member")
    admin, _ = await stack.user(owner, "admin")
    dev = await join_device(stack, admin, speed=1.0)       # real-time pump runs, so 'busy' can be observed
    devices = (await stack.get("/devices", member)).json()
    assert devices[0]["id"] == dev and devices[0]["status"] == "online" and devices[0]["last_seen_at"].endswith("Z")
    assert (await stack.get(f"/devices/{dev}", member)).json()["board"] == "carrier-v1"
    assert (await stack.get("/devices/join", member)).json()["devices"] == [dev]
    assert (await stack.patch(f"/devices/{dev}", admin, {"name": "Windowsill"})).json()["name"] == "Windowsill"

    cfg = (await stack.get(f"/devices/{dev}/config", member)).json()
    assert cfg["desired_rev"] == 1 and cfg["sync_state"] == "in_sync"
    r = await stack.put(f"/devices/{dev}/config", admin, {"base_rev": 1, "config": CFG})
    assert r.status_code == 200 and r.json()["rev"] == 2
    assert (await stack.put(f"/devices/{dev}/config", admin, {"base_rev": 1, "config": CFG})).json()["code"] == "conflict"
    await stack.until(lambda: stack.mc.hub.state["devices"][0]["reported_rev"] == 2)
    assert (await stack.get(f"/devices/{dev}/config", member)).json()["reported"]["slots"][1]["module"] == "pump"
    board = (await stack.get("/meta/boards/carrier-v1", member)).json()
    assert [p["id"] for p in board["ports"]] == ["P1", "P2", "P3", "P4"]

    plant = (await stack.post("/plants", member, {"name": "Ficus", "sensor": {"device_id": dev, "slot": 0},
                                                  "pump": {"device_id": dev, "slot": 2}})).json()
    assert (await stack.get(f"/plants/{plant['id']}", member)).json()["name"] == "Ficus"
    assert (await stack.patch(f"/plants/{plant['id']}", member, {"notes": "north window"})).json()["notes"] == "north window"
    rule = (await stack.post(f"/plants/{plant['id']}/rules", member,
                             {"threshold": 20, "water_s": 5, "cooldown_s": 600, "max_per_day": 3})).json()
    assert (await stack.get(f"/plants/{plant['id']}/rules", member)).json()[0]["id"] == rule["id"]
    assert (await stack.patch(f"/plants/{plant['id']}/rules/{rule['id']}", member, {"threshold": 25})).json()["threshold"] == 25

    cmd = (await stack.post(f"/plants/{plant['id']}/water", member, {"seconds": 1})).json()
    assert cmd["status"] == "queued" and cmd["created_at"].endswith("Z") and cmd["exp"].endswith("Z")
    assert (await stack.post(f"/plants/{plant['id']}/water", member, {"seconds": 1})).status_code == 409   # busy
    assert (await stack.post(f"/plants/{plant['id']}/water", member, {"seconds": 9999})).json()["code"] == "safety_limit"

    async def status():
        return (await stack.get(f"/commands/{cmd['id']}", member)).json()["status"]
    await stack.until(lambda: status())
    for _ in range(400):
        if await status() == "done":
            break
        await stack.settle(3)
        import asyncio
        await asyncio.sleep(0.01)
    assert await status() == "done"
    assert (await stack.get(f"/plants/{plant['id']}/commands", member)).json()["items"][0]["id"] == cmd["id"]
    assert (await stack.get("/commands?status=done", member)).json()["items"][0]["id"] == cmd["id"]
    assert (await stack.get("/commands?limit=1", member)).json()["items"].__len__() == 1

    # readings: ISO and unix bounds both work, buckets aggregate
    await stack.sim.report(next(iter(stack.sim.modules.values())))
    await stack.settle()
    rd = (await stack.get(f"/plants/{plant['id']}/readings", member)).json()
    assert rd["items"] and isinstance(rd["items"][0]["ts"], str) and rd["items"][0]["ts"].endswith("Z")
    b = (await stack.get(f"/plants/{plant['id']}/readings?bucket=hour&from=2020-01-01T00:00:00Z", member)).json()
    assert b["items"][0]["count"] >= 1
    assert (await stack.get(f"/devices/{dev}/health", member)).json()["items"]
    assert (await stack.get(f"/devices/{dev}/events", member)).json()["items"] == []
    ident = await stack.post(f"/devices/{dev}/actions", member, {"action": "identify"})
    assert ident.status_code == 202 and ident.json()["action"] == "device.identify"
    assert (await stack.post(f"/devices/{dev}/actions", member, {"action": "reboot"})).status_code == 403
    assert (await stack.post(f"/devices/{dev}/actions", admin, {"action": "reboot"})).status_code == 202
    cancel = await stack.post(f"/commands/{cmd['id']}/cancel", member)
    assert cancel.status_code == 409                                                   # already done


async def test_alerts_and_ack(stack: Stack):
    owner = await stack.setup_owner()
    member, _ = await stack.user(owner, "member")
    viewer, _ = await stack.user(owner, "viewer")
    dev = await join_device(stack, owner)
    await stack.sim.t.publish(f"zigbee2mqtt/{dev}/availability", b'{"state":"offline"}')
    await stack.until(lambda: stack.mc.hub.state["alerts_open"])
    alert = (await stack.get("/alerts", viewer)).json()[0]
    assert alert["kind"] == "device_offline" and alert["opened_at"].endswith("Z")
    assert (await stack.post(f"/alerts/{alert['id']}/ack", viewer)).status_code == 403
    r = await stack.post(f"/alerts/{alert['id']}/ack", member)
    assert r.status_code == 200 and r.json()["acked_at"].endswith("Z")


async def test_removing_a_device_needs_the_password(stack: Stack):
    owner = await stack.setup_owner()
    dev = await join_device(stack, owner)
    assert (await stack.delete(f"/devices/{dev}", owner)).json()["code"] == "reauth_required"
    assert (await stack.delete(f"/devices/{dev}", owner, headers=await stack.proof(owner))).status_code == 204
    await stack.until(lambda: stack.mc.hub.state["devices"] == [])
    assert (await stack.get(f"/devices/{dev}", owner)).status_code == 404


async def test_hub_down_gives_stale_reads_and_refused_writes(stack: Stack):
    owner = await stack.setup_owner()
    plant = (await stack.post("/plants", owner, {"name": "Aloe"})).json()
    await stack.hub_t.kill()
    await stack.settle()
    r = await stack.get("/plants", owner)
    assert r.status_code == 200 and r.json()[0]["name"] == "Aloe" and r.headers["x-mc-stale"] == "true"
    w = await stack.post(f"/plants/{plant['id']}/water", owner, {"seconds": 5})
    assert w.status_code == 503 and w.json()["code"] == "hub_unavailable"
    assert (await stack.get("/me", owner)).status_code == 200                       # login side keeps working
    assert (await stack.get("/status", owner)).json()["hub"]["online"] is False
    assert (await stack.get("/meta")).json()["hub"]["online"] is False


async def test_hub_timeout_and_incompatible_contract(stack: Stack):
    owner = await stack.setup_owner()
    stack.mc.hub.timeout_s = 0.3
    stack.broker.drop = lambda t, p: t.startswith("mc/v1/req/")
    r = await stack.post("/plants", owner, {"name": "Lost"})
    assert r.status_code == 504 and r.json()["code"] == "hub_timeout"
    stack.broker.drop = None
    await stack.broker.clients[0].publish("mc/v1/status/hub", b'{"state":"online","contract":"2.0","version":"9"}', retain=True)
    await stack.settle()
    r = await stack.post("/plants", owner, {"name": "x"})
    assert r.status_code == 503 and r.json()["code"] == "incompatible_hub"
    assert (await stack.get("/meta")).json()["hub"]["compatible"] is False


async def test_installation_and_status(stack: Stack):
    owner = await stack.setup_owner()
    r = await stack.patch("/installation", owner, {"name": "Flat 4", "telegram": {"token": "123:SECRET", "chat_id": "42"}})
    assert r.status_code == 200
    inst = (await stack.get("/installation", owner)).json()
    assert inst["name"] == "Flat 4" and inst["telegram_configured"] is True and "SECRET" not in json.dumps(inst)
    assert (await stack.patch("/installation", owner, {"timezone": "Mars/Base"})).status_code == 422
    st = (await stack.get("/status", owner)).json()
    assert st["hub"]["online"] and st["hub"]["contract"] == "1.0" and st["api"]["db_size"] > 0
    log = (await stack.get("/audit", owner)).json()["items"]
    assert "SECRET" not in json.dumps(log) and any(i["action"] == "installation_changed" for i in log)


async def test_export_and_backup(stack: Stack):
    owner = await stack.setup_owner()
    dev = await join_device(stack, owner)
    await stack.post("/plants", owner, {"name": "Fern", "sensor": {"device_id": dev, "slot": 0}})
    r = await stack.post("/export", owner, headers=await stack.proof(owner))
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"manifest.json", "users.json", "installation.json", "devices.json", "plants.json", "rules.json",
            "readings.ndjson.gz", "health.ndjson.gz", "events.ndjson.gz", "commands.ndjson.gz",
            "rule_executions.ndjson.gz"} == names
    users = json.loads(z.read("users.json"))
    assert users[0]["username"] == "owner" and "password_hash" not in json.dumps(users)
    assert json.loads(z.read("plants.json"))[0]["name"] == "Fern"
    assert json.loads(z.read("installation.json"))["name"] == "Home"
    b = await stack.post("/backup", owner)
    assert b.status_code == 200 and b.json()["hub"]["file"].startswith("hub-") and b.json()["api"]["file"].startswith("api-")
