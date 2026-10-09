import json

from sqlalchemy import func, select

from mc_hub.db.models import DeviceEvent, HealthReport, Reading

from .conftest import add_device, plant_entry, report


async def count(rig, model):
    async with rig.sessions() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar()


async def test_new_device_is_created_and_renamed(rig):
    await rig.z2m.devices([{"ieee_address": "0x00", "friendly_name": "Coordinator", "type": "Coordinator"},
                           plant_entry()])
    await rig.api.settle()
    devs = rig.api.state["state/devices"]
    assert len(devs) == 1 and devs[0]["id"].startswith("dev-") and devs[0]["status"] == "ready"
    renames = [json.loads(p) for t, p in rig.broker.log if t == "zigbee2mqtt/bridge/request/device/rename"]
    assert renames == [{"from": "0x00124b0001", "to": devs[0]["id"]}]


async def test_other_zigbee_devices_are_unsupported(rig):
    await rig.z2m.devices([plant_entry(ieee="0x99", friendly="0x99", model="TS0601")])
    await rig.api.settle()
    assert rig.api.state["state/devices"][0]["status"] == "unsupported"


async def test_interview_failure_and_recovery(rig):
    await rig.z2m.devices([plant_entry(interview="FAILED")])
    await rig.api.settle()
    assert rig.api.state["state/devices"][0]["status"] == "join_failed"
    await rig.z2m.devices([plant_entry(interview="SUCCESSFUL")])
    await rig.api.settle()
    assert rig.api.state["state/devices"][0]["status"] == "ready"


async def test_removed_device_is_soft_deleted(rig):
    await add_device(rig)
    await rig.z2m.devices([])
    await rig.api.settle()
    assert rig.api.state["state/devices"] == []


async def test_telemetry_stores_reading_for_assigned_plant(rig):
    dev = await add_device(rig)
    plant = (await rig.api.request("plant_create", {"name": "Ficus", "sensor": {"device_id": dev, "slot": 0}}))["body"]["plant"]
    rig.api.events.clear()
    await rig.z2m.state(dev, report(seq=1, v0=41.5))
    await rig.api.settle()
    async with rig.sessions() as s:
        rows = (await s.execute(select(Reading))).scalars().all()
    assert len(rows) == 1 and rows[0].plant_id == plant["id"] and rows[0].value == 41.5   # pump slot not stored
    d = rig.api.state["state/devices"][0]
    assert d["status"] == "online" and d["link_quality"] == 112 and d["latest_readings"]["0"]["value"] == 41.5
    assert d["board"] == "carrier-v1"
    assert rig.api.state["state/plants"][0]["latest_value"] == 41.5
    assert "reading" in [e["kind"] for e in rig.api.events]


async def test_repeated_seq_is_not_stored_twice_but_new_boot_is(rig):
    dev = await add_device(rig)
    for seq, boot in ((5, 1), (5, 1), (6, 1), (6, 1), (3, 2)):
        await rig.z2m.state(dev, report(seq=seq, boot_id=boot))
        await rig.api.settle()
    assert await count(rig, Reading) == 3 and await count(rig, HealthReport) == 3


async def test_seq_wraparound(rig):
    dev = await add_device(rig)
    for seq in (65535, 0):
        await rig.z2m.state(dev, report(seq=seq))
        await rig.api.settle()
    assert await count(rig, Reading) == 2


async def test_unknown_device_and_garbage_are_dropped(rig):
    await rig.z2m.state("dev-unknown", report())
    await rig.z2m.t.publish("zigbee2mqtt/dev-x", b"not json")
    await rig.api.settle()
    assert await count(rig, Reading) == 0


async def test_offline_alert_and_recovery(rig):
    dev = await add_device(rig)
    await rig.z2m.state(dev, report(seq=1))
    await rig.z2m.availability(dev, "offline")
    await rig.api.settle()
    assert rig.api.state["state/devices"][0]["status"] == "offline"
    alerts = rig.api.state["state/alerts_open"]
    assert [a["kind"] for a in alerts] == ["device_offline"]
    await rig.z2m.state(dev, report(seq=2))
    await rig.api.settle()
    assert rig.api.state["state/devices"][0]["status"] == "online"
    assert rig.api.state["state/alerts_open"] == []


async def test_safe_mode_alert(rig):
    dev = await add_device(rig)
    await rig.z2m.state(dev, report(seq=1, status="safe_mode", safe_reason="crash_loop"))
    await rig.api.settle()
    d = rig.api.state["state/devices"][0]
    assert d["status"] == "safe_mode" and d["safe_reason"] == "crash_loop"
    assert rig.api.state["state/alerts_open"][0]["kind"] == "device_safe_mode"
    await rig.z2m.state(dev, report(seq=2))
    await rig.api.settle()
    assert rig.api.state["state/alerts_open"] == []


async def test_events_are_deduplicated_and_raise_alerts(rig):
    dev = await add_device(rig)
    ev = {"n": 4, "code": "sensor_fault", "slot": 0, "arg": 0}
    for seq in (1, 2):
        await rig.z2m.state(dev, report(seq=seq, event=ev))
        await rig.api.settle()
    assert await count(rig, DeviceEvent) == 1
    assert [a["kind"] for a in rig.api.state["state/alerts_open"]] == ["sensor_error"]
    await rig.z2m.state(dev, report(seq=3, event={"n": 5, "code": "sensor_ok", "slot": 0, "arg": 0}))
    await rig.api.settle()
    assert rig.api.state["state/alerts_open"] == []


async def test_alert_ack_goes_through_request(rig):
    dev = await add_device(rig)
    await rig.z2m.state(dev, report(seq=1, event={"n": 1, "code": "safety_stop", "slot": 2, "arg": 0}))
    await rig.api.settle()
    alert = rig.api.state["state/alerts_open"][0]
    r = await rig.api.request("alert_ack", {"alert_id": alert["id"]}, role="member")
    assert r["ok"] and r["body"]["alert"]["acked_by"] == "u1"
    assert rig.api.state["state/alerts_open"][0]["acked_at"] is not None


async def test_config_state_sync(rig):
    dev = await add_device(rig)
    await rig.z2m.state(dev, report(seq=1, cfg_rev=0, cfg_result="ok"))
    await rig.api.settle()
    d = rig.api.state["state/devices"][0]
    assert d["reported_rev"] == 0 and d["config_sync"] == "pending"   # the initial revision 1 is still to be applied
    await rig.z2m.state(dev, report(seq=2, cfg_rev=1, cfg_result="ok"))
    await rig.api.settle()
    d = rig.api.state["state/devices"][0]
    assert d["reported_rev"] == 1 and d["config_sync"] == "in_sync"


async def test_bridge_state_in_status_snapshot(rig):
    await rig.z2m.t.publish("zigbee2mqtt/bridge/state", b'{"state":"online"}', retain=True)
    await rig.api.settle()
    assert rig.api.state["state/status"]["zigbee2mqtt"] == "online"
