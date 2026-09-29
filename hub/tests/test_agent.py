import json
import time

import pytest

from mc_core.commands import CommandRejected
from mc_core.contract import gateway as g
from mc_hub.agent import Agent
from mc_hub.config import HubConfig
from mc_hub.store import Store

GW = "gw-test0000000000000"
DEV = "mc-dev0000000000000a"
PLANT, RULE = "P1", "R1"
NOW = 1_790_000_000  # 2026-09-21 ~14:13 Berlin


class Recorder:
    """Local broker publishes (device commands/configs)."""

    def __init__(self):
        self.sent: list[tuple[str, dict | str, bool]] = []

    async def __call__(self, topic, body, retain):
        try:
            body = json.loads(body)
        except ValueError:
            pass
        self.sent.append((topic, body, retain))

    def topics(self):
        return [t for t, _, _ in self.sent]


def snapshot(rev=1, rule_state=None, **rule):
    return {
        "t": "snapshot", "id": f"S{rev}", "rev": rev, "household_id": "H",
        "timezone": "Europe/Berlin", "settings": {"battery_low_mv": 3500},
        "devices": [{"id": DEV, "adapter": "esp32-mqtt", "wake_interval_s": 600,
                     "actuators": [{"slot": 2, "max_run_s": 60, "min_pause_s": 0}],
                     "limits": {"max_run_s_hard": 300, "slots_max": 6}}],
        "plants": [{"id": PLANT, "sensor": {"device": DEV, "slot": 0},
                    "pump": {"device": DEV, "slot": 2}}],
        "rules": [{"id": RULE, "plant_id": PLANT, "enabled": True, "threshold": 30.0,
                   "water_s": 10, "cooldown_s": 3600, "max_per_day": 2, "quiet_from": None,
                   "quiet_to": None, **rule}],
        "rule_state": rule_state or [],
    }


def telemetry(seq, value):
    return json.dumps({"seq": seq, "ts": NOW, "cfg_rev": 1,
                       "readings": [{"slot": 0, "type": "soil_moisture", "value": value}],
                       "health": {"batt_mv": 3900, "rssi": -60, "wake": "timer"}}).encode()


@pytest.fixture
def clock():
    return {"t": NOW}


@pytest.fixture
def agent(tmp_path, clock):
    cfg = HubConfig(data_dir=tmp_path, lan_host="192.168.1.20")
    a = Agent(cfg, Store(tmp_path / "hub.db"), Recorder(), clock=lambda: clock["t"])
    a.enrolled(GW, "c" * 43)
    return a


def outbox(agent, t=None):
    msgs = agent.store.outbox_peek(1000)
    return [m for m in msgs if t is None or m["t"] == t]


async def device(agent, suffix, payload):
    await agent.on_message(f"mc/v1/{DEV}/{suffix}",
                           payload if isinstance(payload, bytes) else json.dumps(payload).encode())


def test_enrollment_stores_credential(agent, tmp_path):
    assert agent.gateway_id == GW
    cred = tmp_path / "secrets" / "credential"
    assert cred.read_text() == "c" * 43 and oct(cred.stat().st_mode)[-3:] == "600"


def test_every_up_message_is_valid_and_sequenced(agent):
    agent.apply_snapshot(snapshot())
    agent.apply_keys({"t": "keys", "id": "K1", "rev": 1,
                      "devices": [{"id": DEV, "adapter": "esp32-mqtt", "psk": "cd" * 32}]})
    return_msgs = outbox(agent)
    assert [m["seq"] for m in return_msgs] == list(range(1, len(return_msgs) + 1))
    for m in return_msgs:
        g.MESSAGES[m["t"]].model_validate(m)


async def test_device_messages_are_forwarded_unchanged(agent):
    await device(agent, "status", {"state": "online", "fw": "0.4.0", "boot": 3})
    await device(agent, "telemetry", telemetry(1, 50.0))
    msgs = outbox(agent, "device")
    assert [m["kind"] for m in msgs] == ["status", "telemetry"]
    assert msgs[1]["payload"]["readings"][0]["value"] == 50.0
    g.DeviceMessage.model_validate(msgs[1]).parsed()


def test_keys_write_psk_and_ack(agent, tmp_path):
    ack = agent.apply_keys({"t": "keys", "id": "K3", "rev": 3,
                            "devices": [{"id": DEV, "adapter": "esp32-mqtt", "psk": "cd" * 32}]})
    assert ack == {"t": "down_ack", "id": "K3", "result": "applied"}
    assert (tmp_path / "broker/psk").read_text() == f"{DEV}:{'cd' * 32}\n"
    assert outbox(agent, "gateway_state")[-1]["keys_rev"] == 3
    # Re-delivery after a reconnect: acked again, nothing rewritten.
    assert agent.apply_keys({"t": "keys", "id": "K3", "rev": 3, "devices": []})["result"] == \
        "applied"
    assert (tmp_path / "broker/psk").read_text().startswith(DEV)


