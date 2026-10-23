from sqlalchemy import select

from mc_hub.db.models import Command

from .conftest import CFG, ack, add_device, device_report, ready_device, ready_plant, report, sent


async def commands_in_db(rig):
    async with rig.sessions() as s:
        return (await s.execute(select(Command).order_by(Command.created_at, Command.id))).scalars().all()


async def test_new_device_gets_initial_config_and_config_put_is_sent(rig):
    dev = await add_device(rig)
    await device_report(rig, dev)
    assert sent(rig, dev)[0]["config"]["rev"] == 1 and sent(rig, dev)[0]["config"]["slots"] == []
    await device_report(rig, dev, cfg_rev=1, cfg_result="ok")
    res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 1, "config": CFG})
    assert res["body"]["rev"] == 2
    cfg = sent(rig, dev)[-1]["config"]
    assert cfg["rev"] == 2 and cfg["report_interval_s"] == 300
    assert cfg["slots"][1] == {"slot": 2, "module": "pump", "port": "P3", "max_run_s": 60, "min_pause_s": 600, "active_high": True}
    assert rig.api.state["state/devices"][0]["config_sync"] == "pending"
    await device_report(rig, dev, cfg_rev=2, cfg_result="ok")
    assert rig.api.state["state/devices"][0]["config_sync"] == "in_sync"


async def test_config_validation(rig):
    dev = await add_device(rig)
    await device_report(rig, dev, cfg_rev=1, cfg_result="ok")

    async def put(config, base=1):
        return (await rig.api.request("device_config_put", {"device_id": dev, "base_rev": base, "config": config}))

    assert (await put(CFG, base=0))["error"]["type"] == "conflict"
    assert (await put({"slots": [{"slot": 0, "module": "moisture", "port": "P9"}]}))["error"]["type"] == "validation"
    assert (await put({"slots": [{"slot": 0, "module": "moisture", "port": "P1"},
                                 {"slot": 1, "module": "pump", "port": "P1"}]}))["error"]["type"] == "validation"
    assert (await put({"slots": [{"slot": 7, "module": "pump", "port": "P1"}]}))["error"]["type"] == "validation"
    assert (await put({"report_interval_s": 5}))["error"]["type"] == "validation"
    assert (await put({"slots": [{"slot": 0, "module": "pump", "port": "P1", "max_run_s": 9999}]}))["error"]["type"] == "validation"
    assert (await put({"slots": [{"slot": 0, "module": "led", "port": "P1"}]}))["error"]["type"] == "validation"


async def test_config_needs_a_known_board(rig):
    dev = await add_device(rig)
    res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 1, "config": CFG})
    assert res["error"]["type"] == "device_not_ready"          # no report yet, board unknown


async def test_rejected_config(rig):
    dev = await add_device(rig)
    await device_report(rig, dev, cfg_rev=1, cfg_result="ok")
    await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 1, "config": CFG})
    await device_report(rig, dev, cfg_rev=1, cfg_result="rejected", cfg_error=0x0301)
    d = rig.api.state["state/devices"][0]
    assert d["config_sync"] == "rejected"
    assert [a["kind"] for a in rig.api.state["state/alerts_open"]] == ["config_rejected"]
    n = len(sent(rig, dev))
    await rig.hub.tick()
    await rig.api.settle()
    assert len(sent(rig, dev)) == n                            # a rejected revision is not resent
    await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 2, "config": CFG})
    await device_report(rig, dev, cfg_rev=3, cfg_result="ok")
    assert rig.api.state["state/alerts_open"] == []


