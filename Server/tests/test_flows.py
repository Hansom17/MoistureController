"""End-to-end flows through the API and the ingest pipeline."""

import json

from mc_api.jobs import runner

from .conftest import Api, FakeDevice, downlink


async def test_device_pairing_bundle_and_initial_config(setup, ctx):
    bundle = setup["bundle"]
    assert bundle["device_id"].startswith("mc-")
    assert bundle["mqtt"] == {"host": "192.168.1.20", "port": 8883,
                              "psk": bundle["mqtt"]["psk"]}
    assert len(bundle["mqtt"]["psk"]) == 64
    desired = await downlink(ctx, "config_desired")
    assert desired[0].body["device"] == bundle["device_id"]
    assert desired[0].body["config"]["rev"] == 1
    # Only the newest key set / snapshot is pending; it has the device in it.
    keys = await downlink(ctx, "keys", pending=True)
    assert len(keys) == 1 and [d["id"] for d in keys[0].body["devices"]] == [bundle["device_id"]]
    assert keys[0].body["devices"][0]["psk"] == bundle["mqtt"]["psk"]
    snap = await downlink(ctx, "snapshot", pending=True)
    assert len(snap) == 1 and snap[0].body["plants"][0]["id"] == setup["plant"]["id"]


async def test_device_needs_a_gateway(owner, household):
    r = await owner.req("POST", f"/households/{household['id']}/devices", json={"name": "X"})
    assert r.status_code == 409 and r.json()["type"] == "no_gateway"


async def test_device_needs_gateway_online(owner, household, gateway, ctx):
    ctx.gateways.unregister(gateway)
    r = await owner.req("POST", f"/households/{household['id']}/devices", json={"name": "X"})
    assert r.status_code == 409 and r.json()["type"] == "gateway_offline"


async def test_down_ack_updates_sync_state(setup, owner, ctx):
    h, gw = setup["h"], setup["gateway"]
    info = await owner.get(f"/households/{h}/gateway")
    assert info["online"] and not info["in_sync"] and info["lan_host"] == "192.168.1.20"
    for row in await downlink(ctx, pending=True):
        if row.type in ("snapshot", "keys"):
            await gw.down_ack(row)
    info = await owner.get(f"/households/{h}/gateway")
    assert info["in_sync"] and info["snapshot_rev_applied"] == info["snapshot_rev"]
    households = await owner.get("/me/households")
    assert households[0]["gateway"] == {"online": True, "offline_since": None}


async def test_rejected_snapshot_opens_alert(setup, owner, ctx):
    snap = (await downlink(ctx, "snapshot", pending=True))[0]
    await setup["gateway"].down_ack(snap, "rejected", "bad_rule")
    alerts = await owner.get(f"/households/{setup['h']}/alerts")
    assert [a["kind"] for a in alerts] == ["gateway_sync_failed"]


async def test_replayed_up_message_is_ignored_by_seq(setup, owner, ctx):
    from mc_api.db.models import Gateway

    await setup["device"].wake(moisture=40)
    async with ctx.sessionmaker() as s:
        assert (await s.get(Gateway, setup["gateway"].gateway_id)).last_up_seq == \
            setup["gateway"].seq


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
    sent = (await downlink(ctx, "command"))[-1]
    assert sent.body["device"] == dev.id
    assert sent.body["command"] == {
        "id": cmd["id"], "action": "pump.run", "exp": sent.body["command"]["exp"],
        "args": {"slot": 2, "seconds": 10}}
    await setup["gateway"].down_ack(sent)

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
    # Handed to the gateway: cancelling needs the device's ack.
    await setup["gateway"].down_ack((await downlink(ctx, "command"))[-1])
    res = await owner.post(f"/households/{h}/commands/{cmd['id']}/cancel", expect=202)
    assert res["status"] == "cancelling"
    cancel_msg = (await downlink(ctx, "command"))[-1].body["command"]
    assert cancel_msg["action"] == "cmd.cancel" and cancel_msg["args"] == {"target": cmd["id"]}
    await dev.ack(cmd["id"], "cancelled")
    assert (await owner.get(f"/households/{h}/commands/{cmd['id']}"))["status"] == "cancelled"


async def test_gateway_rejected_command_fails(setup, owner, ctx):
    h = setup["h"]
    cmd = (await owner.post(f"/households/{h}/plants/{setup['plant']['id']}/water",
                            {"seconds": 10}, expect=202))["command"]
    await setup["gateway"].down_ack((await downlink(ctx, "command"))[-1], "rejected",
                                    "unknown_device")
    got = await owner.get(f"/households/{h}/commands/{cmd['id']}")
    assert got["status"] == "failed" and got["reason"] == "unknown_device"


