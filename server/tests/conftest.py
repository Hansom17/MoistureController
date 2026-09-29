import json
import time

import httpx
import pytest
from sqlalchemy import select

from mc_server.config import Settings
from mc_server.db.models import Outbox
from mc_server.main import create_app
from mc_server.services import ingest


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


class FakeDevice:
    """Feeds contract messages into the ingest pipeline as if they came over MQTT."""

    def __init__(self, ctx, device_id: str):
        self.ctx = ctx
        self.id = device_id
        self.seq = 0
        self.boot = 1

    async def send(self, suffix: str, payload: dict | bytes, retained: bool = False):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        async with self.ctx.uow() as uow:
            await ingest.handle(uow, f"mc/v1/{self.id}/{suffix}", body, retained)

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
                        broker_files_dir=tmp_path / "broker", auth_mode="dev",
                        broker_public_host="mqtt.example.com")
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


@pytest.fixture
async def setup(owner, household, ctx):
    """Household with one paired device (reported config) and one plant."""
    h = household["id"]
    created = await owner.post(f"/households/{h}/devices", {"name": "Kitchen"}, expect=201)
    device = FakeDevice(ctx, created["device"]["id"])
    await device.report_config()
    plant = await owner.post(f"/households/{h}/plants", {
        "name": "Basil", "sensor_device_id": device.id, "sensor_slot": 0,
        "pump_device_id": device.id, "pump_slot": 2}, expect=201)
    return {"h": h, "device": device, "plant": plant, "bundle": created["bundle"]}


async def outbox(ctx, topic_suffix: str | None = None) -> list[Outbox]:
    async with ctx.sessionmaker() as s:
        rows = list(await s.scalars(select(Outbox).order_by(Outbox.id)))
    return [r for r in rows if topic_suffix is None or r.topic.endswith(topic_suffix)]
