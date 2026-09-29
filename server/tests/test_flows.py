"""End-to-end flows through the API and the ingest pipeline."""

import json

from mc_server.jobs import runner

from .conftest import Api, FakeDevice, outbox


async def test_device_pairing_bundle_and_initial_config(setup, ctx):
    bundle = setup["bundle"]
    assert bundle["device_id"].startswith("mc-")
    assert bundle["mqtt"] == {"host": "mqtt.example.com", "port": 8883,
                              "psk": bundle["mqtt"]["psk"]}
    assert len(bundle["mqtt"]["psk"]) == 64
    desired = await outbox(ctx, "config/desired")
    assert desired[0].retain and json.loads(desired[0].payload)["rev"] == 1


async def test_telemetry_reaches_plant_and_device(setup, owner):
    h, dev = setup["h"], setup["device"]
    await dev.wake(moisture=37.2, batt_mv=3950)
    await dev.sleep(600)
    plant = await owner.get(f"/households/{h}/plants/{setup['plant']['id']}")
    assert plant["moisture"] == 37.2 and plant["max_run_s"] == 60
    device = (await owner.get(f"/households/{h}/devices"))[0]
    assert device["status"] == "sleeping" and device["batt_mv"] == 3950
    assert device["sync_state"] == "in_sync"
    readings = await owner.get(f"/households/{h}/plants/{setup['plant']['id']}/readings")
    assert [r["value"] for r in readings] == [37.2]


async def test_duplicate_telemetry_is_dropped(setup, owner):
    dev = setup["device"]
    await dev.wake(moisture=40)
    dev.seq -= 1  # resend the same seq, like a QoS 1 duplicate
    await dev.wake(moisture=10)
    readings = await owner.get(f"/households/{setup['h']}/plants/{setup['plant']['id']}/readings")
    assert [r["value"] for r in readings] == [40]


async def test_water_command_lifecycle(setup, owner, ctx):
    h, dev, plant = setup["h"], setup["device"], setup["plant"]
    sub = ctx.bus.subscribe(h, "alice", None)
    res = await owner.post(f"/households/{h}/plants/{plant['id']}/water", {"seconds": 10},
                           expect=202)
    cmd = res["command"]
    assert cmd["status"] == "queued" and res["warnings"] == []
    sent = await outbox(ctx, "/cmd")
    assert json.loads(sent[-1].payload) == {
        "id": cmd["id"], "action": "pump.run", "exp": json.loads(sent[-1].payload)["exp"],
        "args": {"slot": 2, "seconds": 10}}

    # A second run on the same pump while one is pending → busy.
    busy = await owner.req("POST", f"/households/{h}/plants/{plant['id']}/water",
                           json={"seconds": 5})
    assert busy.status_code == 409 and busy.json()["type"] == "busy"

    await dev.ack(cmd["id"], "done", ts=1790412318)
    got = await owner.get(f"/households/{h}/commands/{cmd['id']}")
    assert got["status"] == "done"
    kinds = [sub.queue.get_nowait().kind for _ in range(sub.queue.qsize())]
    assert kinds.count("command") >= 2


async def test_safety_limit_from_reported_config(setup, owner):
    r = await owner.req("POST", f"/households/{setup['h']}/plants/{setup['plant']['id']}/water",
                        json={"seconds": 61})
    assert r.status_code == 422 and r.json()["type"] == "safety_limit"


async def test_cancel_queued_command(setup, owner, ctx):
    h, dev = setup["h"], setup["device"]
    cmd = (await owner.post(f"/households/{h}/plants/{setup['plant']['id']}/water",
                            {"seconds": 10}, expect=202))["command"]
    res = await owner.post(f"/households/{h}/commands/{cmd['id']}/cancel", expect=202)
    assert res["status"] == "cancelling"
    cancel_msg = json.loads((await outbox(ctx, "/cmd"))[-1].payload)
    assert cancel_msg["action"] == "cmd.cancel" and cancel_msg["args"] == {"target": cmd["id"]}
    await dev.ack(cmd["id"], "cancelled")
    assert (await owner.get(f"/households/{h}/commands/{cmd['id']}"))["status"] == "cancelled"


async def test_failed_command_opens_alert(setup, owner):
    h = setup["h"]
    cmd = (await owner.post(f"/households/{h}/plants/{setup['plant']['id']}/water",
                            {"seconds": 10}, expect=202))["command"]
    await setup["device"].ack(cmd["id"], "failed", reason="hw_error")
    alerts = await owner.get(f"/households/{h}/alerts")
    assert [a["kind"] for a in alerts] == ["command_failed"]
    acked = await owner.post(f"/households/{h}/alerts/{alerts[0]['id']}/ack", expect=200)
    assert acked["resolved_at"] is not None


