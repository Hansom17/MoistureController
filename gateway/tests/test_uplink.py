"""Gateway ↔ API end to end: the real agent and uplink against the real API app
served by uvicorn on a local port (contracts/gateway_api.md)."""

import asyncio
import hashlib
import json
import secrets
import socket
import time

import httpx
import pytest

from mc_gateway.agent import Agent
from mc_gateway.config import GatewayConfig
from mc_gateway.store import Store
from mc_gateway.uplink import Uplink, ws_url

from .test_agent import Recorder

mc_api = pytest.importorskip("mc_api")
uvicorn = pytest.importorskip("uvicorn")

USER = {"Authorization": "Bearer dev:alice:alice@example.com"}
SLOTS = [{"slot": 0, "module": "moisture_capacitive", "pin": 34},
         {"slot": 2, "module": "pump_relay", "pin": 25, "max_run_s": 60, "min_pause_s": 0}]


def test_ws_url():
    assert ws_url("https://api.example.com/") == "wss://api.example.com/gateway/v1/connect"
    assert ws_url("http://host.docker.internal:8000") == \
        "ws://host.docker.internal:8000/gateway/v1/connect"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def api(tmp_path):
    from mc_api.config import Settings
    from mc_api.main import create_app

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/api.db", auth_mode="dev",
                        public_api_url=base)
    server = uvicorn.Server(uvicorn.Config(create_app(settings, background=False),
                                           host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    async with httpx.AsyncClient(base_url=base, headers=USER) as http:
        yield http
    server.should_exit = True
    await task


async def eventually(check, timeout=5.0):
    """Polls `check` (sync or async) until it returns something truthy."""
    deadline = time.monotonic() + timeout
    while True:
        result = check()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return result
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.05)


async def enroll(api: httpx.AsyncClient, h: str) -> dict:
    secret = secrets.token_bytes(32)
    start = (await api.post("/gateway/v1/enroll/start", json={
        "secret_sha256": hashlib.sha256(secret).hexdigest(), "version": "0.1.0",
        "arch": "arm64", "adapters": ["esp32-mqtt"]})).json()
    r = await api.post(f"/api/v1/households/{h}/gateway", json={"user_code": start["user_code"]})
    assert r.status_code == 201, r.text
    return (await api.post("/gateway/v1/enroll/poll",
                           json={"enroll_id": start["enroll_id"], "secret": secret.hex()})).json()


async def test_gateway_end_to_end(api, tmp_path):
    h = (await api.post("/api/v1/households", json={"name": "Home"})).json()["id"]
    creds = await enroll(api, h)

    cfg = GatewayConfig(data_dir=tmp_path / "gw", api_url=str(api.base_url), lan_host="192.168.1.20",
                    arch="arm64")
    cfg.data_dir.mkdir()
    local = Recorder()
    agent = Agent(cfg, Store(cfg.db_path), publish=local)
    agent.enrolled(creds["gateway_id"], creds["credential"])
    uplink = asyncio.create_task(Uplink(cfg, agent).run())

    async def gateway() -> dict:
        return (await api.get(f"/api/v1/households/{h}/gateway")).json()

    # Connects, applies keys + snapshot, reports its LAN address.
    info = await eventually(lambda: _when(gateway(), lambda g: g["in_sync"] and g["lan_host"]))
    assert info["online"] and info["lan_host"] == "192.168.1.20"

    # A device paired in the app: its key reaches the broker's PSK file.
    r = await api.post(f"/api/v1/households/{h}/devices", json={"name": "Kitchen"})
    assert r.status_code == 201, r.text
    dev = r.json()["device"]["id"]
    psk = r.json()["bundle"]["mqtt"]["psk"]
    assert r.json()["bundle"]["mqtt"]["host"] == "192.168.1.20"
    await eventually(lambda: f"{dev}:{psk}" in (cfg.broker_dir / "psk").read_text())
    await eventually(lambda: f"mc/v1/{dev}/config/desired" in local.topics())

    # The device reports its config and a reading; both reach the API.
    await agent.on_message(f"mc/v1/{dev}/config/state", json.dumps({
        "rev": 1, "result": "applied", "wake_interval_s": 600, "slots": SLOTS,
        "limits": {"max_run_s_hard": 300, "slots_max": 6}}).encode())
    plant = (await api.post(f"/api/v1/households/{h}/plants", json={
        "name": "Basil", "sensor_device_id": dev, "sensor_slot": 0,
        "pump_device_id": dev, "pump_slot": 2})).json()
    await _telemetry(agent, dev, 1, 42.0)
    await eventually(lambda: _when(api.get(f"/api/v1/households/{h}/plants/{plant['id']}"),
                                   lambda p: p.json()["moisture"] == 42.0))

    # Watering from the app: API → gateway → device → ack → API.
    await eventually(lambda: agent.snapshot and agent.snapshot.plants)  # plant in the snapshot
    cmd = (await api.post(f"/api/v1/households/{h}/plants/{plant['id']}/water",
                          json={"seconds": 5})).json()["command"]
    await eventually(lambda: f"mc/v1/{dev}/cmd" in local.topics())
    await agent.on_message(f"mc/v1/{dev}/cmd/ack", json.dumps(
        {"id": cmd["id"], "status": "done", "ts": int(time.time())}).encode())
    await eventually(lambda: _when(api.get(f"/api/v1/households/{h}/commands/{cmd['id']}"),
                                   lambda c: c.json()["status"] == "done"))

    # API unreachable: readings wait in the outbox and are replayed on reconnect.
    uplink.cancel()
    await asyncio.gather(uplink, return_exceptions=True)
    await _telemetry(agent, dev, 2, 38.0)
    assert agent.store.outbox_depth()[0] >= 1
    uplink = asyncio.create_task(Uplink(cfg, agent).run())
    await eventually(lambda: _when(api.get(f"/api/v1/households/{h}/plants/{plant['id']}"),
                                   lambda p: p.json()["moisture"] == 38.0))
    await eventually(lambda: agent.store.outbox_depth()[0] == 0)

    # Removed in the app: the uplink ends and the gateway can forget everything.
    await api.delete(f"/api/v1/households/{h}/gateway")
    await asyncio.wait_for(uplink, 5)


async def _when(response_coro, predicate):
    value = await response_coro
    return value if predicate(value) else None


async def _telemetry(agent: Agent, dev: str, seq: int, value: float) -> None:
    await agent.on_message(f"mc/v1/{dev}/telemetry", json.dumps({
        "seq": seq, "ts": int(time.time()), "cfg_rev": 1,
        "readings": [{"slot": 0, "type": "soil_moisture", "raw": 2100, "value": value,
                      "unit": "%"}],
        "health": {"batt_mv": 3900, "rssi": -60, "wake": "timer"}}).encode())
