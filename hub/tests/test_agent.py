import json
import time

import pytest

from mc_core.commands import CommandRejected
from mc_hub.agent import Agent
from mc_hub.config import HubConfig
from mc_hub.store import Store

HUB = "hub-test0000000000000"
DEV = "mc-dev0000000000000a"
PLANT, RULE = "P1", "R1"
NOW = 1_790_000_000  # a Monday, 2026-09-21 ~14:13 Berlin


class Recorder:
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

    def last(self, suffix):
        return next(b for t, b, _ in reversed(self.sent) if t.endswith(suffix))


def snapshot(rev=1, rule_state=None, **rule):
    return {
        "rev": rev, "household_id": "H", "timezone": "Europe/Berlin",
        "settings": {"battery_low_mv": 3500},
        "devices": [{"id": DEV, "wake_interval_s": 600,
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
    store = Store(tmp_path / "hub.db")
    a = Agent(cfg, store, Recorder(), clock=lambda: clock["t"])
    a.enrolled(HUB, "mqtt.example.com", 8883, "ab" * 32)
    return a


async def feed(agent, suffix, payload, hub=False):
    topic = f"mc/hub/v1/{HUB}/{suffix}" if hub else f"mc/v1/{DEV}/{suffix}"
    await agent.on_message(topic, payload if isinstance(payload, bytes) else
                           json.dumps(payload).encode())


def test_enrollment_writes_bridge_without_devices(agent, tmp_path):
    conf = (tmp_path / "broker/conf.d/bridge.conf").read_text()
    assert f"bridge_identity {HUB}" in conf and "address mqtt.example.com:8883" in conf
    assert f"topic mc/hub/v1/{HUB}/down/keys in 1" in conf
    assert "/cmd in 1" not in conf  # no devices yet


async def test_keys_write_psk_bridge_and_ack(agent, tmp_path):
    rec = agent._publish
    await feed(agent, "down/keys", {"rev": 3, "devices": [{"id": DEV, "psk": "cd" * 32}]},
               hub=True)
    assert (tmp_path / "broker/psk").read_text() == f"{DEV}:{'cd' * 32}\n"
    assert f"topic mc/v1/{DEV}/cmd in 1" in (tmp_path / "broker/conf.d/bridge.conf").read_text()
    assert rec.last("up/ack") == {"topic": "down/keys", "rev": 3, "result": "applied"}
    assert rec.last("up/state")["keys_rev"] == 3
    # Retained re-delivery after a reconnect: acked again, nothing rewritten.
    await feed(agent, "down/keys", {"rev": 3, "devices": []}, hub=True)
    assert (tmp_path / "broker/psk").read_text().startswith(DEV)


async def test_invalid_snapshot_is_rejected_and_old_one_kept(agent):
    await feed(agent, "down/snapshot", snapshot(rev=5), hub=True)
    await feed(agent, "down/snapshot", {"rev": 6, "household_id": "H"}, hub=True)
    assert agent._publish.last("up/ack")["result"] == "rejected"
    assert agent.snapshot.rev == 5


async def test_dry_reading_waters_and_reports_in_order(agent):
    await feed(agent, "down/snapshot", snapshot(), hub=True)
    await feed(agent, "telemetry", telemetry(1, 22.0))
    t = agent._publish.topics()
    up_cmd, local_cmd, rule_exec = (t.index(f"mc/hub/v1/{HUB}/up/cmd"),
                                    t.index(f"mc/v1/{DEV}/cmd"),
                                    t.index(f"mc/hub/v1/{HUB}/up/rule_exec"))
    assert up_cmd < local_cmd < rule_exec  # cloud knows the command before the device
    cmd = agent._publish.last("/cmd")
    assert cmd["args"] == {"slot": 2, "seconds": 10} and cmd["exp"] == NOW + 1200
    report = agent._publish.last("up/rule_exec")
    assert report["decision"] == "water" and report["command_id"] == cmd["id"]


async def test_pending_then_cooldown(agent, clock):
    await feed(agent, "down/snapshot", snapshot(cooldown_s=0), hub=True)
    await feed(agent, "telemetry", telemetry(1, 22.0))
    await feed(agent, "telemetry", telemetry(2, 21.0))
    assert agent._publish.last("up/rule_exec")["skip_reason"] == "pending_command"

    cmd_id = agent._publish.last("/cmd")["id"]
    await feed(agent, "cmd/ack", {"id": cmd_id, "status": "done", "ts": NOW})
    await feed(agent, "down/snapshot", snapshot(rev=2), hub=True)  # cooldown 1 h again
    clock["t"] += 60
    await feed(agent, "telemetry", telemetry(3, 20.0))
    assert agent._publish.last("up/rule_exec")["skip_reason"] == "cooldown"


async def test_snapshot_rule_state_limits_a_fresh_hub(agent):
    # A re-enrolled hub has no local history; the cloud's rule_state still counts.
    await feed(agent, "down/snapshot", snapshot(rule_state=[
        {"plant_id": PLANT, "last_rule_cmd_at": NOW - 600, "rule_cmds_today": 1}]), hub=True)
    await feed(agent, "telemetry", telemetry(1, 22.0))
    assert agent._publish.last("up/rule_exec")["skip_reason"] == "cooldown"


async def test_no_rule_commands_without_synced_clock(agent):
    agent.cfg.assume_time_synced = False
    await feed(agent, "down/snapshot", snapshot(), hub=True)
    await feed(agent, "telemetry", telemetry(1, 10.0))
    assert f"mc/v1/{DEV}/cmd" not in agent._publish.topics()
    assert agent._publish.last("up/state")["time_synced"] is False


async def test_duplicate_telemetry_ignored(agent):
    await feed(agent, "down/snapshot", snapshot(), hub=True)
    await feed(agent, "telemetry", telemetry(1, 50.0))
    await feed(agent, "telemetry", telemetry(1, 10.0))
    assert "up/rule_exec" not in " ".join(agent._publish.topics())


async def test_local_manual_watering(agent):
    await feed(agent, "down/snapshot", snapshot(), hub=True)
    cmd_id = await agent.water_plant(PLANT, 15)
    report = agent._publish.last("up/cmd")
    assert report["id"] == cmd_id and report["source"] == "local" and "rule_id" not in report
    with pytest.raises(CommandRejected) as e:
        await agent.water_plant(PLANT, 999)
    assert e.value.code == "safety_limit"


async def test_cloud_command_counts_as_pending(agent):
    await feed(agent, "down/snapshot", snapshot(), hub=True)
    await feed(agent, "cmd", {"id": "C1", "action": "pump.run", "exp": NOW + 900,
                              "args": {"slot": 2, "seconds": 5}})
    await feed(agent, "telemetry", telemetry(1, 22.0))
    assert agent._publish.last("up/rule_exec")["skip_reason"] == "pending_command"


def test_reset_forgets_everything(agent, tmp_path):
    agent.reset()
    assert agent.hub_id is None
    assert not (tmp_path / "broker/conf.d/bridge.conf").exists()
    assert (tmp_path / "broker/psk").read_text() == ""


def test_store_retention(tmp_path):
    store = Store(tmp_path / "x.db")
    store.add_reading(DEV, 0, 1, int(time.time()) - 8 * 86400, "soil_moisture", 1.0, None)
    store.cleanup()
    assert store.latest_reading(DEV, 0) is None
