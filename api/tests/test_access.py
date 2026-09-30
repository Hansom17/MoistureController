"""Tenant isolation, roles, sensitive actions, invites (Api_Specs §5, §14)."""

import pytest

from .conftest import Api

# (method, path template, minimum role). {h} household, {p} plant, {d} device.
ROUTES = [
    ("GET", "/households/{h}", "viewer"),
    ("GET", "/households/{h}/plants", "viewer"),
    ("GET", "/households/{h}/devices", "viewer"),
    ("GET", "/households/{h}/alerts", "viewer"),
    ("GET", "/households/{h}/commands", "viewer"),
    ("GET", "/households/{h}/members", "viewer"),
    ("POST", "/households/{h}/plants/{p}/water", "member"),
    ("POST", "/households/{h}/plants/{p}/rules", "member"),
    ("POST", "/households/{h}/plants", "member"),
    ("POST", "/households/{h}/devices", "admin"),
    ("PUT", "/households/{h}/devices/{d}/config", "admin"),
    ("GET", "/households/{h}/invites", "admin"),
    ("GET", "/households/{h}/audit", "admin"),
    ("PATCH", "/households/{h}", "owner"),
]
BODIES = {
    "water": {"seconds": 5},
    "rules": {"threshold": 30, "water_s": 5},
    "plants": {"name": "X"},
    "devices": {"name": "X"},
    "config": {"base_rev": 1, "wake_interval_s": 600, "slots": []},
    "{h}": {"name": "Y"},
}
ORDER = ["viewer", "member", "admin", "owner"]


def _body(template: str):
    for key, body in BODIES.items():
        if template.endswith(key):
            return body
    return None


async def _invite(owner: Api, h: str, role: str, uid: str, client) -> Api:
    inv = await owner.post(f"/households/{h}/invites", {"role": role}, expect=201)
    user = Api(client, uid)
    await user.post(f"/invites/{inv['code']}/accept", expect=200)
    return user


@pytest.mark.parametrize(("method", "template", "min_role"), ROUTES)
async def test_route_access(setup, owner, client, method, template, min_role):
    h = setup["h"]
    path = template.format(h=h, p=setup["plant"]["id"], d=setup["device"].id)
    body = _body(template)

    stranger = Api(client, "mallory")
    r = await stranger.req(method, path, json=body)
    assert r.status_code == 404, "non-members must not learn that it exists"

    for role in ORDER[:-1]:
        user = await _invite(owner, h, role, f"u-{role}", client)
        r = await user.req(method, path, json=body)
        allowed = ORDER.index(role) >= ORDER.index(min_role)
        assert (r.status_code != 403) == allowed, f"{role} → {r.status_code} {r.text}"


async def test_sensitive_action_needs_recent_login(household, owner):
    r = await owner.req("DELETE", f"/households/{household['id']}", stale=True)
    assert r.status_code == 401 and r.json()["type"] == "reauth_required"
    await owner.delete(f"/households/{household['id']}")
    assert await owner.get("/me/households") == []


async def test_invite_flow(household, owner, client):
    h = household["id"]
    inv = await owner.post(f"/households/{h}/invites", {"role": "member"}, expect=201)
    assert inv["url"].endswith(f"/join#c={inv['code']}")
    bob = Api(client, "bob")
    preview = await bob.get(f"/invites/{inv['code']}")
    assert preview["household_name"] == "Home" and preview["role"] == "member"
    joined = await bob.post(f"/invites/{inv['code']}/accept", expect=200)
    assert joined["role"] == "member"
    again = await Api(client, "carol").req("POST", f"/invites/{inv['code']}/accept")
    assert again.status_code == 410


async def test_admin_cannot_invite_admin_or_touch_owner(household, owner, client):
    h = household["id"]
    admin = await _invite(owner, h, "admin", "adam", client)
    r = await admin.req("POST", f"/households/{h}/invites", json={"role": "admin"})
    assert r.status_code == 403
    r = await admin.req("PATCH", f"/households/{h}/members/alice", json={"role": "viewer"})
    assert r.status_code == 403


async def test_owner_cannot_leave_and_transfer(household, owner, client):
    h = household["id"]
    r = await owner.req("DELETE", f"/households/{h}/members/alice")
    assert r.status_code == 409
    bob = await _invite(owner, h, "member", "bob", client)
    await owner.req("POST", f"/households/{h}/transfer-ownership", expect=204,
                    json={"uid": "bob"})
    roles = {m["uid"]: m["role"] for m in await bob.get(f"/households/{h}/members")}
    assert roles == {"alice": "admin", "bob": "owner"}


async def test_member_removal_closes_stream(household, owner, client, ctx):
    h = household["id"]
    bob = await _invite(owner, h, "viewer", "bob", client)
    sub = ctx.bus.subscribe(h, "bob", None)
    await owner.delete(f"/households/{h}/members/bob")
    kinds = [sub.queue.get_nowait().kind for _ in range(sub.queue.qsize())]
    assert kinds[-1] == "close"
    assert (await bob.req("GET", f"/households/{h}")).status_code == 404


async def test_delete_account_blocked_while_sole_owner_of_shared_household(
        household, owner, client):
    await _invite(owner, household["id"], "member", "bob", client)
    r = await owner.req("DELETE", "/me")
    assert r.status_code == 409 and r.json()["type"] == "sole_owner"


async def test_app_version_gate(app, owner):
    app.state.ctx.settings.min_app_version = "1.2.0"
    r = await owner.c.get("/api/v1/me", headers={"X-MC-App": "android/1.1.9",
                                                 "Authorization": "Bearer dev:alice"})
    assert r.status_code == 426
