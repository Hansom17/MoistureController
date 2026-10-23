import asyncio
import json

import httpx
import pytest
import uvicorn

from mc_api.app import cleanup_tokens, create_app
from mc_api.db.models import Token
from mc_api.realtime.bus import RING_SIZE, EventBus
from sqlalchemy import select

from .conftest import Stack


# ---- the SSE bus ----------------------------------------------------------------------------------

def test_bus_replay_resync_and_overflow():
    t = [1000.0]
    bus = EventBus(lambda: t[0])
    ids = []
    for i in range(3):
        bus.publish("plant", {"i": i})
    sub = bus.subscribe("u", "t", None)
    assert sub.queue.empty()                                     # a fresh stream starts at "now"
    bus.publish("plant", {"i": 3})
    first = sub.queue.get_nowait()
    again = bus.subscribe("u", "t", first.id - 2)               # replay what was missed
    assert [e.data["i"] for e in list(again.queue._queue)] == [2, 3]
    stale = bus.subscribe("u", "t", 5)                           # an id from a previous process
    assert stale.queue.get_nowait().kind == "resync"
    for i in range(RING_SIZE + 5):
        bus.publish("reading", {"i": i})
    old = bus.subscribe("u", "t", first.id)                      # fell out of the ring
    assert old.queue.get_nowait().kind == "resync"
    slow = bus.subscribe("u", "t", None)
    for i in range(600):
        bus.publish("reading", {"i": i})
    assert list(slow.queue._queue)[0].kind == "resync" and slow.queue.qsize() < 500


def test_tickets_are_single_use_and_expire():
    t = [1000.0]
    bus = EventBus(lambda: t[0])
    tk = bus.issue_ticket("u", "tok")
    assert bus.redeem_ticket(tk) == ("u", "tok") and bus.redeem_ticket(tk) is None
    tk = bus.issue_ticket("u", "tok")
    t[0] += 61
    assert bus.redeem_ticket(tk) is None


# ---- the stream over a real socket ----------------------------------------------------------------------