async def test_water_is_sent_at_once_and_follows_the_acks(rig):
    dev, plant = await ready_plant(rig)
    res = await rig.api.request("water", {"plant_id": plant["id"], "seconds": 10}, role="member")
    cmd = res["body"]["command"]
    assert cmd["status"] == "queued" and cmd["action"] == "pump.run"
    pr = sent(rig, dev)[-1]["pump_run"]
    assert pr["slot"] == 2 and pr["seconds"] == 10 and pr["ttl_s"] == 900
    await ack(rig, dev, pr["cmd_id"], "running", 1, ends_in_s=10)
    c = (await commands_in_db(rig))[0]
    assert c.status == "delivered" and c.ends_at == int(rig.clock.now()) + 10
    await ack(rig, dev, pr["cmd_id"], "done", 2)
    assert (await commands_in_db(rig))[0].status == "done"
    kinds = [e["body"]["status"] for e in rig.api.events if e["kind"] == "command"]
    assert kinds == ["queued", "queued", "delivered", "done"]    # created, sent, running, done


async def test_water_checks(rig):
    dev, plant = await ready_plant(rig)
    water = lambda s, **kw: rig.api.request("water", {"plant_id": plant["id"], "seconds": s, **kw})
    assert (await water(61))["error"]["type"] == "safety_limit"
    assert (await water(0))["error"]["type"] == "safety_limit"
    assert (await water(5, ttl_s=5))["error"]["type"] == "validation"
    first = await water(5)
    assert first["ok"]
    assert (await water(5))["error"]["type"] == "busy"
    cid = sent(rig, dev)[-1]["pump_run"]["cmd_id"]
    await ack(rig, dev, cid, "running", 1, ends_in_s=5)
    await ack(rig, dev, cid, "done", 2)
    again = await water(5)
    assert again["error"]["type"] == "safety_limit" and "min_pause" in again["error"]["detail"]
    rig.clock.advance(601)
    assert (await water(5))["ok"]


async def test_water_needs_pump_and_actuator_config(rig):
    dev = await add_device(rig)
    await device_report(rig, dev, cfg_rev=1, cfg_result="ok")
    p = (await rig.api.request("plant_create", {"name": "P", "pump": {"device_id": dev, "slot": 2}}))["body"]["plant"]
    assert (await rig.api.request("water", {"plant_id": p["id"], "seconds": 5}))["error"]["type"] == "slot_not_actuator"
    q = (await rig.api.request("plant_create", {"name": "Q"}))["body"]["plant"]
    assert (await rig.api.request("water", {"plant_id": q["id"], "seconds": 5}))["error"]["type"] == "conflict"


async def test_same_request_id_creates_one_command(rig):
    dev, plant = await ready_plant(rig)
    for _ in range(2):
        await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5}, id="01JC0000000000000000000099")
    assert len(await commands_in_db(rig)) == 1
    assert len([m for m in sent(rig, dev) if "pump_run" in m]) == 1


async def test_offline_device_queues_and_sends_with_remaining_ttl(rig):
    dev, plant = await ready_plant(rig)
    await rig.z2m.availability(dev, "offline")
    await rig.api.settle()
    n = len(sent(rig, dev))
    res = await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5})
    assert res["body"]["command"]["status"] == "queued"
    assert len(sent(rig, dev)) == n                              # nothing sent while offline
    rig.clock.advance(300)
    await rig.z2m.availability(dev, "online")
    await rig.api.settle()
    await device_report(rig, dev)                                # the module is back
    pr = sent(rig, dev)[-1]["pump_run"]
    assert pr["ttl_s"] == 600                                    # 900 - 300 waited


async def test_command_expires_while_the_device_is_offline(rig):
    dev, plant = await ready_plant(rig)
    await rig.z2m.availability(dev, "offline")
    await rig.api.settle()
    await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5})
    rig.clock.advance(901)
    await rig.hub.tick()
    await rig.api.settle()
    c = (await commands_in_db(rig))[0]
    assert c.status == "expired" and c.sent_at is None
    n = len(sent(rig, dev))
    await rig.z2m.availability(dev, "online")
    await device_report(rig, dev)
    assert len(sent(rig, dev)) == n or "pump_run" not in sent(rig, dev)[-1]