async def test_command_from_gateway_rule(setup, owner, ctx):
    h, dev, plant = setup["h"], setup["device"], setup["plant"]
    rule = await owner.post(f"/households/{h}/plants/{plant['id']}/rules", {
        "threshold": 30, "water_s": 10, "cooldown_s": 0, "max_per_day": 4}, expect=201)
    await dev.wake(moisture=20)
    gw = setup["gateway"]
    await gw.up({"t": "command_created", "id": "01JCMDFROMGATEWAY000000000", "device": dev.id,
                 "action": "pump.run", "args": {"slot": 2, "seconds": 10},
                 "exp": 1_900_000_000, "source": "rule", "rule_id": rule["id"],
                 "plant_id": plant["id"], "created_at": 1_790_000_000})
    await gw.up({"t": "rule_exec", "id": "01JRULEEXECFROMGATEWAY0000", "rule_id": rule["id"],
                 "plant_id": plant["id"], "ts": 1_790_000_000,
                 "reading": {"device": dev.id, "slot": 0, "seq": dev.seq, "value": 20},
                 "decision": "water", "command_id": "01JCMDFROMGATEWAY000000000"})
    got = await owner.get(f"/households/{h}/commands/01JCMDFROMGATEWAY000000000")
    assert got["origin"] == "gateway" and got["source"] == "rule"
    await dev.ack(got["id"], "done")
    assert (await owner.get(f"/households/{h}/commands/{got['id']}"))["status"] == "done"


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
    await setup["device"].send("telemetry", {"seq": "not a number"})
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

    from mc_api.db.models import CommandRow

    from mc_api.db.models import Gateway

    async with ctx.sessionmaker() as s:
        row = await s.get(CommandRow, cmd["id"])
        row.exp = row.exp - timedelta(hours=3)
        # Past the grace period after the gateway (re)connected.
        (await s.get(Gateway, setup["gateway"].gateway_id)).connected_at -= timedelta(hours=1)
        await s.commit()
    await runner.run_once(ctx)
    assert (await owner.get(f"/households/{h}/commands/{cmd['id']}"))["status"] == "expired"


async def test_late_and_offline_detection(setup, owner, ctx):
    from datetime import timedelta

    from mc_api.db.models import Device

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


async def test_delete_device_tells_gateway(setup, owner, ctx):
    dev = setup["device"]
    await owner.delete(f"/households/{setup['h']}/devices/{dev.id}")
    assert [r.body["device"] for r in await downlink(ctx, "device_removed")] == [dev.id]
    assert (await downlink(ctx, "keys", pending=True))[0].body["devices"] == []
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


async def test_unknown_device_is_ignored(gateway):
    await FakeDevice(gateway, "mc-unknown000000000").wake()


async def test_offline_gateway_pauses_expiry_and_alerts(setup, owner, ctx):
    from datetime import timedelta

    from mc_api.db.models import CommandRow, Gateway

    h, gw = setup["h"], setup["gateway"]
    cmd = (await owner.post(f"/households/{h}/plants/{setup['plant']['id']}/water",
                            {"seconds": 10}, expect=202))["command"]
    ctx.gateways.unregister(gw)
    from mc_api.services import gateways

    async with ctx.uow() as uow:
        await gateways.disconnected(uow, gw.gateway_id)
    async with ctx.sessionmaker() as s:
        row = await s.get(CommandRow, cmd["id"])
        row.exp = row.exp - timedelta(hours=3)
        (await s.get(Gateway, gw.gateway_id)).disconnected_at -= timedelta(minutes=20)
        await s.commit()
    await runner.run_once(ctx)
    assert (await owner.get(f"/households/{h}/commands/{cmd['id']}"))["status"] == "queued"
    assert [a["kind"] for a in await owner.get(f"/households/{h}/alerts")] == ["gateway_offline"]
    water = await owner.req("POST", f"/households/{h}/plants/{setup['plant']['id']}/water",
                            json={"seconds": 5})
    assert water.status_code == 409  # still busy with the queued one


async def test_remove_gateway(setup, owner, ctx):
    h = setup["h"]
    await owner.delete(f"/households/{h}/gateway")
    assert [r.type for r in await downlink(ctx, "removed")] == ["removed"]
    assert (await owner.get(f"/households/{h}/devices"))[0]["needs_repair"]
    await owner.req("GET", f"/households/{h}/gateway", expect=404)


async def test_new_gateway_after_removal(setup, owner, client, ctx):
    from .conftest import enroll

    h = setup["h"]
    await owner.delete(f"/households/{h}/gateway")
    creds = await enroll(client, owner, h)
    assert creds["gateway_id"] != setup["gateway"].gateway_id
    assert (await owner.get(f"/households/{h}/gateway"))["id"] == creds["gateway_id"]


async def test_api_as_second_user(other: Api):
    assert await other.get("/me/households") == []
