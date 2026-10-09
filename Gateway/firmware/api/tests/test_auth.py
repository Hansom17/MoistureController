import pytest
from sqlalchemy import select

from mc_api.db.models import Setting, Token, User

from .conftest import Stack


async def test_meta_before_and_after_setup(stack: Stack):
    m = (await stack.get("/meta")).json()
    assert m["setup_required"] is True and m["hub"] == {"online": True, "compatible": True} and m["auth"] == "token"
    await stack.setup_owner()
    m = (await stack.get("/meta")).json()
    assert m["setup_required"] is False and m["name"] == "Home"        # the name comes from the hub


async def test_setup_checks_and_is_one_time(stack: Stack):
    from mc_api.routers.meta_auth import setup_code
    code = await setup_code(stack.mc)
    body = {"name": "Home", "timezone": "Europe/Berlin", "username": "Owner", "password": "correct horse"}
    assert (await stack.post("/setup", json={**body, "setup_code": "WRONGWRONG"})).json()["code"] == "invalid_setup_code"
    assert (await stack.post("/setup", json={**body, "setup_code": code, "password": "short"})).status_code == 422
    assert (await stack.post("/setup", json={**body, "setup_code": code, "username": "x y"})).status_code == 422
    assert (await stack.post("/setup", json={**body, "setup_code": code, "timezone": "Mars/Base"})).status_code == 422
    r = await stack.post("/setup", json={**body, "setup_code": code.lower()})
    assert r.status_code == 201 and r.json()["user"]["role"] == "owner" and r.json()["user"]["username"] == "owner"
    again = await stack.post("/setup", json={**body, "setup_code": code})
    assert again.status_code == 409 and again.json()["code"] == "already_set_up"
    async with stack.mc.sessions() as s:
        assert await s.get(Setting, "setup_code") is None                    # spent
    assert stack.mc.hub.state["installation"]["timezone"] == "Europe/Berlin"


async def test_setup_needs_the_hub(stack: Stack):
    from mc_api.routers.meta_auth import setup_code
    code = await setup_code(stack.mc)
    await stack.hub_t.kill()
    await stack.settle()
    r = await stack.post("/setup", json={"setup_code": code, "name": "Home", "timezone": "UTC",
                                         "username": "owner", "password": "correct horse"})
    assert r.status_code == 503 and r.json()["code"] == "hub_unavailable"
    async with stack.mc.sessions() as s:
        assert (await s.execute(select(User))).first() is None              # nothing half-created


async def test_login_logout_and_tokens(stack: Stack):
    await stack.setup_owner()
    bad = await stack.post("/auth/login", json={"username": "owner", "password": "nope"})
    assert bad.status_code == 401 and bad.headers["content-type"].startswith("application/problem+json")
    assert (await stack.post("/auth/login", json={"username": "ghost", "password": "nope"})).status_code == 401
    r = await stack.post("/auth/login", json={"username": "OWNER", "password": "correct horse", "device_name": "Pixel"})
    tok = r.json()["token"]
    assert (await stack.get("/me", tok)).json()["username"] == "owner"
    toks = (await stack.get("/auth/tokens", tok)).json()
    assert {t["name"] for t in toks} == {"setup", "Pixel"} and [t["current"] for t in toks].count(True) == 1
    other = next(t for t in toks if not t["current"])
    assert (await stack.delete(f"/auth/tokens/{other['id']}", tok)).status_code == 204
    assert (await stack.post("/auth/logout", tok)).status_code == 204
    assert (await stack.get("/me", tok)).status_code == 401
    async with stack.mc.sessions() as s:                                      # only hashes are stored
        raw = [t.token_hash for t in (await s.execute(select(Token))).scalars()]
    assert all(len(h) == 64 and h != tok for h in raw)


async def test_requests_without_valid_token_are_refused(stack: Stack):
    await stack.setup_owner()
    assert (await stack.get("/devices")).status_code == 401
    assert (await stack.get("/devices", "garbage-token-value")).status_code == 401
    r = await stack.http.get("/api/v1/devices", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


async def test_login_rate_limit(stack: Stack):
    await stack.setup_owner()
    for _ in range(5):
        assert (await stack.post("/auth/login", json={"username": "owner", "password": "bad"})).status_code == 401
    r = await stack.post("/auth/login", json={"username": "owner", "password": "bad"})
    assert r.status_code == 401                                              # the 6th failure starts the delay
    r = await stack.post("/auth/login", json={"username": "owner", "password": "correct horse"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1       # even the right password waits
    stack.clock.advance(5)
    assert (await stack.post("/auth/login", json={"username": "owner", "password": "correct horse"})).status_code == 200


async def test_change_password_revokes_other_tokens(stack: Stack):
    first = await stack.setup_owner()
    second = (await stack.post("/auth/login", json={"username": "owner", "password": "correct horse"})).json()["token"]
    assert (await stack.patch("/me", second, {"password": "new password 1"})).status_code == 401   # needs the old one
    assert (await stack.patch("/me", second, {"password": "new password 1", "current_password": "correct horse"})).status_code == 200
    assert (await stack.get("/me", first)).status_code == 401
    assert (await stack.get("/me", second)).status_code == 200
    assert (await stack.post("/auth/login", json={"username": "owner", "password": "new password 1"})).status_code == 200


async def test_reauth_proof(stack: Stack):
    tok = await stack.setup_owner()
    assert (await stack.post("/auth/reauth", tok, {"password": "wrong"})).status_code == 401
    proof = await stack.proof(tok)
    assert (await stack.post("/export", tok)).json()["code"] == "reauth_required"
    assert (await stack.post("/export", tok, headers=proof)).status_code == 200
    stack.clock.advance(301)
    assert (await stack.post("/export", tok, headers=proof)).json()["code"] == "reauth_required"   # five minutes only
    other, _ = await stack.user(tok, "admin")
    assert (await stack.post("/export", tok, headers={"X-MC-Reauth": "stolen"})).json()["code"] == "reauth_required"


async def test_reset_owner_flow(stack: Stack):
    old = await stack.setup_owner()
    from mc_api.cli import _status
    await _status(stack.settings, reset=True)
    assert (await stack.get("/meta")).json()["setup_required"] is True
    from mc_api.routers.meta_auth import setup_code
    code = await setup_code(stack.mc)
    r = await stack.post("/setup", json={"setup_code": code, "name": "Home", "timezone": "UTC", "username": "newowner",
                                         "password": "another pass"})
    assert r.status_code == 201
    users = (await stack.get("/users", r.json()["token"])).json()
    assert {u["username"]: u["role"] for u in users} == {"owner": "admin", "newowner": "owner"}


async def test_errors_are_problem_json_and_headers_are_set(stack: Stack):
    tok = await stack.setup_owner()
    r = await stack.get("/nothing", tok)
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    r = await stack.post("/plants", tok, {"name": ""})
    assert r.status_code == 422 and r.json()["code"] == "validation" and "name" in r.json()["detail"]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    big = await stack.http.post("/api/v1/auth/login", content=b"x" * 70000, headers={"content-type": "application/json"})
    assert big.status_code == 413
