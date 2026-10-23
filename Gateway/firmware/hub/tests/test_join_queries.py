import importlib.util
import json
from pathlib import Path

from sqlalchemy import select

from mc_hub.db.models import Command, Plant, Rule

from .conftest import CFG, ack, add_device, device_report, plant_entry, ready_device, ready_plant, sent


def load_sim():
    path = Path(__file__).resolve().parents[3] / "scripts" / "z2m_sim.py"
    spec = importlib.util.spec_from_file_location("z2m_sim", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def published(rig, topic):
    return [json.loads(p) for t, p in rig.broker.log if t == topic]


# ---- join window ---------------------------------------------------------------------------------

async def test_join_open_close_and_expiry(rig):
    await rig.z2m.t.publish("zigbee2mqtt/bridge/state", b'{"state":"online"}', retain=True)
    res = await rig.api.request("device_join_open", {"seconds": 60})
    assert res["ok"] and res["body"]["join"]["open"] is True
    assert published(rig, "zigbee2mqtt/bridge/request/permit_join") == [{"time": 60}]
    assert rig.api.state["state/join"]["open"] is True
    await rig.z2m.devices([plant_entry()])
    await rig.api.settle()
    new = rig.api.state["state/devices"][0]["id"]
    assert rig.api.state["state/join"]["devices"] == [new]
    rig.clock.advance(61)
    await rig.hub.tick()
    await rig.api.settle()
    assert rig.api.state["state/join"]["open"] is False
    await rig.api.request("device_join_open", {})
    await rig.api.request("device_join_close", {})
    assert published(rig, "zigbee2mqtt/bridge/request/permit_join")[-1] == {"time": 0}
    assert rig.api.state["state/join"]["open"] is False


async def test_join_validation_and_install_code(rig):
    assert (await rig.api.request("device_join_open", {"seconds": 5}))["error"]["type"] == "validation"
    assert (await rig.api.request("device_join_open", {"install_code": "xyz"}))["error"]["type"] == "validation"
    r = await rig.api.request("device_join_open", {"install_code": "83fe d340 7a93 9738 9d3a 6b1b 1d8a 7f34"})
    assert r["ok"]
    assert published(rig, "zigbee2mqtt/bridge/request/install_code/add") == [{"value": "83FED3407A9397389D3A6B1B1D8A7F34"}]


async def test_join_refused_while_zigbee_is_down(rig):
    await rig.z2m.t.publish("zigbee2mqtt/bridge/state", b'{"state":"offline"}', retain=True)
    await rig.api.settle()
    assert (await rig.api.request("device_join_open", {}))["error"]["type"] == "conflict"


async def test_permit_join_error_closes_the_window(rig):
    await rig.api.request("device_join_open", {})
    await rig.z2m.t.publish("zigbee2mqtt/bridge/response/permit_join",
                            b'{"status":"error","error":"coordinator busy"}')
    await rig.api.settle()
    st = rig.api.state["state/join"]
    assert st["open"] is False and st["error"] == "coordinator busy"


async def test_failed_interview_is_retried_twice(rig):
    await rig.z2m.devices([plant_entry(interview="FAILED")])
    await rig.api.settle()
    assert rig.api.state["state/devices"][0]["status"] == "join_failed"
    retries = lambda: published(rig, "zigbee2mqtt/bridge/request/device/interview")
    await rig.hub.tick()
    assert retries() == []                                       # first the pause
    for n in (1, 2):
        rig.clock.advance(31)
        await rig.hub.tick()
        await rig.api.settle()
        assert len(retries()) == n and retries()[-1] == {"id": "0x00124b0001"}
        assert rig.api.state["state/devices"][0]["status"] == "joining"
        await rig.z2m.devices([plant_entry(interview="FAILED")])   # still failing
        await rig.api.settle()
    rig.clock.advance(31)
    await rig.hub.tick()
    await rig.api.settle()
    assert len(retries()) == 2 and rig.api.state["state/devices"][0]["status"] == "join_failed"


# ---- removal -------------------------------------------------------------------------------------

async def test_remove_device_cancels_commands_and_frees_plants(rig):
    dev, plant = await ready_plant(rig)
    rule = (await rig.api.request("rule_create", {"plant_id": plant["id"], "threshold": 30, "water_s": 5,
                                                  "cooldown_s": 60, "max_per_day": 3}))["body"]["rule"]
    await rig.z2m.availability(dev, "offline")
    await rig.api.settle()
    await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5})
    res = await rig.api.request("device_remove", {"device_id": dev, "force": True})
    assert res["ok"]
    assert published(rig, "zigbee2mqtt/bridge/request/device/remove") == [{"id": "0x00124b0001", "force": True}]
    assert rig.api.state["state/devices"] == []
    p = rig.api.state["state/plants"][0]
    assert p["sensor"]["device_id"] is None and p["pump"]["device_id"] is None
    assert rig.api.state["state/rules"][0]["enabled"] is False
    async with rig.sessions() as s:
        c = (await s.execute(select(Command))).scalar_one()
    assert c.status == "cancelled" and c.reason == "device_removed"
    assert (await rig.api.request("device_remove", {"device_id": dev}))["error"]["type"] == "not_found"
    await device_report_unknown(rig, dev)


