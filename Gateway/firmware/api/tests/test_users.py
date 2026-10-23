from .conftest import Stack


async def test_role_matrix(stack: Stack):
    owner = await stack.setup_owner()
    viewer, _ = await stack.user(owner, "viewer")
    member, _ = await stack.user(owner, "member")
    admin, _ = await stack.user(owner, "admin")
    assert (await stack.get("/devices", viewer)).status_code == 200
    assert (await stack.get("/audit", member)).status_code == 403
    assert (await stack.get("/audit", admin)).status_code == 200
    assert (await stack.post("/plants", viewer, {"name": "x"})).status_code == 403
    assert (await stack.post("/plants", member, {"name": "x"})).status_code == 201
    assert (await stack.post("/devices/join", member, {})).status_code == 403
    assert (await stack.patch("/installation", admin, {"name": "n"})).status_code == 403
    assert (await stack.patch("/installation", owner, {"name": "New name"})).status_code == 200
    assert (await stack.post("/backup", member)).status_code == 403
    assert (await stack.post("/export", admin)).status_code == 403
    r = await stack.get("/me", viewer)
    assert r.json()["role"] == "viewer"


async def test_invites(stack: Stack):
    owner = await stack.setup_owner()
    admin, _ = await stack.user(owner, "admin")
    assert (await stack.post("/invites", admin, {"role": "admin"})).status_code == 403   # admins invite up to member
    assert (await stack.post("/invites", admin, {"role": "owner"})).status_code == 403
    assert (await stack.post("/invites", owner, {"role": "member", "expires_in": 10})).status_code == 422
    inv = (await stack.post("/invites", admin, {"role": "member"})).json()
    assert inv["status"] == "open" and inv["path"].endswith(inv["code"])
    assert "code" not in (await stack.get("/invites", admin)).json()[0]           # shown once
    prev = (await stack.get(f"/invites/{inv['code']}")).json()
    assert prev["role"] == "member" and prev["installation"] == "Home"
    bad = await stack.post(f"/invites/{inv['code']}/accept", json={"username": "owner", "password": "password123"})
    assert bad.status_code == 409                                                  # username taken
    ok = await stack.post(f"/invites/{inv['code']}/accept", json={"username": "newbie", "password": "password123"})
    assert ok.status_code == 201 and ok.json()["user"]["role"] == "member"
    assert (await stack.get(f"/invites/{inv['code']}")).json()["code"] == "invalid_invite"       # single use
    assert (await stack.get("/invites", admin)).json()[0]["status"] == "used"
    other = (await stack.post("/invites", admin, {"role": "viewer"})).json()
    assert (await stack.delete(f"/invites/{other['id']}", admin)).status_code == 204
    assert (await stack.get(f"/invites/{other['code']}")).status_code == 404
    short = (await stack.post("/invites", admin, {"role": "viewer", "expires_in": 300})).json()
    stack.clock.advance(301)
    assert (await stack.get(f"/invites/{short['code']}")).status_code == 404       # expired


async def test_managing_users(stack: Stack):
    owner = await stack.setup_owner()
    admin, admin_id = await stack.user(owner, "admin")
    member, member_id = await stack.user(owner, "member")
    viewer, viewer_id = await stack.user(owner, "viewer")
    users = {u["username"]: u for u in (await stack.get("/users", viewer)).json()}
    owner_id = users["owner"]["id"]
    # an admin manages members and viewers, up to member
    assert (await stack.patch(f"/users/{viewer_id}", admin, {"role": "member"})).json()["role"] == "member"
    assert (await stack.patch(f"/users/{viewer_id}", admin, {"role": "admin"})).status_code == 403
    assert (await stack.patch(f"/users/{admin_id}", admin, {"role": "viewer"})).status_code == 403
    assert (await stack.patch(f"/users/{owner_id}", admin, {"role": "viewer"})).status_code == 403
    assert (await stack.delete(f"/users/{owner_id}", owner)).status_code == 403
    # the owner changes admins, with the password
    assert (await stack.patch(f"/users/{admin_id}", owner, {"role": "member"})).json()["code"] == "reauth_required"
    proof = await stack.proof(owner)
    r = await stack.http.patch(f"/api/v1/users/{admin_id}", headers={**stack.h(owner), **proof}, json={"role": "member"})
    assert r.status_code == 200 and r.json()["role"] == "member"
    # disabling revokes tokens
    assert (await stack.patch(f"/users/{member_id}", owner, {"disabled": True})).json()["disabled"] is True
    assert (await stack.get("/me", member)).status_code == 401
    assert (await stack.post("/auth/login", json={"username": "member-user", "password": "password123"})).status_code == 401
    assert (await stack.patch(f"/users/{member_id}", owner, {"disabled": False})).status_code == 200
    # deleting
    assert (await stack.delete(f"/users/{viewer_id}", owner)).status_code == 204
    assert (await stack.get("/me", viewer)).status_code == 401
    assert viewer_id not in [u["id"] for u in (await stack.get("/users", owner)).json()]
    assert (await stack.delete(f"/users/{viewer_id}", owner)).status_code == 404


async def test_transfer_ownership(stack: Stack):
    owner = await stack.setup_owner()
    admin, admin_id = await stack.user(owner, "admin")
    assert (await stack.post("/transfer-ownership", owner, {"user_id": admin_id})).json()["code"] == "reauth_required"
    proof = await stack.proof(owner)
    r = await stack.post("/transfer-ownership", owner, {"user_id": admin_id}, headers=proof)
    assert r.status_code == 200
    assert (await stack.get("/me", admin)).json()["role"] == "owner"
    assert (await stack.get("/me", owner)).json()["role"] == "admin"
    assert (await stack.post("/transfer-ownership", owner, {"user_id": admin_id})).status_code == 403   # no longer owner


async def test_audit_log_records_what_happened(stack: Stack):
    owner = await stack.setup_owner()
    _, uid = await stack.user(owner, "member")
    await stack.delete(f"/users/{uid}", owner)
    log = (await stack.get("/audit", owner)).json()
    actions = [i["action"] for i in log["items"]]
    assert actions[:3] == ["user_removed", "invite_accepted", "invite_created"] and "setup" in actions
    assert log["items"][0]["ts"].endswith("Z")
    page = (await stack.get("/audit?limit=2", owner)).json()
    assert len(page["items"]) == 2 and page["next"]
    older = (await stack.get(f"/audit?limit=50&before={page['next']}", owner)).json()["items"]
    assert older[0]["id"] < page["next"]