def test_invalid_snapshot_is_rejected_and_old_one_kept(agent):
    agent.apply_snapshot(snapshot(rev=5))
    ack = agent.apply_snapshot({"t": "snapshot", "id": "S6", "rev": 6})
    assert ack["result"] == "rejected" and agent.snapshot.rev == 5


async def test_dry_reading_waters_and_reports_in_order(agent):
    agent.apply_snapshot(snapshot())
    await device(agent, "telemetry", telemetry(1, 22.0))
    types = [m["t"] for m in outbox(agent)]
    assert types.index("command_created") < types.index("rule_exec")
    created = outbox(agent, "command_created")[0]
    assert created["args"] == {"slot": 2, "seconds": 10} and created["exp"] == NOW + 1200
    assert agent._publish.sent[-1][0] == f"mc/v1/{DEV}/cmd"  # after the report
    report = outbox(agent, "rule_exec")[0]
    assert report["decision"] == "water" and report["command_id"] == created["id"]


async def test_pending_then_cooldown(agent, clock):
    agent.apply_snapshot(snapshot(cooldown_s=0))
    await device(agent, "telemetry", telemetry(1, 22.0))
    await device(agent, "telemetry", telemetry(2, 21.0))
    assert outbox(agent, "rule_exec")[-1]["skip_reason"] == "pending_command"

    cmd_id = outbox(agent, "command_created")[0]["id"]
    await device(agent, "cmd/ack", {"id": cmd_id, "status": "done", "ts": NOW})
    agent.apply_snapshot(snapshot(rev=2))  # cooldown 1 h again
    clock["t"] += 60
    await device(agent, "telemetry", telemetry(3, 20.0))
    assert outbox(agent, "rule_exec")[-1]["skip_reason"] == "cooldown"


async def test_snapshot_rule_state_limits_a_fresh_gateway(agent):
    agent.apply_snapshot(snapshot(rule_state=[
        {"plant_id": PLANT, "last_rule_cmd_at": NOW - 600, "rule_cmds_today": 1}]))
    await device(agent, "telemetry", telemetry(1, 22.0))
    assert outbox(agent, "rule_exec")[-1]["skip_reason"] == "cooldown"


async def test_no_rule_commands_without_synced_clock(agent):
    agent.cfg.assume_time_synced = False
    agent.apply_snapshot(snapshot())
    await device(agent, "telemetry", telemetry(1, 10.0))
    assert f"mc/v1/{DEV}/cmd" not in agent._publish.topics()
    assert outbox(agent, "rule_exec")[-1]["skip_reason"] == "clock_not_synced"


async def test_command_from_api_is_checked_again(agent):
    agent.apply_snapshot(snapshot())
    ok = await agent.apply_command({"t": "command", "id": "D1", "device": DEV, "command": {
        "id": "C1", "action": "pump.run", "exp": NOW + 900, "args": {"slot": 2, "seconds": 5}}})
    assert ok["result"] == "applied" and agent._publish.topics() == [f"mc/v1/{DEV}/cmd"]
    busy = await agent.apply_command({"t": "command", "id": "D2", "device": DEV, "command": {
        "id": "C2", "action": "pump.run", "exp": NOW + 900, "args": {"slot": 2, "seconds": 5}}})
    assert busy == {"t": "down_ack", "id": "D2", "result": "rejected", "error": "busy"}


async def test_config_desired_is_retained(agent):
    await agent.apply_config({"t": "config_desired", "id": "D3", "device": DEV,
                              "config": {"rev": 2, "wake_interval_s": 600, "slots": []}})
    topic, body, retain = agent._publish.sent[-1]
    assert topic == f"mc/v1/{DEV}/config/desired" and retain and body["rev"] == 2


async def test_local_manual_watering(agent):
    agent.apply_snapshot(snapshot())
    cmd_id = await agent.water_plant(PLANT, 15)
    report = outbox(agent, "command_created")[-1]
    assert report["id"] == cmd_id and report["source"] == "local" and "rule_id" not in report
    with pytest.raises(CommandRejected) as e:
        await agent.water_plant(PLANT, 999)
    assert e.value.code == "safety_limit"


def test_outbox_ack_and_reset(agent, tmp_path):
    agent.publish_state()
    agent.publish_state()
    agent.store.outbox_ack(1)
    assert [m["seq"] for m in outbox(agent)] == [2]
    agent.reset()
    assert agent.gateway_id is None
    assert not (tmp_path / "secrets/credential").exists()
    assert (tmp_path / "broker/psk").read_text() == ""
    assert outbox(agent)  # kept for inspection


def test_store_retention(tmp_path):
    store = Store(tmp_path / "x.db")
    store.add_reading(DEV, 0, 1, int(time.time()) - 8 * 86400, "soil_moisture", 1.0, None)
    store.cleanup()
    assert store.latest_reading(DEV, 0) is None
