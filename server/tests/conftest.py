import hashlib
import secrets
import time

import httpx
import pytest
from sqlalchemy import select

from mc_core.contract import gateway as g
from mc_server.config import Settings
from mc_server.db.models import Downlink, Gateway
from mc_server.main import create_app
from mc_server.services import gateways


def auth(uid: str, stale: bool = False) -> dict:
    return {"Authorization": f"Bearer dev:{uid}:{uid}@example.com{':stale' if stale else ''}"}


class Api:
    """Thin client acting as one user."""

    def __init__(self, client: httpx.AsyncClient, uid: str):
        self.c = client
        self.uid = uid

    async def req(self, method: str, path: str, expect: int | None = None, stale=False, **kw):
        r = await self.c.request(method, f"/api/v1{path}", headers=auth(self.uid, stale), **kw)
        if expect is not None:
            assert r.status_code == expect, f"{method} {path}: {r.status_code} {r.text}"
        return r

    async def get(self, path, expect=200, **kw):
        return (await self.req("GET", path, expect, **kw)).json()

    async def post(self, path, body=None, expect=None, **kw):
        r = await self.req("POST", path, expect, json=body, **kw)
        return r.json() if r.content and r.headers.get("content-type", "").endswith("json") else r

    async def patch(self, path, body, expect=200, **kw):
        return (await self.req("PATCH", path, expect, json=body, **kw)).json()

    async def put(self, path, body, expect=200, **kw):
        return (await self.req("PUT", path, expect, json=body, **kw)).json()

    async def delete(self, path, expect=204, **kw):
        return await self.req("DELETE", path, expect, **kw)


class FakeGateway:
    """An enrolled gateway with a live (fake) session: up messages go straight
    into `gateways.process_up`, down messages are read from the downlink table."""

    def __init__(self, ctx, gateway_id: str):
        self.ctx = ctx
        self.gateway_id = gateway_id
        self.seq = 0
        self.closed: list[int] = []

    async def close(self, code: int, reason: str) -> None:
        self.closed.append(code)

    async def up(self, msg: dict) -> None:
        self.seq += 1
        async with self.ctx.uow() as uow:
            gw = await uow.s.get(Gateway, self.gateway_id)
            await gateways.process_up(uow, gw, {**msg, "seq": self.seq})

    async def down_ack(self, row: Downlink, result: str = "applied", error: str | None = None):
        async with self.ctx.uow() as uow:
            gw = await uow.s.get(Gateway, self.gateway_id)
            await gateways.process_down_ack(uow, gw, g.DownAck(id=row.id, result=result,
                                                               error=error))


class FakeDevice:
    """Feeds contract messages in as if the gateway had received them over MQTT."""

    def __init__(self, gateway: FakeGateway, device_id: str):
        self.gw = gateway
        self.id = device_id
        self.seq = 0
        self.boot = 1

    async def send(self, kind: str, payload: dict):
        await self.gw.up({"t": "device", "device": self.id, "adapter": "esp32-mqtt",
                          "kind": kind.replace("/", "_"), "received_at": int(time.time()),
                          "payload": payload})

    async def report_config(self, rev=1, slots=None, max_run_s=60, result="applied", **extra):
        slots = slots if slots is not None else [
            {"slot": 0, "module": "moisture_capacitive", "pin": 34,
             "cal": {"dry": 3000, "wet": 1200}},
            {"slot": 2, "module": "pump_relay", "pin": 25, "active_high": True,
             "max_run_s": max_run_s, "min_pause_s": 0},
        ]
        await self.send("config/state", {
            "rev": rev, "result": result, "wake_interval_s": 600, "slots": slots,
            "limits": {"max_run_s_hard": 300, "slots_max": 6}, **extra})

    async def wake(self, moisture: float | None = 41.5, error: str | None = None,
                   batt_mv: int = 3900):
        await self.send("status", {"state": "online", "fw": "0.4.0", "boot": self.boot})
        self.seq += 1
        reading = {"slot": 0, "type": "soil_moisture", "raw": 2100}
        if error:
            reading["error"] = error
        else:
            reading.update(value=moisture, unit="%")
        await self.send("telemetry", {
            "seq": self.seq, "ts": int(time.time()), "cfg_rev": 1, "readings": [reading],
            "health": {"batt_mv": batt_mv, "rssi": -60, "wake": "timer"}})

    async def ack(self, command_id: str, status: str, **extra):
        await self.send("cmd/ack", {"id": command_id, "status": status, **extra})

    async def sleep(self, next_wake_s: int = 600):
        await self.send("status", {"state": "sleeping", "next_wake_s": next_wake_s})


