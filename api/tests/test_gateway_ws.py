"""The gateway WebSocket (gateway_api.md §4) over a real ASGI connection."""

import hashlib
import secrets
import time

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mc_api.config import Settings
from mc_api.main import create_app

USER = {"Authorization": "Bearer dev:alice:alice@example.com"}


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db", auth_mode="dev")
    with TestClient(create_app(settings, background=False)) as c:
        yield c


def enroll(c: TestClient, check_pending: bool = False) -> tuple[str, dict]:
    h = c.post("/api/v1/households", json={"name": "Home"}, headers=USER).json()["id"]
    secret = secrets.token_bytes(32)
    start = c.post("/gateway/v1/enroll/start", json={
        "secret_sha256": hashlib.sha256(secret).hexdigest(), "version": "0.1.0",
        "arch": "arm64", "adapters": ["esp32-mqtt"]}).json()
    body = {"enroll_id": start["enroll_id"], "secret": secret.hex()}
    if check_pending:
        assert c.post("/gateway/v1/enroll/poll", json=body).status_code == 202
        time.sleep(4.1)  # poll interval (429 slow_down otherwise)
    r = c.post(f"/api/v1/households/{h}/gateway", json={"user_code": start["user_code"]},
               headers=USER)
    assert r.status_code == 201, r.text
    creds = c.post("/gateway/v1/enroll/poll", json=body).json()
    assert creds["ws_url"].endswith("/gateway/v1/connect")
    return h, creds


def auth(creds: dict) -> dict:
    return {"Authorization": f"Gateway {creds['gateway_id']}:{creds['credential']}"}


HELLO = {"t": "hello", "version": "0.1.0", "adapters": ["esp32-mqtt"], "snapshot_rev": 0,
         "keys_rev": 0}
STATE = {"t": "gateway_state", "version": "0.1.0", "arch": "arm64", "uptime_s": 5,
         "snapshot_rev": 1, "keys_rev": 1, "lan_host": "192.168.1.20", "time_synced": True}


def test_bad_credential_is_rejected(client):
    _, creds = enroll(client, check_pending=True)
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/gateway/v1/connect",
                                      headers=auth({**creds, "credential": "nope"})):
            pass
    assert e.value.code == 1008


def test_session_protocol(client):
    h, creds = enroll(client)
    with client.websocket_connect("/gateway/v1/connect", headers=auth(creds)) as ws:
        ws.send_json(HELLO)
        welcome = ws.receive_json()
        assert welcome["t"] == "welcome" and welcome["ack_seq"] == 0
        # Queued at claim time: the key set and snapshot.
        first = [ws.receive_json(), ws.receive_json()]
        assert [m["t"] for m in first] == ["keys", "snapshot"]
        for m in first:
            ws.send_json({"t": "down_ack", "id": m["id"], "result": "applied"})

        ws.send_json({**STATE, "seq": 1})
        assert ws.receive_json() == {"t": "ack", "seq": 1}
        ws.send_json({**STATE, "seq": 1})  # replay after a reconnect: acked, not reprocessed
        assert ws.receive_json() == {"t": "ack", "seq": 1}

        info = client.get(f"/api/v1/households/{h}/gateway", headers=USER).json()
        assert info["online"] and info["in_sync"] and info["lan_host"] == "192.168.1.20"

        # A change through the API arrives right away (sender woken on commit).
        r = client.post(f"/api/v1/households/{h}/devices", json={"name": "Kitchen"},
                        headers=USER)
        assert r.status_code == 201, r.text
        device_id = r.json()["device"]["id"]
        got = {m["t"]: m for m in (ws.receive_json() for _ in range(3))}
        assert set(got) == {"keys", "snapshot", "config_desired"}
        assert got["keys"]["devices"][0]["id"] == device_id
        assert got["config_desired"]["device"] == device_id

        client.delete(f"/api/v1/households/{h}/gateway", headers=USER)
        assert ws.receive_json()["t"] == "removed"
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4001

    # The credential is dead after removal.
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/gateway/v1/connect", headers=auth(creds)):
            pass


def test_reconnect_resumes_from_ack(client):
    h, creds = enroll(client)
    with client.websocket_connect("/gateway/v1/connect", headers=auth(creds)) as ws:
        ws.send_json(HELLO)
        ws.receive_json()
        ws.receive_json(), ws.receive_json()  # keys + snapshot, not acked
        ws.send_json({**STATE, "seq": 1})
        assert ws.receive_json() == {"t": "ack", "seq": 1}
    assert not client.get(f"/api/v1/households/{h}/gateway", headers=USER).json()["online"]

    with client.websocket_connect("/gateway/v1/connect", headers=auth(creds)) as ws:
        ws.send_json(HELLO)
        assert ws.receive_json()["ack_seq"] == 1
        # Unacknowledged down messages are sent again.
        assert [ws.receive_json()["t"], ws.receive_json()["t"]] == ["keys", "snapshot"]
