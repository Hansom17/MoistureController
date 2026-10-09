import asyncio
import json
from datetime import timedelta

import pytest
from ulid import ULID

from mc_hub.bus.publisher import Publisher, make_will
from mc_hub.bus.transport import MemoryBroker
from mc_hub.clock import FakeClock
from mc_hub.db import migrate
from mc_hub.db.session import make_engine, make_sessionmaker
from mc_hub.hub import Hub


class Api:
    """Plays the role of the api service on the in-memory broker."""

    def __init__(self, transport, clock):
        self.t, self.clock = transport, clock
        self.responses: dict[str, dict] = {}
        self.events: list[dict] = []
        self.state: dict[str, object] = {}

    async def start(self):
        await self.t.connect()
        await self.t.subscribe("mc/v1/res/api-1/#", self._res)
        await self.t.subscribe("mc/v1/event/#", self._event)
        await self.t.subscribe("mc/v1/state/#", self._state)
        await self.t.subscribe("mc/v1/status/#", self._state)

    async def _res(self, topic, payload):
        self.responses[topic.rsplit("/", 1)[1]] = json.loads(payload)

    async def _event(self, topic, payload):
        self.events.append(json.loads(payload))

    async def _state(self, topic, payload):
        self.state[topic.replace("mc/v1/", "")] = json.loads(payload) if payload else None

    async def request(self, kind, body, *, id=None, role="admin", deadline_s=10.0, wait=True):
        id = id or str(ULID())
        now = self.clock.dt()
        env = {"v": 1, "id": id, "ts": now.isoformat(), "deadline": (now + timedelta(seconds=deadline_s)).isoformat(),
               "reply_to": f"mc/v1/res/api-1/{id}", "actor": {"user_id": "u1", "role": role}, "body": body}
        await self.t.publish(f"mc/v1/req/hub/{kind}", json.dumps(env).encode())
        if wait:
            await self.settle()
        return self.responses.get(id)

    async def settle(self):
        for _ in range(5):
            await asyncio.sleep(0)
            await self.t.settle()
            for c in self.t.broker.clients:
                await c.settle()


class Z2M:
    """Publishes what Zigbee2MQTT would."""

    def __init__(self, transport):
        self.t = transport

    async def start(self):
        await self.t.connect()

    async def devices(self, entries):
        await self.t.publish("zigbee2mqtt/bridge/devices", json.dumps(entries).encode(), retain=True)

    async def state(self, name, payload):
        await self.t.publish(f"zigbee2mqtt/{name}", json.dumps(payload).encode())

    async def availability(self, name, state):
        await self.t.publish(f"zigbee2mqtt/{name}/availability", json.dumps({"state": state}).encode())


def plant_entry(ieee="0x00124b0001", friendly="0x00124b0001", interview="SUCCESSFUL", model="MC-PLANT"):
    return {"ieee_address": ieee, "friendly_name": friendly, "type": "EndDevice", "supported": True,
            "interview_state": interview, "model_id": model, "software_build_id": "0.1.0",
            "definition": {"model": model, "vendor": "MoistureController"}}


def report(seq=1, boot_id=7, v0=41.5, **extra):
    p = {"seq": seq, "boot_id": boot_id, "status": "operational", "slot0_type": "moisture", "slot0_value": v0,
         "slot0_raw": 2143, "slot0_error": "ok", "slot2_type": "pump", "slot2_value": 0, "slot2_raw": 0,
         "slot2_error": "ok", "linkquality": 112, "voltage_mv": 0, "board": "carrier-v1", "cfg_rev": 0}
    p.update(extra)
    return p


class Rig:
    pass


@pytest.fixture
async def rig(tmp_path):
    r = Rig()
    r.clock = FakeClock()
    r.broker = MemoryBroker()
    db = tmp_path / "hub.db"
    await migrate.upgrade(db)
    r.engine = make_engine(db)
    r.sessions = make_sessionmaker(r.engine)
    pub0 = Publisher(None, r.clock)
    r.hub_t = r.broker.client(make_will(pub0.boot_id))
    await r.hub_t.connect()
    pub = Publisher(r.hub_t, r.clock)
    pub.boot_id = pub0.boot_id
    r.hub = Hub(r.hub_t, r.sessions, r.clock, pub)
    r.api = Api(r.broker.client(), r.clock)
    r.z2m = Z2M(r.broker.client())
    await r.api.start()
    await r.z2m.start()
    await r.hub.start()
    await r.api.settle()
    yield r
    await r.engine.dispose()


async def add_device(r, name="dev-a", entry=None):
    """Join a module through bridge/devices and give it the internal id as friendly name."""
    await r.z2m.devices([entry or plant_entry()])
    await r.api.settle()
    dev = r.api.state["state/devices"][0]
    return dev["id"]
