from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from mc_core import ids, pins
from mc_core.commands import Actuator, CommandRejected, check_pump_run, expiry
from mc_core.contract import topics
from mc_core.contract.device import ConfigDesired
from mc_core.rules import Decision, RuleContext, RuleSpec, evaluate, start_of_day


# --- ids -----------------------------------------------------------------------


def test_ids_have_contract_shape():
    assert len(ids.new_device_id()) == 19 and ids.new_device_id().startswith("mc-")
    assert ids.new_gateway_id().startswith("gw-") and len(ids.new_gateway_id()) == 19
    assert len(ids.new_id()) == 26
    code = ids.new_user_code()
    assert len(code) == 9 and code[4] == "-"
    assert ids.normalize_user_code(code.lower()) == code.replace("-", "")
    assert len(ids.new_psk()) == 64


# --- topics --------------------------------------------------------------------


def test_topic_parse():
    t = topics.parse("mc/v1/mc-abc/cmd/ack")
    assert (t.id, t.suffix) == ("mc-abc", "cmd/ack")
    assert topics.parse("mc/hub/v1/hub-x/up/state") is None
    assert topics.parse("other/topic") is None


# --- pins ----------------------------------------------------------------------


def cfg(*slots) -> ConfigDesired:
    return ConfigDesired(rev=2, wake_interval_s=600, slots=list(slots))


def codes(c: ConfigDesired) -> list[str]:
    return [e.code for e in pins.validate_config(c)]


def test_valid_config():
    c = cfg(
        {"slot": 0, "module": "moisture_capacitive", "pin": 34},
        {"slot": 1, "module": "pump_relay", "pin": 25, "max_run_s": 60},
        {"slot": 2, "module": "sht3x", "addr": 0x44},
    )
    assert codes(c) == []


def test_pump_on_input_only_pin():
    assert codes(cfg({"slot": 0, "module": "pump_relay", "pin": 34, "max_run_s": 10})) == [
        "pin_not_output"
    ]


def test_reserved_and_conflict():
    c = cfg(
        {"slot": 0, "module": "moisture_capacitive", "pin": 6},
        {"slot": 1, "module": "moisture_capacitive", "pin": 32},
        {"slot": 2, "module": "water_level_float", "pin": 32},
    )
    assert codes(c) == ["pin_reserved", "pin_conflict"]


def test_max_run_above_hard_limit():
    c = cfg({"slot": 0, "module": "pump_relay", "pin": 25, "max_run_s": 301})
    assert codes(c) == ["out_of_range"]


def test_board_description_lists_modules():
    desc = pins.board_description()
    assert {m["module"] for m in desc["modules"]} == set(pins.MODULES)


# --- commands ------------------------------------------------------------------


PUMP = Actuator(slot=2, max_run_s=60, min_pause_s=600, hard_limit_s=300)


def test_expiry_minimum_15_min():
    assert expiry(1000, 60) == 1000 + 900
    assert expiry(1000, 3600) == 1000 + 7200


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"seconds": 10, "actuator": None}, "slot_not_actuator"),
        ({"seconds": 61, "actuator": PUMP}, "safety_limit"),
        ({"seconds": 0, "actuator": PUMP}, "safety_limit"),
        ({"seconds": 10, "actuator": PUMP, "last_run_ended_at": 9_700}, "safety_limit"),
        ({"seconds": 10, "actuator": PUMP, "pending": True}, "busy"),
    ],
)
def test_pump_checks_reject(kwargs, code):
    with pytest.raises(CommandRejected) as e:
        check_pump_run(now=10_000, **kwargs)
    assert e.value.code == code


def test_pump_check_passes():
    check_pump_run(10, PUMP, now=10_000, last_run_ended_at=9_000)


# --- rules ---------------------------------------------------------------------

TZ = "Europe/Berlin"
RULE = RuleSpec(
    id="r", plant_id="p", enabled=True, threshold=30, water_s=10,
    cooldown_s=6 * 3600, max_per_day=2, quiet_from="22:00", quiet_to="07:00",
)


def at(hour: int) -> int:
    return int(datetime(2026, 9, 28, hour, 0, tzinfo=ZoneInfo(TZ)).timestamp())


def ctx(**over) -> RuleContext:
    base = dict(now=at(12), timezone=TZ, has_pump=True, last_rule_cmd_at=None,
                rule_cmds_today=0, pending_command=False)
    return RuleContext(**{**base, **over})


def test_rule_waters_below_threshold():
    assert evaluate(RULE, 25, None, ctx()) == Decision("water")


def test_rule_silent_above_threshold_or_disabled():
    assert evaluate(RULE, 35, None, ctx()) is None
    assert evaluate(RuleSpec(**{**RULE.__dict__, "enabled": False}), 10, None, ctx()) is None


@pytest.mark.parametrize(
    ("value", "error", "over", "reason"),
    [
        (None, "no_signal", {}, "sensor_error"),
        (25, None, {"has_pump": False}, "no_pump"),
        (25, None, {"now": at(23)}, "quiet_hours"),
        (25, None, {"now": at(5)}, "quiet_hours"),
        (25, None, {"last_rule_cmd_at": at(12) - 3600}, "cooldown"),
        (25, None, {"rule_cmds_today": 2}, "daily_limit"),
        (25, None, {"pending_command": True}, "pending_command"),
    ],
)
def test_rule_skips(value, error, over, reason):
    assert evaluate(RULE, value, error, ctx(**over)) == Decision("skip", reason)


def test_start_of_day_uses_household_timezone():
    assert start_of_day(at(12), TZ) == at(0)
