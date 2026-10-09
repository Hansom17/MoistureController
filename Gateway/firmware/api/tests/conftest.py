import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from mc_api.app import create_app, startup
from mc_api.config import Settings
from mc_api.db import migrate as api_migrate
from mc_api.db.session import make_engine as api_engine, make_sessionmaker as api_sessions
from mc_hub.bus.publisher import Publisher, make_will
from mc_hub.bus.transport import MemoryBroker
from mc_hub.clock import FakeClock
from mc_hub.db import migrate as hub_migrate
from mc_hub.db.session import make_engine as hub_engine, make_sessionmaker as hub_sessions
from mc_hub.hub import Hub

SIM = Path(__file__).resolve().parents[2] / ".." / "scripts" / "z2m_sim.py"


def load_sim():
    spec = importlib.util.spec_from_file_location("z2m_sim", SIM.resolve())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Stack:
    """The real hub, the api and a simulated Zigbee2MQTT on one in-memory broker."""

    async def settle(self, rounds: int = 6):
        for _ in range(rounds):
            await asyncio.sleep(0.002)
            for c in list(self.broker.clients):
                await c.settle()

    async def until(self, pred, tries: int = 300):
        for _ in range(tries):
            await self.settle(2)
            r = pred()
            if asyncio.iscoroutine(r):
                r = await r
            if r:
                return
            await asyncio.sleep(0.005)
        raise AssertionError("condition not reached")

    # ---- http helpers ------------------------------------------------------------------------------
    def h(self, token):
        return {"Authorization": f"Bearer {token}"}

    async def get(self, path, token=None, **kw):
        return await self.http.get("/api/v1" + path, headers=self.h(token) if token else None, **kw)

    async def post(self, path, token=None, json=None, headers=None, **kw):
        hd = dict(self.h(token)) if token else {}
        hd.update(headers or {})
        return await self.http.post("/api/v1" + path, headers=hd, json=json, **kw)

    async def patch(self, path, token, json):
        return await self.http.patch("/api/v1" + path, headers=self.h(token), json=json)

    async def put(self, path, token, json):
        return await self.http.put("/api/v1" + path, headers=self.h(token), json=json)

    async def delete(self, path, token, headers=None):
        hd = dict(self.h(token))
        hd.update(headers or {})
        return await self.http.delete("/api/v1" + path, headers=hd)

    async def setup_owner(self, username="owner", password="correct horse"):
        from mc_api.routers.meta_auth import setup_code
        code = await setup_code(self.mc)
        r = await self.post("/setup", json={"setup_code": code, "name": "Home", "timezone": "Europe/Berlin",
                                            "username": username, "password": password})
        assert r.status_code == 201, r.text
        return r.json()["token"]

    async def proof(self, token, password="correct horse"):
        r = await self.post("/auth/reauth", token, {"password": password})
        assert r.status_code == 200, r.text
        return {"X-MC-Reauth": r.json()["proof"]}

    async def user(self, owner_token, role="member", username=None):
        """Invite and accept: returns (token, user id)."""
        r = await self.post("/invites", owner_token, {"role": role})
        assert r.status_code == 201, r.text
        username = username or f"{role}-user"
        a = await self.post(f"/invites/{r.json()['code']}/accept", json={"username": username, "password": "password123"})
        assert a.status_code == 201, a.text
        return a.json()["token"], a.json()["user"]["id"]


@pytest.fixture
async def stack(tmp_path):
    s = Stack()
    s.clock = FakeClock()
    s.broker = MemoryBroker()
    # hub
    hub_db = tmp_path / "hub.db"
    await hub_migrate.upgrade(hub_db)
    s.hub_engine = hub_engine(hub_db)
    pub0 = Publisher(None, s.clock)
    s.hub_t = s.broker.client(make_will(pub0.boot_id))
    await s.hub_t.connect()
    pub = Publisher(s.hub_t, s.clock)
    pub.boot_id = pub0.boot_id
    s.hub = Hub(s.hub_t, hub_sessions(s.hub_engine), s.clock, pub, engine=s.hub_engine, backup_dir=tmp_path / "hub-backups")
    # api
    settings = Settings(data_dir=tmp_path, instance="api-1", request_timeout_s=2.0)
    api_db = settings.db_path
    await api_migrate.upgrade(api_db)
    s.api_engine = api_engine(api_db)
    s.api_t = s.broker.client()
    await s.api_t.connect()
    s.app = create_app(settings, s.api_t, api_sessions(s.api_engine), s.clock, engine=s.api_engine, ping_s=0.2)
    s.mc = s.app.state.mc
    s.settings = settings
    await s.hub.start()
    await startup(s.mc)
    await s.settle()
    s.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app), base_url="http://test")
    # simulated Zigbee2MQTT (modules join when a window is opened)
    s.sim_mod = load_sim()
    s.sim = None
    yield s
    await s.http.aclose()
    await s.api_engine.dispose()
    await s.hub_engine.dispose()


async def start_sim(s, **kw):
    kw.setdefault("modules", 0)
    kw.setdefault("pending", 1)
    kw.setdefault("speed", 10000)
    s.sim = s.sim_mod.Sim(s.broker.client(), join_delay=0.001, report_interval=3600, **kw)
    await s.sim.t.connect()
    await s.sim.start()
    await s.settle()
    return s.sim


CFG = {"slots": [{"slot": 0, "module": "moisture", "port": "P1"},
                 {"slot": 2, "module": "pump", "port": "P3", "max_run_s": 60, "min_pause_s": 0}]}


async def join_device(s, token, **sim):
    """Open the join window through the api and wait until the simulated module is online."""
    await start_sim(s, **sim)
    r = await s.post("/devices/join", token, {"seconds": 60})
    assert r.status_code == 202, r.text
    await s.until(lambda: s.mc.hub.state.get("devices") and s.mc.hub.state["devices"][0]["status"] == "online")
    return s.mc.hub.state["devices"][0]["id"]