async def test_retries_then_waits_for_a_report(rig):
    dev, plant = await ready_plant(rig)
    await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5})
    runs = lambda: [m for m in sent(rig, dev) if "pump_run" in m]
    assert len(runs()) == 1
    for expected in (2, 3, 3):
        rig.clock.advance(12)
        await rig.hub.tick()
        await rig.api.settle()
        assert len(runs()) == expected
    assert runs()[0]["pump_run"]["cmd_id"] == runs()[2]["pump_run"]["cmd_id"]     # same id: idempotent on the device
    rig.clock.advance(12)
    await device_report(rig, dev)                                # a report gives it a fresh start
    assert len(runs()) == 4


async def test_cancel_unsent_command_is_immediate(rig):
    dev, plant = await ready_plant(rig)
    await rig.z2m.availability(dev, "offline")
    await rig.api.settle()
    cid = (await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5}))["body"]["command"]["id"]
    res = await rig.api.request("command_cancel", {"command_id": cid})
    assert res["body"]["command"]["status"] == "cancelled"
    assert (await rig.api.request("command_cancel", {"command_id": cid}))["error"]["type"] == "conflict"


async def test_cancel_running_run_sends_pump_stop(rig):
    dev, plant = await ready_plant(rig)
    cid = (await rig.api.request("water", {"plant_id": plant["id"], "seconds": 30}))["body"]["command"]["id"]
    run = sent(rig, dev)[-1]["pump_run"]
    await ack(rig, dev, run["cmd_id"], "running", 1, ends_in_s=30)
    res = await rig.api.request("command_cancel", {"command_id": cid})
    assert res["body"]["command"]["status"] == "cancelling"
    stop = sent(rig, dev)[-1]["pump_stop"]
    assert stop["slot"] == 2
    await ack(rig, dev, run["cmd_id"], "cancelled", 2)
    await ack(rig, dev, stop["cmd_id"], "done", 3)
    st = {c.action: c.status for c in await commands_in_db(rig)}
    assert st == {"pump.run": "cancelled", "pump.stop": "done"}


async def test_cancel_sent_but_unacked_command_sends_cancel(rig):
    dev, plant = await ready_plant(rig)
    cid = (await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5}))["body"]["command"]["id"]
    run = sent(rig, dev)[-1]["pump_run"]
    await rig.api.request("command_cancel", {"command_id": cid})
    # the pump_run is still in flight, so the cancel waits for its ack or timeout
    rig.clock.advance(12)
    await rig.hub.tick()
    await rig.api.settle()
    await ack(rig, dev, run["cmd_id"], "cancelled", 1)
    assert {c.action: c.status for c in await commands_in_db(rig)}["pump.run"] == "cancelled"


async def test_duplicate_ack_is_ignored_and_failure_raises_alert(rig):
    dev, plant = await ready_plant(rig)
    await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5})
    cid = sent(rig, dev)[-1]["pump_run"]["cmd_id"]
    await ack(rig, dev, cid, "failed", 1, reason="hw_error")
    await ack(rig, dev, cid, "failed", 1, reason="hw_error")
    c = (await commands_in_db(rig))[0]
    assert c.status == "failed" and c.reason == "hw_error"
    assert [a["kind"] for a in rig.api.state["state/alerts_open"]] == ["command_failed"]
    assert any("Watering failed" in t[2] for t in rig.tg_sent) is False     # telegram not configured


async def test_ack_for_unknown_or_foreign_command_is_ignored(rig):
    dev, plant = await ready_plant(rig)
    await ack(rig, dev, 424242, "done", 1)
    assert await commands_in_db(rig) == []


async def test_run_without_final_ack_fails(rig):
    dev, plant = await ready_plant(rig)
    await rig.api.request("water", {"plant_id": plant["id"], "seconds": 10})
    cid = sent(rig, dev)[-1]["pump_run"]["cmd_id"]
    await ack(rig, dev, cid, "running", 1, ends_in_s=10)
    rig.clock.advance(10 + 61)
    await rig.hub.tick()
    await rig.api.settle()
    c = (await commands_in_db(rig))[0]
    assert c.status == "failed" and c.reason == "no_final_ack"


