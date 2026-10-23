"""The Zigbee2MQTT converter and the hub agree on the messages (Gateway/specs.md 7.5).

Both sides share fixtures in `Gateway/firmware/zigbee2mqtt/test/fixtures/`:
- `module_report.json`, `module_commands.json`: what the converter publishes for a module's report/acks
  (written by the converter's tests); here they go through the hub's adapter and ingest.
- `hub_set_payloads.json`: what the hub sends to `zigbee2mqtt/<dev>/set` (written here with
  UPDATE_FIXTURES=1); the converter's tests turn them into attribute writes and commands.
"""
import json
import os
from pathlib import Path

import pytest

from mc_hub.db.models import Command
from mc_hub.services import config_sync
from mc_hub.services.sender import payload_for
from mc_hub.zigbee import adapter
from mc_hub.zigbee.messages import CmdAck, ConfigState, Event, Status, Telemetry

from .conftest import add_device, device_report

FIXTURES = Path(__file__).resolve().parents[2] / "zigbee2mqtt" / "test" / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def hub_payloads() -> dict:
    now = 1_800_000_000

    def cmd(zb_id, action, args, exp=now + 900):
        return Command(zb_id=zb_id, action=action, args=args, exp=exp)

    board = {"name": "carrier-v1", "ports": [{"id": f"P{i}", "roles": ["moisture", "pump"]} for i in range(1, 7)]}
    body = config_sync.validate(
        {"slots": [{"slot": 0, "module": "moisture", "port": "P1"},
                   {"slot": 2, "module": "pump", "port": "P3", "max_run_s": 60, "min_pause_s": 600}]}, board)
    return {
        "config": {"config": {"rev": 9, **body}},
        "pump_run": payload_for(cmd(1048577, "pump.run", {"slot": 2, "seconds": 10}), now, None),
        "pump_stop": payload_for(cmd(1048578, "pump.stop", {"slot": 2}), now, None),
        "cancel": payload_for(cmd(1048579, "cmd.cancel", {"target": 1048577}), now, None),
        "device_action": payload_for(cmd(1048580, "device.identify", {"arg": 0}), now, None),
    }


def test_hub_payloads_match_the_fixture_the_converter_reads():
    actual = hub_payloads()
    path = FIXTURES / "hub_set_payloads.json"
    if os.environ.get("UPDATE_FIXTURES"):
        path.write_text(json.dumps(actual, indent=2) + "\n")
    assert actual == json.loads(path.read_text()), "run with UPDATE_FIXTURES=1 and then the converter tests"


def test_module_report_is_understood_by_the_adapter():
    state = fixture("module_report.json")
    msgs = {type(m): m for m in adapter.normalize(state)}
    assert set(msgs) == {Telemetry, Status, ConfigState}
    t = msgs[Telemetry]
    assert (t.seq, t.boot_id) == (1042, 7)
    assert [(s.slot, s.type, s.value, s.raw, s.error) for s in t.slots] == [
        (0, "moisture", 41.5, 2143, "ok"), (2, "pump", 0, 0, "ok")]
    s = msgs[Status]
    assert (s.status, s.safe_reason, s.fast_mode, s.board, s.interface, s.config_schema) == (
        "operational", "none", False, "carrier-v1", "1.0", 1)
    assert s.diagnostics == {"uptime_s": 86400, "boot_reason": "power_on", "reset_count": 0, "rejoin_count": 1,
                             "last_error": 0, "free_heap": 143000}
    c = msgs[ConfigState]
    assert (c.cfg_rev, c.cfg_result, c.cfg_error) == (8, "ok", None)


def test_acks_and_events_are_understood_by_the_adapter():
    f = fixture("module_commands.json")
    (ack,) = adapter.normalize(f["ack"])
    assert isinstance(ack, CmdAck) and (ack.n, ack.cmd_id, ack.state, ack.reason) == (17, 1048577, "done", "none")
    (run,) = adapter.normalize(f["running"])
    assert run.state == "running" and run.ends_in_s == 10
    (ev,) = adapter.normalize(f["event"])
    assert isinstance(ev, Event) and (ev.n, ev.code, ev.slot) == (4, "sensor_fault", 1)


async def test_module_report_goes_through_the_whole_ingest(rig):
    dev = await add_device(rig)
    await rig.z2m.state(dev, {**fixture("module_report.json"), "linkquality": 120})
    await rig.api.settle()
    d = rig.api.state["state/devices"][0]
    assert d["status"] == "online" and d["board"] == "carrier-v1" and d["link_quality"] == 120
    assert d["latest_readings"]["0"]["value"] == 41.5
    assert d["diagnostics"]["rejoin_count"] == 1