async def test_config_validation_and_conflict(setup, owner):
    h, dev = setup["h"], setup["device"]
    path = f"/households/{h}/devices/{dev.id}/config"
    bad = await owner.req("PUT", path, json={"base_rev": 1, "wake_interval_s": 600, "slots": [
        {"slot": 0, "module": "pump_relay", "pin": 34, "max_run_s": 10}]})
    assert bad.status_code == 422 and bad.json()["type"] == "pin_not_output"
    ok = await owner.put(path, {"base_rev": 1, "wake_interval_s": 900, "slots": [
        {"slot": 0, "module": "moisture_capacitive", "pin": 34},
        {"slot": 2, "module": "pump_relay", "pin": 25, "max_run_s": 30}]})
    assert ok["desired_rev"] == 2 and ok["sync_state"] == "pending"
    stale = await owner.req("PUT", path, json={"base_rev": 1, "wake_interval_s": 600,
                                               "slots": []})
    assert stale.status_code == 409 and stale.json()["type"] == "config_rev_conflict"

    await dev.report_config(rev=1, result="rejected", rejected_rev=2,
                            error={"slot": 2, "code": "pin_not_output", "detail": "x"})
    cfg = await owner.get(path)
    assert cfg["sync_state"] == "rejected"
    assert [a["kind"] for a in await owner.get(f"/households/{h}/alerts")] == ["config_rejected"]
    await dev.report_config(rev=2, max_run_s=30)
    assert (await owner.get(path))["sync_state"] == "in_sync"
    assert (await owner.get(f"/households/{h}/alerts?open_only=true")) == []


async def test_invalid_payload_is_recorded(setup, owner):
    await setup["device"].send("telemetry", b"{not json")
    events = await owner.get(f"/households/{setup['h']}/devices/{setup['device'].id}/events")
    assert events[0]["kind"] == "invalid_payload"


async def test_sensor_error_alert_after_three_cycles(setup, owner):
    for _ in range(3):
        await setup["device"].wake(error="no_signal")
    alerts = await owner.get(f"/households/{setup['h']}/alerts")
    assert [a["kind"] for a in alerts] == ["sensor_error"]
    await setup["device"].wake(moisture=40)
    assert await owner.get(f"/households/{setup['h']}/alerts?open_only=true") == []


async def test_lwt_opens_crash_alert_and_online_resolves(setup, owner):
    dev = setup["device"]
    await dev.send("status", {"state": "offline"})
    assert [a["kind"] for a in await owner.get(f"/households/{setup['h']}/alerts")] == [
        "device_crashed"]
    await dev.wake()
    assert await owner.get(f"/households/{setup['h']}/alerts?open_only=true") == []


async def test_expiry_job(setup, owner, ctx):
    h = setup["h"]
    cmd = (await owner.post(f"/households/{h}/plants/{setup['plant']['id']}/water",
                            {"seconds": 10}, expect=202))["command"]
    from datetime import timedelta

    from mc_server.db.models import CommandRow

    async with ctx.sessionmaker() as s:
        row = await s.get(CommandRow, cmd["id"])
        row.exp = row.exp - timedelta(hours=3)
        await s.commit()
    await runner.run_once(ctx)
    assert (await owner.get(f"/households/{h}/commands/{cmd['id']}"))["status"] == "expired"


async def test_late_and_offline_detection(setup, owner, ctx):
    from datetime import timedelta

    from mc_server.db.models import Device

    await setup["device"].sleep(600)
    async with ctx.sessionmaker() as s:
        d = await s.get(Device, setup["device"].id)
        d.next_expected_at -= timedelta(minutes=25)  # > 1 interval overdue
        await s.commit()
    await runner.run_once(ctx)
    assert (await owner.get(f"/households/{setup['h']}/devices"))[0]["status"] == "late"
    async with ctx.sessionmaker() as s:
        d = await s.get(Device, setup["device"].id)
        d.next_expected_at -= timedelta(minutes=30)  # > 3 intervals overdue
        await s.commit()
    await runner.run_once(ctx)
    assert (await owner.get(f"/households/{setup['h']}/devices"))[0]["status"] == "offline"
    assert [a["kind"] for a in await owner.get(f"/households/{setup['h']}/alerts")] == [
        "device_offline"]


async def test_delete_device_clears_retained_topics(setup, owner, ctx):
    dev = setup["device"]
    await owner.delete(f"/households/{setup['h']}/devices/{dev.id}")
    cleared = [r.topic for r in await outbox(ctx) if r.payload is None and r.retain]
    assert f"mc/v1/{dev.id}/config/desired" in cleared
    plant = await owner.get(f"/households/{setup['h']}/plants/{setup['plant']['id']}")
    assert plant["pump_device_id"] is None


async def test_export_contains_no_keys(setup, owner):
    import io
    import zipfile

    await setup["device"].wake()
    r = await owner.req("POST", f"/households/{setup['h']}/export", expect=200)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert "manifest.json" in z.namelist()
    assert "psk" not in z.read("devices.json").decode()
    assert json.loads(z.read("manifest.json"))["counts"]["readings.ndjson.gz"] == 1


async def test_sse_ticket_is_single_use(owner, household, ctx):
    t = (await owner.post("/events/ticket", expect=200))["ticket"]
    assert ctx.bus.redeem_ticket(t) == "alice"
    assert ctx.bus.redeem_ticket(t) is None


async def test_board_meta(owner):
    board = await owner.get("/meta/boards/doit_esp32_devkit_v1")
    assert 34 in board["input_only_pins"]


async def test_unknown_device_is_ignored(ctx):
    await FakeDevice(ctx, "mc-unknown000000000").wake()


async def test_api_as_second_user(other: Api):
    assert await other.get("/me/households") == []
