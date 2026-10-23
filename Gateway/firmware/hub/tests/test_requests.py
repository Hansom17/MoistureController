import json

from sqlalchemy import func, select

from mc_hub.db.models import Plant, RequestRecord

from .conftest import add_device, report


async def test_start_publishes_status_and_snapshots(rig):
    st = rig.api.state["status/hub"]
    assert st["state"] == "online" and st["contract"] == "1.0"
    for name in ("installation", "devices", "plants", "rules", "alerts_open", "join", "status"):
        assert f"state/{name}" in rig.api.state


async def test_last_will_marks_hub_offline(rig):
    await rig.hub_t.kill()
    await rig.api.settle()
    assert rig.api.state["status/hub"]["state"] == "offline"


async def test_plant_create_answer_event_and_snapshot(rig):
    res = await rig.api.request("plant_create", {"name": "  Ficus "})
    assert res["ok"] and res["body"]["plant"]["name"] == "Ficus"
    assert [e["kind"] for e in rig.api.events] == ["plant"]
    assert [p["name"] for p in rig.api.state["state/plants"]] == ["Ficus"]


async def test_repeated_request_id_executes_once(rig):
    a = await rig.api.request("plant_create", {"name": "Fern"}, id="01JC0000000000000000000001")
    b = await rig.api.request("plant_create", {"name": "Fern"}, id="01JC0000000000000000000001")
    assert a == b
    async with rig.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(Plant))).scalar() == 1
    assert len(rig.api.events) == 1


async def test_duplicated_delivery_executes_once(rig):
    rig.broker.duplicate = lambda t, p: t.startswith("mc/v1/req/")
    res = await rig.api.request("plant_create", {"name": "Moss"})
    assert res["ok"]
    async with rig.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(Plant))).scalar() == 1


async def test_expired_deadline_is_ignored(rig):
    res = await rig.api.request("plant_create", {"name": "Late"}, deadline_s=-1)
    assert res is None
    async with rig.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(Plant))).scalar() == 0


async def test_dropped_request_can_be_retried_with_same_id(rig):
    rig.broker.drop = lambda t, p: t.startswith("mc/v1/req/")
    assert await rig.api.request("plant_create", {"name": "Aloe"}, id="01JC0000000000000000000009") is None
    rig.broker.drop = None
    res = await rig.api.request("plant_create", {"name": "Aloe"}, id="01JC0000000000000000000009")
    assert res["ok"]


async def test_unknown_kind_and_validation_errors(rig):
    assert (await rig.api.request("nope", {}))["error"]["type"] == "unknown_kind"
    r = await rig.api.request("plant_create", {})
    assert r["error"]["type"] == "validation" and r["error"]["status"] == 422
    r = await rig.api.request("plant_update", {"plant_id": "x", "fields": {}})
    assert r["error"]["type"] == "not_found"


async def test_bad_version_rejected(rig):
    from datetime import timedelta
    from ulid import ULID
    id = str(ULID())
    now = rig.clock.dt()
    env = {"v": 2, "id": id, "ts": now.isoformat(), "deadline": (now + timedelta(seconds=5)).isoformat(),
           "reply_to": f"mc/v1/res/api-1/{id}", "actor": {"user_id": "u", "role": "admin"}, "body": {}}
    await rig.api.t.publish("mc/v1/req/hub/plant_create", json.dumps(env).encode())
    await rig.api.settle()
    assert rig.api.responses[id]["error"]["type"] == "unsupported_version"


async def test_garbage_request_is_dropped(rig):
    await rig.api.t.publish("mc/v1/req/hub/plant_create", b"{not json")
    await rig.api.settle()
    assert rig.api.state["status/hub"]["state"] == "online"