async def test_safe_mode_allows_only_device_actions(rig):
    dev, plant = await ready_plant(rig)
    await device_report(rig, dev, status="safe_mode", safe_reason="crash_loop")
    assert (await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5}))["error"]["type"] == "device_safe_mode"
    res = await rig.api.request("device_action", {"device_id": dev, "action": "clear_safe_mode"}, role="admin")
    assert res["ok"]
    assert sent(rig, dev)[-1]["device_action"]["action"] == "clear_safe_mode"
    assert (await rig.api.request("device_action", {"device_id": dev, "action": "format"}))["error"]["type"] == "validation"


async def test_late_job_and_recovery(rig):
    dev, plant = await ready_plant(rig)
    rig.clock.advance(901)
    await rig.hub.tick()
    await rig.api.settle()
    assert rig.api.state["state/devices"][0]["status"] == "late"
    await device_report(rig, dev)
    assert rig.api.state["state/devices"][0]["status"] == "online"


async def test_zigbee_down_raises_alert_and_suspends_late(rig):
    dev, plant = await ready_plant(rig)
    await rig.z2m.t.publish("zigbee2mqtt/bridge/state", b'{"state":"offline"}', retain=True)
    await rig.api.settle()
    rig.clock.advance(400)
    await rig.hub.tick()
    await rig.api.settle()
    assert [a["kind"] for a in rig.api.state["state/alerts_open"]] == ["zigbee_offline"]
    assert rig.api.state["state/devices"][0]["status"] == "online"      # silence proves nothing now
    await rig.z2m.t.publish("zigbee2mqtt/bridge/state", b'{"state":"online"}', retain=True)
    await rig.api.settle()
    await rig.hub.tick()
    await rig.api.settle()
    assert rig.api.state["state/alerts_open"] == []


async def test_commands_are_not_sent_while_zigbee_is_down(rig):
    dev, plant = await ready_plant(rig)
    await rig.z2m.t.publish("zigbee2mqtt/bridge/state", b'{"state":"offline"}', retain=True)
    await rig.api.settle()
    n = len(sent(rig, dev))
    await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5})
    assert len(sent(rig, dev)) == n
    await rig.z2m.t.publish("zigbee2mqtt/bridge/state", b'{"state":"online"}', retain=True)
    await rig.api.settle()
    assert "pump_run" in sent(rig, dev)[-1]


def test_pump_limits_match_the_firmware_ceiling():
    import pytest
    from mc_hub.services import commands, config_sync, domain
    from mc_hub.errors import HubError
    assert commands.HARD_LIMIT_S == 300 and domain.MAX_WATER_S == 300
    board = {"name": "carrier-v1", "ports": [{"id": "P3", "roles": ["moisture", "pump"]}]}

    def slot(**kw):
        return {"slots": [{"slot": 2, "module": "pump", "port": "P3", **kw}]}

    config_sync.validate(slot(max_run_s=300, min_pause_s=65535), board)
    with pytest.raises(HubError):
        config_sync.validate(slot(max_run_s=301), board)
    with pytest.raises(HubError):
        config_sync.validate(slot(min_pause_s=65536), board)


async def test_report_now_is_a_device_action_that_reaches_the_module_even_in_safe_mode(rig):
    dev, plant = await ready_plant(rig)
    res = await rig.api.request("device_action", {"device_id": dev, "action": "report_now"})   # no admin needed
    assert res["ok"], res
    assert sent(rig, dev)[-1]["device_action"]["action"] == "report_now"
    await device_report(rig, dev, status="safe_mode", safe_reason="crash_loop")
    res = await rig.api.request("device_action", {"device_id": dev, "action": "report_now"})
    assert res["ok"] and sent(rig, dev)[-1]["device_action"]["action"] == "report_now"
