"""A device that appears before it is interviewed still gets its initial configuration once it is supported."""
from .conftest import plant_entry


def entry_without_model():
    return {"ieee_address": "0x00124b0002", "friendly_name": "0x00124b0002", "type": "EndDevice",
            "supported": False, "interview_state": "IN_PROGRESS"}


async def device(rig):
    return rig.api.state["state/devices"][0]


async def test_a_device_seen_before_its_interview_gets_the_initial_configuration_when_it_is_known(rig):
    await rig.z2m.devices([entry_without_model()])
    await rig.api.settle()
    d = await device(rig)
    assert d["desired_rev"] == 0 and d["desired_config"] is None      # nothing to configure yet
    await rig.z2m.devices([plant_entry(ieee="0x00124b0002", friendly="0x00124b0002")])   # interviewed, model known
    await rig.api.settle()
    d = await device(rig)
    assert d["desired_rev"] == 1 and d["desired_config"]["slots"] == []
    assert d["desired_config"]["batt_low_mv"] == 3600 and d["status"] == "ready"


async def test_an_unsupported_model_never_gets_a_configuration(rig):
    await rig.z2m.devices([plant_entry(ieee="0x00124b0003", friendly="0x00124b0003", model="OTHER")])
    await rig.api.settle()
    d = await device(rig)
    assert d["status"] == "unsupported" and d["desired_config"] is None


async def test_a_known_device_is_not_given_a_second_initial_configuration(rig):
    await rig.z2m.devices([plant_entry()])
    await rig.api.settle()
    rev = (await device(rig))["desired_rev"]
    await rig.z2m.devices([plant_entry()])
    await rig.api.settle()
    assert (await device(rig))["desired_rev"] == rev == 1


async def test_the_power_settings_are_part_of_every_configuration_and_validated(rig):
    from .conftest import CFG, ready_device
    dev = await ready_device(rig)                               # revision 2, reported back by the module
    cfg = (await device(rig))["desired_config"]
    assert [cfg[k] for k in ("power_mode", "poll_interval_ms", "awake_s")] == [0, 3000, 5]   # always on
    res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 2,
                                                      "config": {**CFG, "power_mode": 1, "poll_interval_ms": 2000, "awake_s": 8}})
    assert res["ok"], res
    cfg = (await device(rig))["desired_config"]
    assert [cfg[k] for k in ("power_mode", "poll_interval_ms", "awake_s")] == [1, 2000, 8]
    for bad in ({"power_mode": 3}, {"poll_interval_ms": 100}, {"awake_s": 31}):
        res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 3, "config": {**CFG, **bad}})
        assert res["error"]["type"] == "validation", bad


async def test_an_editor_that_does_not_send_the_power_settings_keeps_them(rig):
    from .conftest import CFG, ready_device
    dev = await ready_device(rig)
    await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 2,
                                                "config": {**CFG, "power_mode": 2, "awake_s": 9}})
    body = {k: v for k, v in CFG.items() if k not in ("power_mode", "poll_interval_ms", "awake_s")}
    res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 3, "config": body})
    assert res["ok"], res
    cfg = (await device(rig))["desired_config"]
    assert [cfg[k] for k in ("power_mode", "poll_interval_ms", "awake_s")] == [2, 3000, 9]


async def test_a_new_device_whose_module_carries_an_old_configuration_gets_the_clean_one_on_top(rig):
    from .conftest import add_device, device_report, sent
    dev = await add_device(rig)
    d = await device(rig)
    assert d["desired_rev"] == 1
    await device_report(rig, dev, cfg_rev=7, cfg_result="ok")          # the module still runs revision 7 of an earlier life
    d = await device(rig)
    assert d["desired_rev"] == 8 and d["desired_config"]["slots"] == [] and d["desired_config"]["rev"] == 8
    pushed = [p["config"] for p in sent(rig, dev) if "config" in p]
    assert pushed and pushed[-1]["rev"] == 8, "the clean configuration goes to the module, above its own revision"
    await device_report(rig, dev, cfg_rev=8, cfg_result="ok")
    d = await device(rig)
    assert d["reported_rev"] == 8 and d["config_sync"] == "in_sync"


async def test_a_configuration_the_user_made_is_never_replaced_by_the_adoption(rig):
    from .conftest import device_report, ready_device
    dev = await ready_device(rig)                                       # revision 2 is the user's
    await device_report(rig, dev, cfg_rev=9, cfg_result="ok")
    assert (await device(rig))["desired_rev"] == 2


async def test_a_removal_zigbee2mqtt_refuses_is_repeated_by_force(rig):
    import json

    def published(topic):
        return [json.loads(p) for t, p in rig.broker.log if t == topic]

    await rig.z2m.t.publish("zigbee2mqtt/bridge/response/device/remove",
                            b'{"data":{"id":"0x00124b0001","block":false,"force":false},"status":"error","error":"Failed to remove"}')
    await rig.api.settle()
    assert published("zigbee2mqtt/bridge/request/device/remove")[-1] == {"id": "0x00124b0001", "force": True}
    n = len(published("zigbee2mqtt/bridge/request/device/remove"))
    await rig.z2m.t.publish("zigbee2mqtt/bridge/response/device/remove",
                            b'{"data":{"id":"0x00124b0001","block":false,"force":true},"status":"error","error":"still no"}')
    await rig.api.settle()
    assert len(published("zigbee2mqtt/bridge/request/device/remove")) == n, "no loop"
