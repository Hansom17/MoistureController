from sqlalchemy import select

from mc_hub.db.models import Command, RuleExecution
from mc_hub.services.rules_engine import RuleContext, RuleSpec, evaluate, in_quiet_hours, start_of_day

from .conftest import ack, device_report, ready_plant, sent

RULE = {"threshold": 30, "water_s": 10, "cooldown_s": 3600, "max_per_day": 2}


async def executions(rig):
    async with rig.sessions() as s:
        return (await s.execute(select(RuleExecution).order_by(RuleExecution.id))).scalars().all()


async def make_rule(rig, plant, **kw):
    return (await rig.api.request("rule_create", {"plant_id": plant["id"], **RULE, **kw}))["body"]["rule"]


def spec(**kw):
    base = dict(id="r", plant_id="p", enabled=True, threshold=30, water_s=10, cooldown_s=3600, max_per_day=2)
    return RuleSpec(**(base | kw))


def ctx(**kw):
    base = dict(now=1_800_000_000, timezone="UTC", has_pump=True, last_rule_cmd_at=None, rule_cmds_today=0,
                pending_command=False)
    return RuleContext(**(base | kw))


def test_engine_decisions():
    assert evaluate(spec(), 50, "ok", ctx()) is None
    assert evaluate(spec(enabled=False), 10, "ok", ctx()) is None
    assert evaluate(spec(), 10, "ok", ctx()).decision == "water"
    assert evaluate(spec(), None, "ok", ctx()).skip_reason == "sensor_error"
    assert evaluate(spec(), 10, "no_signal", ctx()).skip_reason == "sensor_error"
    assert evaluate(spec(), 10, "ok", ctx(has_pump=False)).skip_reason == "no_pump"
    assert evaluate(spec(), 10, "ok", ctx(last_rule_cmd_at=1_800_000_000 - 60)).skip_reason == "cooldown"
    assert evaluate(spec(), 10, "ok", ctx(rule_cmds_today=2)).skip_reason == "daily_limit"
    assert evaluate(spec(), 10, "ok", ctx(pending_command=True)).skip_reason == "pending_command"
    assert evaluate(spec(), 10, "ok", ctx(clock_synced=False)).skip_reason == "clock_not_synced"


def test_quiet_hours_span_midnight_and_use_timezone():
    r = spec(quiet_from="22:00", quiet_to="07:00")
    night = start_of_day(1_800_000_000, "UTC") + 23 * 3600
    noon = start_of_day(1_800_000_000, "UTC") + 12 * 3600
    assert in_quiet_hours(r, night, "UTC") and not in_quiet_hours(r, noon, "UTC")
    assert not in_quiet_hours(r, night, "Asia/Tokyo")     # 23:00 UTC is 08:00 in Tokyo


async def test_dry_reading_waters_the_plant(rig):
    dev, plant = await ready_plant(rig)
    await make_rule(rig, plant)
    await device_report(rig, dev, v0=20)
    cmd = [m for m in sent(rig, dev) if "pump_run" in m][-1]["pump_run"]
    assert cmd["seconds"] == 10 and cmd["slot"] == 2
    ex = await executions(rig)
    assert [(e.decision, e.skip_reason) for e in ex] == [("water", None)]
    async with rig.sessions() as s:
        c = (await s.execute(select(Command))).scalar_one()
    assert c.source == "rule" and c.rule_id and c.plant_id == plant["id"] and c.created_by is None


async def test_wet_reading_does_nothing(rig):
    dev, plant = await ready_plant(rig)
    await make_rule(rig, plant)
    await device_report(rig, dev, v0=60)
    assert await executions(rig) == [] and not [m for m in sent(rig, dev) if "pump_run" in m]


