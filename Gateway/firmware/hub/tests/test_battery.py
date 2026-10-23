"""Battery detection in the hub (Gateway/specs.md 13.1)."""
import pytest

from mc_hub.params import BATTERY
from mc_hub.services import battery

from .conftest import add_device, ack, device_report, ready_device, ready_plant, sent


# ---- the pure parts --------------------------------------------------------------------------------

CURVE = BATTERY["percent_curves"][battery.CHEMISTRY]     # the numbers are owned by interface.yaml, not by this test


def test_percent_follows_the_configured_curve_and_interpolates():
    assert CURVE == sorted(CURVE, reverse=True), "the curve is listed from full to empty"
    (top_mv, top_pct), (bottom_mv, bottom_pct) = CURVE[0], CURVE[-1]
    assert battery.percent(top_mv + 100) == top_pct == 100
    assert battery.percent(bottom_mv - 100) == bottom_pct == 0
    for mv, pct in CURVE:
        assert battery.percent(mv) == pct, f"{mv} mV is a point of the curve"
    for (hi_mv, hi_pct), (lo_mv, lo_pct) in zip(CURVE, CURVE[1:]):
        mid = battery.percent((hi_mv + lo_mv) // 2)
        assert lo_pct <= mid <= hi_pct
        assert abs(mid - (hi_pct + lo_pct) / 2) <= 1.5, "halfway in voltage is about halfway in percent"
    values = [battery.percent(mv) for mv in range(bottom_mv - 50, top_mv + 51, 10)]
    assert values == sorted(values), "monotonic"


def test_state_from_voltage_for_a_module_without_batt_state():
    assert battery.state_from(0, 3600, 3400) == "absent"
    assert battery.state_from(3900, 3600, 3400) == "ok"
    assert battery.state_from(3600, 3600, 3400) == "low"
    assert battery.state_from(3400, 3600, 3400) == "critical"


def test_calibration_maths_and_limits():
    assert battery.calibrate_permille(3800, 1000, 3990) == 1050
    assert battery.calibrate_permille(3990, 1050, 3800) == 1000          # undoes the previous correction
    with pytest.raises(ValueError, match="10 %"):
        battery.calibrate_permille(3000, 1000, 3500)
    with pytest.raises(ValueError):
        battery.calibrate_permille(0, 1000, 3800)


# ---- through the hub -------------------------------------------------------------------------------

async def battery_of(rig, dev):
    return next(d for d in rig.api.state["state/devices"] if d["id"] == dev)["battery"]


async def test_voltage_and_state_come_from_the_modules_millivolt_attributes(rig):
    dev = await ready_device(rig)
    await device_report(rig, dev, batt_mv=3900, batt_state="ok", voltage_mv=3900)
    b = await battery_of(rig, dev)
    assert b["mv"] == 3900 and b["state"] == "ok" and b["present"] and b["percent"] is not None
    assert next(d for d in rig.api.state["state/devices"] if d["id"] == dev)["voltage_mv"] == 3900


async def test_a_module_with_only_the_standard_attribute_still_works(rig):
    dev = await ready_device(rig)
    await device_report(rig, dev, voltage_mv=3500)           # 100 mV units times 100, as the converter publishes it
    b = await battery_of(rig, dev)
    assert b["mv"] == 3500 and b["state"] == "low"            # derived from the installation thresholds


async def test_no_cell_is_absent_without_percentage_or_alert(rig):
    dev = await ready_device(rig)
    await device_report(rig, dev, batt_mv=0, batt_state="absent", voltage_mv=0)
    b = await battery_of(rig, dev)
    assert b == {"mv": 0, "percent": None, "state": "absent", "present": False, "calibrated": False,
                 "cal_permille": 1000}
    assert rig.api.state["state/alerts_open"] == []


async def test_percentage_is_smoothed_over_the_last_reports(rig):
    dev = await ready_device(rig)
    for mv in (3900, 3900, 3500, 3900, 3900):                 # one dip
        await device_report(rig, dev, batt_mv=mv, batt_state="ok")
    assert (await battery_of(rig, dev))["percent"] == battery.percent(3900)


async def test_percentage_is_null_when_the_last_report_is_old(rig):
    dev = await ready_device(rig)
    await device_report(rig, dev, batt_mv=3900, batt_state="ok")
    assert (await battery_of(rig, dev))["percent"] is not None
    rig.clock.advance(3 * 300 + 10)                           # the status job marks the device late: the snapshot is rebuilt
    await rig.hub.tick()
    await rig.api.settle()
    d = next(x for x in rig.api.state["state/devices"] if x["id"] == dev)
    assert d["status"] in ("late", "offline")
    assert d["battery"]["mv"] == 3900 and d["battery"]["percent"] is None   # the voltage stays, the estimate does not


async def test_low_opens_a_warning_and_critical_a_second_alert_and_recovery_resolves_them(rig):
    dev = await ready_device(rig)
    await device_report(rig, dev, batt_mv=3550, batt_state="low", event={"n": 1, "code": "low_battery", "slot": None, "arg": 3550})
    kinds = [a["kind"] for a in rig.api.state["state/alerts_open"]]
    assert kinds == ["battery_low"]
    await device_report(rig, dev, batt_mv=3350, batt_state="critical", event={"n": 2, "code": "battery_critical", "slot": None, "arg": 3350})
    alerts = rig.api.state["state/alerts_open"]
    assert sorted(a["kind"] for a in alerts) == ["battery_critical", "battery_low"]
    assert next(a for a in alerts if a["kind"] == "battery_critical")["severity"] == "critical"
    await device_report(rig, dev, batt_mv=3550, batt_state="low")
    assert [a["kind"] for a in rig.api.state["state/alerts_open"]] == ["battery_low"]
    await device_report(rig, dev, batt_mv=3800, batt_state="ok")
    assert rig.api.state["state/alerts_open"] == []


async def test_installation_thresholds_are_validated_and_pushed_to_every_device(rig):
    dev = await ready_device(rig)
    bad = await rig.api.request("installation_set", {"battery_low_mv": 3400, "battery_critical_mv": 3500})
    assert bad["error"]["type"] == "validation"
    ok = await rig.api.request("installation_set", {"battery_low_mv": 3700, "battery_critical_mv": 3450})
    assert ok["ok"]
    d = next(x for x in rig.api.state["state/devices"] if x["id"] == dev)
    assert d["desired_config"]["batt_low_mv"] == 3700 and d["desired_config"]["batt_critical_mv"] == 3450
    assert d["desired_rev"] == 3 and d["config_sync"] == "pending"
    last = sent(rig, dev)[-1]["config"]
    assert last["batt_low_mv"] == 3700 and last["batt_critical_mv"] == 3450 and last["rev"] == 3
    inst = rig.api.state["state/installation"]
    assert (inst["battery_low_mv"], inst["battery_critical_mv"]) == (3700, 3450)


async def test_a_new_device_starts_with_the_installations_thresholds(rig):
    await rig.api.request("installation_set", {"battery_low_mv": 3700, "battery_critical_mv": 3450})
    dev = await add_device(rig)
    d = next(x for x in rig.api.state["state/devices"] if x["id"] == dev)
    assert d["desired_config"]["batt_low_mv"] == 3700 and d["desired_config"]["batt_critical_mv"] == 3450


async def test_an_editor_that_leaves_the_battery_out_keeps_thresholds_and_calibration(rig):
    dev = await ready_device(rig)
    await rig.api.request("installation_set", {"battery_low_mv": 3700, "battery_critical_mv": 3450})
    await device_report(rig, dev, cfg_rev=3, cfg_result="ok")
    res = await rig.api.request("device_config_put", {"device_id": dev, "base_rev": 3,
                                                      "config": {"report_interval_s": 120, "slots": []}})
    assert res["ok"], res
    d = next(x for x in rig.api.state["state/devices"] if x["id"] == dev)
    assert d["desired_config"]["batt_low_mv"] == 3700 and d["desired_config"]["batt_cal_permille"] == 1000


async def test_calibration_creates_a_revision_with_the_new_factor_and_refuses_far_off_values(rig):
    dev = await ready_device(rig)
    await device_report(rig, dev, batt_mv=3800, batt_state="ok")
    res = await rig.api.request("device_battery_calibrate", {"device_id": dev, "measured_mv": 3990})
    assert res["ok"] and res["body"]["cal_permille"] == 1050
    assert sent(rig, dev)[-1]["config"]["batt_cal_permille"] == 1050
    far = await rig.api.request("device_battery_calibrate", {"device_id": dev, "measured_mv": 5000})
    assert far["error"]["type"] == "validation" and "10 %" in far["error"]["detail"]


async def test_calibration_needs_a_voltage_to_calibrate_against(rig):
    dev = await ready_device(rig)
    await device_report(rig, dev, batt_mv=0, batt_state="absent", voltage_mv=0)
    res = await rig.api.request("device_battery_calibrate", {"device_id": dev, "measured_mv": 3800})
    assert res["error"]["type"] == "validation"


async def test_a_pump_run_refused_for_the_battery_is_a_failed_command_with_the_reason(rig):
    dev, plant = await ready_plant(rig)
    res = await rig.api.request("water", {"plant_id": plant["id"], "seconds": 5})
    cmd = res["body"]["command"]
    zb = sent(rig, dev)[-1]["pump_run"]["cmd_id"]
    await ack(rig, dev, zb, "rejected", 1, reason="battery_low")
    q = await rig.api.request("query/command", {"command_id": cmd["id"]})
    assert q["body"]["command"]["status"] == "failed" and q["body"]["command"]["reason"] == "battery_low"


async def test_a_rule_skips_with_battery_critical_instead_of_sending_a_command(rig):
    dev, plant = await ready_plant(rig)
    await rig.api.request("rule_create", {"plant_id": plant["id"], "threshold": 30, "water_s": 10,
                                          "cooldown_s": 3600, "max_per_day": 3})
    await device_report(rig, dev, batt_mv=3350, batt_state="critical", v0=10.0)
    n_before = len([p for p in sent(rig, dev) if "pump_run" in p])
    await device_report(rig, dev, batt_mv=3350, batt_state="critical", v0=9.0)
    assert len([p for p in sent(rig, dev) if "pump_run" in p]) == n_before == 0
    ex = await rig.api.request("query/rule_executions", {"rule_id": rig.api.state["state/rules"][0]["id"]})
    assert ex["body"]["items"][0]["skip_reason"] == "battery_critical"