@pytest.fixture
async def app(tmp_path):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
                        auth_mode="dev")
    application = create_app(settings, background=False)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
def ctx(app):
    return app.state.ctx


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as c:
        yield c


@pytest.fixture
def owner(client):
    return Api(client, "alice")


@pytest.fixture
def other(client):
    return Api(client, "bob")


@pytest.fixture
async def household(owner):
    return await owner.post("/households", {"name": "Home"}, expect=201)


async def enroll(client, owner, h: str) -> dict:
    """Enrollment start → claim by the owner → poll: the gateway's credentials."""
    secret = secrets.token_bytes(32)
    r = await client.post("/gateway/v1/enroll/start", json={
        "secret_sha256": hashlib.sha256(secret).hexdigest(), "version": "0.1.0",
        "arch": "arm64", "adapters": ["esp32-mqtt"]})
    assert r.status_code == 201, r.text
    start = r.json()
    await owner.post(f"/households/{h}/gateway", {"user_code": start["user_code"]}, expect=201)
    r = await client.post("/gateway/v1/enroll/poll",
                          json={"enroll_id": start["enroll_id"], "secret": secret.hex()})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
async def gateway(client, owner, household, ctx) -> FakeGateway:
    """The household's gateway, connected and reporting its LAN address."""
    creds = await enroll(client, owner, household["id"])
    gw = FakeGateway(ctx, creds["gateway_id"])
    await ctx.gateways.register(gw)
    async with ctx.uow() as uow:
        row = await uow.s.get(Gateway, gw.gateway_id)
        await gateways.connected(uow, row, g.Hello(version="0.1.0", adapters=["esp32-mqtt"],
                                                   snapshot_rev=0, keys_rev=0))
    await gw.up({"t": "gateway_state", "version": "0.1.0", "arch": "arm64",
                 "adapters": {"esp32-mqtt": {"devices": 0}}, "lan_host": "192.168.1.20", "lan_port": 8883,
                 "time_synced": True, "outbox_depth": 0, "snapshot_rev": 0, "keys_rev": 0,
                 "uptime_s": 10})
    return gw


@pytest.fixture
async def setup(owner, household, gateway):
    """Household with a gateway, one paired device (reported config) and one plant."""
    h = household["id"]
    created = await owner.post(f"/households/{h}/devices", {"name": "Kitchen"}, expect=201)
    device = FakeDevice(gateway, created["device"]["id"])
    await device.report_config()
    plant = await owner.post(f"/households/{h}/plants", {
        "name": "Basil", "sensor_device_id": device.id, "sensor_slot": 0,
        "pump_device_id": device.id, "pump_slot": 2}, expect=201)
    return {"h": h, "device": device, "plant": plant, "bundle": created["bundle"],
            "gateway": gateway}


async def downlink(ctx, type_: str | None = None, pending: bool = False) -> list[Downlink]:
    async with ctx.sessionmaker() as s:
        q = select(Downlink).order_by(Downlink.created_at, Downlink.id)
        if type_:
            q = q.where(Downlink.type == type_)
        if pending:
            q = q.where(Downlink.acked_at.is_(None))
        return list(await s.scalars(q))