@pytest.fixture
async def live(stack: Stack):
    server = uvicorn.Server(uvicorn.Config(stack.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"))
    task = asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    stack.base = f"http://127.0.0.1:{port}"
    yield stack
    server.should_exit = True
    await task


def lines(resp):
    if not hasattr(resp, "_it"):
        resp._it = resp.aiter_lines()
    return resp._it


async def frames(resp, n, timeout=3.0):
    """Reads n SSE frames: [(id, event, data)]."""
    out, cur = [], {}

    async def read():
        async for line in lines(resp):
            if line == "":
                if cur:
                    out.append((cur.get("id"), cur.get("event"), json.loads(cur.get("data", "{}"))))
                    cur.clear()
                    if len(out) >= n:
                        return
                continue
            k, _, v = line.partition(": ")
            cur[k] = v

    await asyncio.wait_for(read(), timeout)
    return out


async def test_stream_needs_a_valid_single_use_ticket(live: Stack):
    owner = await live.setup_owner()
    assert (await live.get("/stream?ticket=nope")).status_code == 401
    tk = (await live.post("/events/ticket", owner)).json()["ticket"]
    async with httpx.AsyncClient() as c:
        async with c.stream("GET", f"{live.base}/api/v1/stream?ticket={tk}") as r:
            assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
            (hello,) = await frames(r, 1)
            assert hello[1] == "hello"
        again = await c.get(f"{live.base}/api/v1/stream?ticket={tk}")
        assert again.status_code == 401
    assert (await live.post("/events/ticket")).status_code == 401


async def test_stream_delivers_hub_events_and_replays(live: Stack):
    owner = await live.setup_owner()
    member, _ = await live.user(owner, "member")
    async with httpx.AsyncClient() as c:
        tk = (await live.post("/events/ticket", member)).json()["ticket"]
        async with c.stream("GET", f"{live.base}/api/v1/stream?ticket={tk}") as r:
            await frames(r, 1)                                             # hello
            p = (await live.post("/plants", member, {"name": "Streamed"})).json()
            ev = (await frames(r, 1))[0]
            assert ev[1] == "plant" and ev[2]["name"] == "Streamed" and ev[2]["updated_at"].endswith("Z")
            last_id = ev[0]
        await live.post("/plants", member, {"name": "Missed"})            # while disconnected
        await live.settle()
        tk = (await live.post("/events/ticket", member)).json()["ticket"]
        async with c.stream("GET", f"{live.base}/api/v1/stream?ticket={tk}", headers={"Last-Event-ID": last_id}) as r:
            got = await frames(r, 2)
            assert [g[1] for g in got] == ["hello", "plant"] and got[1][2]["name"] == "Missed"
        tk = (await live.post("/events/ticket", member)).json()["ticket"]
        async with c.stream("GET", f"{live.base}/api/v1/stream?ticket={tk}", headers={"Last-Event-ID": "1"}) as r:
            assert [g[1] for g in await frames(r, 2)] == ["hello", "resync"]


async def test_stream_ends_when_the_token_is_revoked(live: Stack):
    owner = await live.setup_owner()
    member, _ = await live.user(owner, "member")
    async with httpx.AsyncClient() as c:
        tk = (await live.post("/events/ticket", member)).json()["ticket"]
        async with c.stream("GET", f"{live.base}/api/v1/stream?ticket={tk}") as r:
            await frames(r, 1)
            await live.post("/auth/logout", member)
            async def drain():
                async for _ in lines(r):
                    pass
            await asyncio.wait_for(drain(), 3)                              # the server closes the stream


async def test_hub_restart_and_event_gaps_become_resync(stack: Stack):
    owner = await stack.setup_owner()
    seen = []
    orig = stack.mc.events.publish
    stack.mc.events.publish = lambda kind, data=None: (seen.append(kind), orig(kind, data))
    await stack.post("/plants", owner, {"name": "One"})
    await stack.settle()
    assert "resync" not in seen
    # an event with an unexpected sequence number: something was missed
    await stack.hub_t.publish("mc/v1/event/plant", json.dumps(
        {"v": 1, "boot_id": stack.hub.pub.boot_id, "seq": stack.hub.pub.seq + 5, "kind": "plant", "body": {}}).encode())
    await stack.settle()
    assert "resync" in seen
    seen.clear()
    await stack.hub_t.publish("mc/v1/event/plant", json.dumps(
        {"v": 1, "boot_id": 123, "seq": 1, "kind": "plant", "body": {}}).encode())     # the hub restarted
    await stack.settle()
    assert "resync" in seen


# ---- static hosting --------------------------------------------------------------------------------------

async def test_web_build_is_served_with_spa_fallback(stack: Stack, tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>app</html>")
    (web / "assets" / "main.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("secret")
    from mc_api.config import Settings
    settings = Settings(data_dir=tmp_path, web_dir=web)
    app = create_app(settings, stack.api_t, stack.mc.sessions, stack.clock)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/")
        assert r.text == "<html>app</html>" and "default-src 'self'" in r.headers["content-security-policy"]
        assert (await c.get("/assets/main.js")).text == "console.log(1)"
        assert (await c.get("/plants/123")).text == "<html>app</html>"          # client-side route
        assert (await c.get("/../secret.txt")).text == "<html>app</html>"       # no escaping the web dir
        assert (await c.get("/%2e%2e/secret.txt")).text == "<html>app</html>"
        n = await c.get("/api/v1/unknown")
        assert n.status_code == 404 and n.headers["content-type"].startswith("application/problem+json")
        assert "content-security-policy" not in n.headers


async def test_unused_and_revoked_tokens_are_cleaned_up(stack: Stack):
    owner = await stack.setup_owner()
    old, _ = await stack.user(owner, "member")
    stack.clock.advance(181 * 86400)
    fresh = (await stack.post("/auth/login", json={"username": "owner", "password": "correct horse"})).json()["token"]
    await cleanup_tokens(stack.mc)
    assert (await stack.get("/me", old)).status_code == 401           # unused for 180+ days
    assert (await stack.get("/me", fresh)).status_code == 200
    async with stack.mc.sessions() as s:
        assert len((await s.execute(select(Token))).scalars().all()) == 1