async def device_report_unknown(rig, dev):
    await rig.z2m.state(dev, {"seq": 1})
    await rig.api.settle()
    assert rig.api.state["state/devices"] == []


# ---- queries -------------------------------------------------------------------------------------

async def fill_readings(rig, dev, n, start=45.0):
    for i in range(n):
        rig.clock.advance(600)
        await device_report(rig, dev, v0=start - i)


async def test_query_readings_raw_paging_and_range(rig):
    dev, plant = await ready_plant(rig)
    await fill_readings(rig, dev, 5)
    q = lambda **b: rig.api.request("query/readings", {"plant_id": plant["id"], **b})
    first = (await q(limit=2))["body"]
    assert [i["value"] for i in first["items"]] == [45.0, 44.0] and first["next_cursor"]
    second = (await q(limit=2, cursor=first["next_cursor"]))["body"]
    assert [i["value"] for i in second["items"]] == [43.0, 42.0]
    last = (await q(limit=2, cursor=second["next_cursor"]))["body"]
    assert [i["value"] for i in last["items"]] == [41.0] and last["next_cursor"] is None
    t0 = first["items"][0]["ts"]
    assert len((await q(**{"from": t0 + 1200, "to": t0 + 1799}))["body"]["items"]) == 1
    assert (await q(limit=0))["error"]["type"] == "validation"
    assert (await q(cursor="garbage"))["error"]["type"] == "validation"


async def test_query_readings_buckets(rig):
    dev, plant = await ready_plant(rig)
    await fill_readings(rig, dev, 6)                           # 6 readings, one every 10 minutes
    items = (await rig.api.request("query/readings", {"plant_id": plant["id"], "bucket": "hour"}))["body"]["items"]
    assert sum(i["count"] for i in items) == 6
    assert all(i["min"] <= i["avg"] <= i["max"] for i in items)
    assert (await rig.api.request("query/readings", {"plant_id": plant["id"], "bucket": "week"}))["error"]["type"] == "validation"


async def test_query_commands_command_events_health_and_executions(rig):
    dev, plant = await ready_plant(rig)
    rule = (await rig.api.request("rule_create", {"plant_id": plant["id"], "threshold": 30, "water_s": 5,
                                                  "cooldown_s": 60, "max_per_day": 5}))["body"]["rule"]
    await device_report(rig, dev, v0=10)                       # the rule waters
    cid = sent(rig, dev)[-1]["pump_run"]["cmd_id"]
    await ack(rig, dev, cid, "running", 1, ends_in_s=5)
    await ack(rig, dev, cid, "done", 2)
    rig.clock.advance(700)
    await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5})
    cmds = (await rig.api.request("query/commands", {"plant_id": plant["id"]}))["body"]["items"]
    assert [c["source"] for c in cmds] == ["manual", "rule"]       # newest first
    only = (await rig.api.request("query/commands", {"status": "done"}))["body"]["items"]
    assert [c["source"] for c in only] == ["rule"]
    page = (await rig.api.request("query/commands", {"limit": 1}))["body"]
    assert len(page["items"]) == 1 and page["next_cursor"]
    one = (await rig.api.request("query/command", {"command_id": cmds[1]["id"]}))["body"]["command"]
    assert one["status"] == "done"
    assert (await rig.api.request("query/command", {"command_id": "nope"}))["error"]["type"] == "not_found"
    health = (await rig.api.request("query/device_health", {"device_id": dev}))["body"]["items"]
    assert len(health) >= 3 and health[0]["ts"] >= health[-1]["ts"]
    await device_report(rig, dev, event={"n": 1, "code": "low_battery", "slot": 0, "arg": 0})
    ev = (await rig.api.request("query/device_events", {"device_id": dev}))["body"]["items"]
    assert [e["code"] for e in ev] == ["low_battery"]
    ex = (await rig.api.request("query/rule_executions", {"rule_id": rule["id"]}))["body"]["items"]
    assert [e["decision"] for e in ex] == ["water"]


