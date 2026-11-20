"""A module in deep sleep (PlantModule/specs.md 18): status, check-in sender, command lifetime, validation."""
from sqlalchemy import select

from mc_hub.db.models import Command

from .conftest import CFG, device_report, ready_device, sent


async def deep_device(rig, interval=300, awake=5):
    dev = await ready_device(rig)
    cfg = {**CFG, "power_mode": 2, "report_interval_s": interval, "awake_s": awake}
    res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 2, "config": cfg})
    assert res["ok"], res
    await device_report(rig, dev, cfg_rev=3, cfg_result="ok")
    return dev


async def status(rig):
    return rig.api.state["state/devices"][0]["status"]


async def test_a_module_that_sleeps_is_sleeping_between_check_ins_not_late(rig):
    dev = await deep_device(rig)
    assert await status(rig) == "online"
    rig.clock.advance(30)                      # the awake window (5 s) is long over
    await rig.hub.tick()
    await rig.api.settle()
    assert await status(rig) == "sleeping"
    await device_report(rig, dev)              # the next check-in
    assert await status(rig) == "online"


async def test_a_sleeper_that_misses_three_intervals_is_late(rig):
    dev = await deep_device(rig)
    rig.clock.advance(30)
    await rig.hub.tick()
    rig.clock.advance(901)
    await rig.hub.tick()
    await rig.api.settle()
    assert await status(rig) == "late"
    await device_report(rig, dev)
    assert await status(rig) == "online"


async def test_a_module_that_stays_awake_never_becomes_sleeping(rig):
    dev = await ready_device(rig)              # always on
    rig.clock.advance(60)
    await rig.hub.tick()
    await rig.api.settle()
    assert await status(rig) == "online"


async def test_commands_wait_for_the_check_in_and_go_out_right_after_the_report(rig):
    dev = await deep_device(rig)
    rig.clock.advance(30)
    await rig.hub.tick()
    await rig.api.settle()
    assert await status(rig) == "sleeping"
    before = len(sent(rig, dev))
    res = await rig.api.request("device_action", {"device_id": dev, "action": "identify"})
    assert res["ok"], res                      # accepted: queued until the module listens
    await rig.hub.tick()
    await rig.api.settle()
    assert len(sent(rig, dev)) == before, "nothing is sent to a sleeping module"
    await device_report(rig, dev)              # it wakes, reports, listens for awake_s
    actions = [p for p in sent(rig, dev)[before:] if "device_action" in p]
    assert len(actions) == 1 and actions[0]["device_action"]["action"] == "identify"


async def test_nothing_is_sent_after_the_window_even_before_the_status_flips(rig):
    dev = await deep_device(rig, awake=5)
    rig.clock.advance(8)                       # the window is closed, the tick has not run yet
    before = len(sent(rig, dev))
    await rig.api.request("device_action", {"device_id": dev, "action": "identify"})
    await rig.api.settle()
    assert len(sent(rig, dev)) == before


async def test_a_command_for_a_sleeper_lives_at_least_two_report_intervals(rig):
    dev = await deep_device(rig, interval=1800)
    await rig.api.request("device_action", {"device_id": dev, "action": "identify"})
    async with rig.sessions() as s:
        c = (await s.execute(select(Command).where(Command.device_id == dev).order_by(Command.created_at.desc()))).scalars().first()
    assert c.exp - c.created_at == 2 * 1800 + 60


async def test_deep_sleep_needs_an_interval_longer_than_its_awake_window(rig):
    dev = await ready_device(rig)
    for interval, awake in ((20, 5), (35, 30), (30, 20)):
        res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 2, "config": {
            **CFG, "power_mode": 2, "report_interval_s": interval, "awake_s": awake}})
        assert res["error"]["type"] == "validation", (interval, awake)
    res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 2, "config": {
        **CFG, "power_mode": 2, "report_interval_s": 60, "awake_s": 5}})
    assert res["ok"], res
    res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 3, "config": {
        **CFG, "power_mode": 1, "report_interval_s": 10}})
    assert res["ok"], res                      # the rule is for deep sleep only