async def test_cooldown_pending_and_daily_limit(rig):
    dev, plant = await ready_plant(rig)
    await make_rule(rig, plant, cooldown_s=60, max_per_day=2)
    await device_report(rig, dev, v0=20)                       # waters
    await device_report(rig, dev, v0=20)                       # run still open (cooldown comes first)
    cid = [m for m in sent(rig, dev) if "pump_run" in m][-1]["pump_run"]["cmd_id"]
    await ack(rig, dev, cid, "running", 1, ends_in_s=10)
    await ack(rig, dev, cid, "done", 2)
    rig.clock.advance(30)
    await device_report(rig, dev, v0=20)                       # inside the cooldown
    rig.clock.advance(700)                                     # cooldown and min pause over
    await device_report(rig, dev, v0=20)                       # waters again (2nd of the day)
    cid2 = [m for m in sent(rig, dev) if "pump_run" in m][-1]["pump_run"]["cmd_id"]
    await ack(rig, dev, cid2, "running", 3, ends_in_s=10)
    await ack(rig, dev, cid2, "done", 4)
    rig.clock.advance(700)
    await device_report(rig, dev, v0=20)                       # daily limit
    assert [(e.decision, e.skip_reason) for e in await executions(rig)] == [
        ("water", None), ("skip", "cooldown"), ("skip", "cooldown"), ("water", None), ("skip", "daily_limit")]


async def test_sensor_error_is_recorded_and_notified(rig):
    dev, plant = await ready_plant(rig)
    await rig.api.request("installation_set", {"telegram": {"token": "T", "chat_id": "42"}})
    await make_rule(rig, plant, notify_channels=["telegram"], notify_on=["skipped_problem"])
    await device_report(rig, dev, v0=None, slot0_error="no_signal")
    assert [(e.decision, e.skip_reason) for e in await executions(rig)] == [("skip", "sensor_error")]
    assert rig.tg_sent == [("T", "42", "Ficus: rule skipped (sensor_error)")]


async def test_notifications_by_rule_channel(rig):
    dev, plant = await ready_plant(rig)
    await rig.api.request("installation_set", {"telegram": {"token": "T", "chat_id": "42"}})
    await make_rule(rig, plant, notify_channels=["app", "telegram"], notify_on=["watered", "failed"])
    await device_report(rig, dev, v0=20)
    assert len(rig.tg_sent) == 1 and "watering 10 s" in rig.tg_sent[0][2]
    notes = [e for e in rig.api.events if e["kind"] == "notification"]
    assert len(notes) == 1 and "watering 10 s" in notes[0]["body"]["text"]
    cid = [m for m in sent(rig, dev) if "pump_run" in m][-1]["pump_run"]["cmd_id"]
    await ack(rig, dev, cid, "failed", 1, reason="hw_error")
    assert any("Watering failed (hw_error)" in t[2] for t in rig.tg_sent)


async def test_alerts_go_to_telegram_only_when_configured(rig):
    dev, plant = await ready_plant(rig)
    await rig.z2m.availability(dev, "offline")
    await rig.api.settle()
    assert rig.tg_sent == []
    await rig.api.request("installation_set", {"telegram": {"token": "T", "chat_id": "42", "kinds": ["device_safe_mode"]}})
    await rig.z2m.availability(dev, "online")
    await device_report(rig, dev)
    await rig.z2m.availability(dev, "offline")
    await rig.api.settle()
    assert rig.tg_sent == []                                      # offline is not in the selected kinds
    await device_report(rig, dev, status="safe_mode", safe_reason="crash_loop")
    assert len(rig.tg_sent) == 1 and "safe mode" in rig.tg_sent[0][2]


async def test_telegram_failure_does_not_break_the_hub(rig):
    async def boom(*a):
        raise RuntimeError("no internet")
    rig.hub.notifier.send = boom
    dev, plant = await ready_plant(rig)
    await rig.api.request("installation_set", {"telegram": {"token": "T", "chat_id": "42"}})
    await make_rule(rig, plant, notify_channels=["telegram"], notify_on=["watered"])
    await device_report(rig, dev, v0=20)
    assert [m for m in sent(rig, dev) if "pump_run" in m]
    assert rig.api.state["status/hub"]["state"] == "online"