async def test_export_parts(rig):
    dev, plant = await ready_plant(rig)
    await fill_readings(rig, dev, 3)
    await rig.api.request("installation_set", {"name": "Home", "telegram": {"token": "SECRET", "chat_id": "1"}})
    ex = lambda part, **b: rig.api.request("query/export", {"part": part, **b})
    inst = (await ex("installation"))["body"]["items"][0]
    assert inst["name"] == "Home" and "SECRET" not in json.dumps(inst)
    assert len((await ex("devices"))["body"]["items"]) == 1
    assert len((await ex("plants"))["body"]["items"]) == 1
    r = (await ex("readings"))["body"]
    assert len(r["items"]) == 5 and r["next_cursor"] is None      # two from the setup, three from here
    assert (await ex("nope"))["error"]["type"] == "validation"
    import mc_hub.services.queries as q
    q.EXPORT_CHUNK = 2
    try:
        page1 = (await ex("readings"))["body"]
        page2 = (await ex("readings", cursor=page1["next_cursor"]))["body"]
        page3 = (await ex("readings", cursor=page2["next_cursor"]))["body"]
    finally:
        q.EXPORT_CHUNK = 1000
    assert [len(p["items"]) for p in (page1, page2, page3)] == [2, 2, 1] and page3["next_cursor"] is None


# ---- backup --------------------------------------------------------------------------------------

async def test_backup_request_and_retention(rig):
    r = await rig.api.request("backup", {})
    assert r["ok"] and r["body"]["file"].startswith("hub-") and r["body"]["size"] > 0
    import sqlite3
    f = rig.hub.backup.dir / r["body"]["file"]
    assert sqlite3.connect(f).execute("select count(*) from sqlite_master").fetchone()[0] > 5
    for _ in range(16):
        rig.clock.advance(1)
        await rig.api.request("backup", {})
    assert len(list(rig.hub.backup.dir.glob("hub-*.db"))) == 14


async def test_nightly_backup_runs_once_a_day(rig):
    await rig.hub.tick()
    n = lambda: len(list(rig.hub.backup.dir.glob("hub-*.db")))
    assert n() == 1
    rig.clock.advance(3600)
    await rig.hub.tick()
    assert n() == 1
    rig.clock.advance(86400)
    await rig.hub.tick()
    assert n() == 2


# ---- the simulator -------------------------------------------------------------------------------

async def test_simulator_full_flow(rig):
    sim_mod = load_sim()
    sim = sim_mod.Sim(rig.broker.client(), modules=0, pending=1, speed=10000, join_delay=0.001,
                      report_interval=3600)
    await sim.t.connect()
    await sim.start()
    await rig.api.settle()

    async def until(pred, tries=200):
        import asyncio
        for _ in range(tries):
            await rig.api.settle()
            if pred():
                return
            await asyncio.sleep(0.005)
        raise AssertionError("condition not reached")

    await rig.api.request("device_join_open", {"seconds": 60})
    await until(lambda: rig.api.state["state/devices"] and rig.api.state["state/devices"][0]["status"] == "online")
    dev = rig.api.state["state/devices"][0]["id"]
    assert rig.api.state["state/join"]["devices"] == [dev]
    assert rig.api.state["state/devices"][0]["config_sync"] == "in_sync"          # initial revision applied
    r = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 1, "config": CFG})
    assert r["ok"]
    await until(lambda: rig.api.state["state/devices"][0]["reported_rev"] == 2)
    plant = (await rig.api.request("plant_create", {"name": "Sim", "sensor": {"device_id": dev, "slot": 0},
                                                    "pump": {"device_id": dev, "slot": 2}}))["body"]["plant"]
    cid = (await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5}))["body"]["command"]["id"]

    async def status():
        return (await rig.api.request("query/command", {"command_id": cid}))["body"]["command"]["status"]

    for _ in range(200):
        await rig.api.settle()
        if await status() == "done":
            break
        import asyncio
        await asyncio.sleep(0.005)
    assert await status() == "done"
    assert (await rig.api.request("water", {"plant_id": plant["id"], "seconds": 500}))["error"]["type"] == "safety_limit"
