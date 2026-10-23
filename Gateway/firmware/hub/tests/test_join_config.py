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