async def test_installation_set_and_token_is_write_only(rig):
    r = await rig.api.request("installation_set", {"name": "Home", "timezone": "Europe/Berlin",
                                                   "telegram": {"token": "123:abc", "chat_id": "42"}})
    assert r["ok"]
    inst = rig.api.state["state/installation"]
    assert inst == {"name": "Home", "timezone": "Europe/Berlin", "battery_low_mv": 3600, "battery_critical_mv": 3400,
                    "battery_chemistry": "li-ion-1s", "telegram_configured": True}
    assert "123:abc" not in json.dumps(rig.api.state)
    # updating the chat id without a token keeps the stored token
    await rig.api.request("installation_set", {"telegram": {"chat_id": "43"}})
    assert rig.api.state["state/installation"]["telegram_configured"] is True


async def test_plant_needs_known_device_and_slot(rig):
    r = await rig.api.request("plant_create", {"name": "X", "sensor": {"device_id": "dev-nope", "slot": 0}})
    assert r["error"]["type"] == "validation"
    dev = await add_device(rig)
    r = await rig.api.request("plant_create", {"name": "X", "sensor": {"device_id": dev, "slot": 9}})
    assert r["error"]["type"] == "validation"
    r = await rig.api.request("plant_create", {"name": "X", "sensor": {"device_id": dev, "slot": 0},
                                               "pump": {"device_id": dev, "slot": 2}})
    assert r["ok"]


async def test_rules_crud_and_limits(rig):
    dev = await add_device(rig)
    plant = (await rig.api.request("plant_create", {"name": "P", "sensor": {"device_id": dev, "slot": 0}}))["body"]["plant"]
    base = {"plant_id": plant["id"], "threshold": 30, "water_s": 10, "cooldown_s": 3600, "max_per_day": 3}
    assert (await rig.api.request("rule_create", base))["error"]["type"] == "conflict"   # no pump yet
    await rig.api.request("plant_update", {"plant_id": plant["id"], "fields": {"pump": {"device_id": dev, "slot": 2}}})
    assert (await rig.api.request("rule_create", base | {"water_s": 601}))["error"]["type"] == "safety_limit"
    assert (await rig.api.request("rule_create", base | {"quiet_from": "25:00", "quiet_to": "06:00"}))["error"]["type"] == "validation"
    assert (await rig.api.request("rule_create", base | {"notify_channels": ["sms"]}))["error"]["type"] == "validation"
    rule = (await rig.api.request("rule_create", base | {"notify_channels": ["app", "telegram"]}))["body"]["rule"]
    assert rig.api.state["state/rules"][0]["notify_channels"] == ["app", "telegram"]
    upd = await rig.api.request("rule_update", {"rule_id": rule["id"], "fields": {"threshold": 25}})
    assert upd["body"]["rule"]["threshold"] == 25
    assert (await rig.api.request("rule_delete", {"rule_id": rule["id"]}))["ok"]
    assert rig.api.state["state/rules"] == []
    assert (await rig.api.request("rule_delete", {"rule_id": rule["id"]}))["error"]["type"] == "not_found"


async def test_plant_delete_disables_rules(rig):
    dev = await add_device(rig)
    plant = (await rig.api.request("plant_create", {"name": "P", "pump": {"device_id": dev, "slot": 2}}))["body"]["plant"]
    await rig.api.request("rule_create", {"plant_id": plant["id"], "threshold": 30, "water_s": 10,
                                          "cooldown_s": 60, "max_per_day": 2})
    await rig.api.request("plant_delete", {"plant_id": plant["id"]})
    assert rig.api.state["state/plants"] == []
    assert rig.api.state["state/rules"][0]["enabled"] is False


async def test_hub_announces_itself_again_after_the_broker_connection_returns(rig):
    await rig.hub_t.kill()                               # the broker publishes the last will: offline
    await rig.api.settle()
    assert rig.api.state["status/hub"]["state"] == "offline"
    await rig.hub_t.connect()                            # the transport reconnects ...
    await rig.hub.on_reconnect()                         # ... and calls this
    await rig.api.settle()
    assert rig.api.state["status/hub"]["state"] == "online"
    assert rig.api.state["state/devices"] == [] and "state/plants" in rig.api.state
