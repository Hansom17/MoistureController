"""The BLE pairing session reference (contracts/ble.md)."""

import json
from pathlib import Path

import pytest

from mc_core import ble

ROOT = Path(__file__).resolve().parents[2]
POP = bytes(range(16))


def pair(pop_app=POP, pop_dev=POP):
    app = ble.new_session("app", pop_app)
    dev = ble.new_session("device", pop_dev)
    data = app.hello()
    out, _ = dev.feed(data)
    out, _ = app.feed(b"".join(out))
    out, _ = dev.feed(b"".join(out))
    app.feed(b"".join(out))
    return app, dev


def test_vectors_file_is_current():
    assert (ROOT / "contracts" / "ble_vectors.json").read_text() == ble.vectors_json(), \
        "regenerate: .venv/bin/python -c 'from mc_core import ble; print(ble.vectors_json(), end=\"\")' > contracts/ble_vectors.json"


def test_vectors_against_independent_primitives():
    """The key schedule checked with another hash/HMAC implementation, not with ble.py itself."""
    import hashlib
    import hmac

    v = json.loads((ROOT / "contracts" / "ble_vectors.json").read_text())
    # HKDF-SHA256 by hand (RFC 5869): extract with salt = PoP, expand to 32 bytes (one block).
    prk = hmac.new(bytes.fromhex(v["pop"]), bytes.fromhex(v["shared"]), hashlib.sha256).digest()
    info = (b"mc-ble-v1" + bytes.fromhex(v["app_public"]) + bytes.fromhex(v["device_public"])
            + bytes.fromhex(v["nonce_d"]))
    k = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()
    assert k.hex() == v["k"]
    assert v["k_enc"] == v["k"][:32] and v["k_mac"] == v["k"][32:]


def test_handshake_and_messages_roundtrip():
    app, dev = pair()
    assert app.open and dev.open
    _, msgs = dev.feed(app.seal({"id": 1, "op": "info"}))
    assert msgs == [{"id": 1, "op": "info"}]
    _, msgs = app.feed(dev.seal({"id": 1, "ok": True}))
    assert msgs == [{"id": 1, "ok": True}]


def test_wrong_pop_fails_confirmation_on_the_device():
    app = ble.new_session("app", POP)
    dev = ble.new_session("device", bytes(16))
    out, _ = dev.feed(app.hello())
    out, _ = app.feed(b"".join(out))
    with pytest.raises(ble.SessionError) as e:
        dev.feed(b"".join(out))
    assert e.value.code == "confirm_failed"


def test_a_device_without_the_pop_cannot_fool_the_app():
    """A man in the middle can relay HELLO but cannot produce mac_d."""
    app = ble.new_session("app", POP)
    mitm = ble.new_session("device", b"\x99" * 16)
    out, _ = mitm.feed(app.hello())
    out, _ = app.feed(b"".join(out))
    # the MITM cannot verify mac_a, and forging a confirm frame fails the app's check
    forged = ble.frame(json.dumps({"t": "confirm", "mac": ble.b64(bytes(32))}).encode())
    with pytest.raises(ble.SessionError) as e:
        app.feed(forged)
    assert e.value.code == "confirm_failed"


def test_replay_reorder_and_tamper_are_rejected():
    app, dev = pair()
    f1, f2 = app.seal({"id": 1, "op": "info"}), app.seal({"id": 2, "op": "info"})
    with pytest.raises(ble.SessionError):
        dev.feed(f2)  # out of order: the counter is implied
    app, dev = pair()
    f1 = app.seal({"id": 1, "op": "info"})
    dev.feed(f1)
    with pytest.raises(ble.SessionError):
        dev.feed(f1)  # replay
    app, dev = pair()
    bad = bytearray(app.seal({"id": 1, "op": "info"}))
    bad[-1] ^= 1
    with pytest.raises(ble.SessionError):
        dev.feed(bytes(bad))


def test_directions_do_not_share_nonces():
    app, dev = pair()
    f = app.seal({"id": 1, "op": "info"})
    with pytest.raises(ble.SessionError):
        app.feed(f)  # an app frame reflected back at the app


def test_frames_survive_any_fragmentation():
    app, dev = pair()
    big = {"id": 7, "op": "set_wifi", "ssid": "x" * 32, "password": "p" * 64}
    data = app.seal(big)
    for mtu in (23, 24, 50, 185, 247):
        a, d = pair()
        msgs = []
        for chunk in ble.chunks(a.seal(big), mtu):
            _, m = d.feed(chunk)
            msgs += m
        assert msgs == [big]
    # byte by byte
    a, d = pair()
    msgs = []
    for b in a.seal(big):
        _, m = d.feed(bytes([b]))
        msgs += m
    assert msgs == [big]
    assert data[:2] == len(data[2:]).to_bytes(2, "big")


def test_unsupported_version_and_garbage():
    dev = ble.new_session("device", POP)
    with pytest.raises(ble.SessionError) as e:
        dev.feed(ble.frame(b'{"t":"hello","v":2,"pub":"AAAA"}'))
    assert e.value.code == "unsupported_version"
    dev = ble.new_session("device", POP)
    with pytest.raises(ble.SessionError):
        dev.feed(ble.frame(b"not json"))
    with pytest.raises(ble.SessionError) as e:
        ble.new_session("device", POP).feed(b"\xff\xff")
    assert e.value.code == "frame_too_large"


def test_label_roundtrip():
    text = ble.label("MC-3F9A", POP)
    assert text == "MCPOP1:MC-3F9A:000G40R40M30E209185GR38E1W"
    name, pop = ble.parse_label(text)
    assert (name, pop) == ("MC-3F9A", POP)
    assert ble.pop_decode(ble.pop_encode(POP).lower().replace("0", "O")) == POP  # typo tolerant
    for bad in ("MCPOP2:MC-1:00", "MCPOP1:MC-1", "hello"):
        with pytest.raises(ValueError):
            ble.parse_label(bad)


# --- the app flow against a loopback device -----------------------------------------------------

import asyncio  # noqa: E402

from mc_core import ble_client  # noqa: E402

BUNDLE = {"device_id": "mc-8f3kq2v7xw1m9hzt",
          "mqtt": {"host": "192.168.1.20", "port": 8883, "psk": "ab" * 32}}


class FakeDevice:
    """What the firmware does, in a few lines."""

    def __init__(self, wifi_ok=True, mqtt_ok=True):
        self.got: dict = {}
        self.wifi_ok, self.mqtt_ok = wifi_ok, mqtt_ok
        self.committed = self.aborted = False

    def __call__(self, m: dict) -> dict:
        op, rid = m.get("op"), m["id"]
        if op == "info":
            return {"id": rid, "ok": True, "hw_mac": "24:6F:28:AA:BB:CC", "fw": "0.1.0",
                    "provisioned": False}
        if op in ("set_wifi", "set_mqtt"):
            self.got[op] = m
            return {"id": rid, "ok": True}
        if op == "test":
            return {"id": rid, "ok": True, "wifi": "ok" if self.wifi_ok else "err",
                    "mqtt": "ok" if self.mqtt_ok else "err",
                    "detail": "" if self.mqtt_ok else "broker: error -5"}
        if op == "commit":
            self.committed = True
            return {"id": rid, "ok": True}
        if op == "abort":
            self.aborted = True
            return {"id": rid, "ok": True}
        return {"id": rid, "ok": False, "error": "unknown_op"}


def run_flow(dev: FakeDevice, pop_app=POP, pop_dev=POP, mtu=23):
    device_session = ble.new_session("device", pop_dev)
    transport = ble_client.LoopbackTransport(device_session, dev, mtu)
    client = ble_client.Client(transport, pop_app)
    return asyncio.run(ble_client.provision(client, ssid="Home", password="secret",
                                            bundle=BUNDLE, log=lambda s: None))


def test_provisioning_flow_end_to_end_with_small_mtu():
    dev = FakeDevice()
    result = run_flow(dev, mtu=23)  # the smallest ATT MTU: every frame is many writes
    assert result["wifi"] == "ok" and result["mqtt"] == "ok"
    assert dev.got["set_wifi"]["ssid"] == "Home"
    assert dev.got["set_mqtt"]["psk"] == "ab" * 32
    assert dev.committed and not dev.aborted


def test_failed_test_aborts_and_does_not_commit():
    dev = FakeDevice(mqtt_ok=False)
    with pytest.raises(ble_client.RequestError) as e:
        run_flow(dev)
    assert e.value.code == "test_failed" and "broker" in e.value.detail
    assert dev.aborted and not dev.committed


def test_wrong_code_is_reported_before_anything_is_sent():
    dev = FakeDevice()
    with pytest.raises(ble.SessionError) as e:
        run_flow(dev, pop_app=bytes(16))
    assert e.value.code == "confirm_failed"
    assert not dev.got


def test_factory_page_layout():
    page = ble.factory_page(POP)
    assert len(page) == 4096 and page[:5] == b"MCFP\x01" and page[5:21] == POP
    assert page[25:] == b"\xff" * (4096 - 25)
    import binascii
    assert int.from_bytes(page[21:25], "little") == binascii.crc32(page[:21])


def test_skip_test_commits_without_testing():
    dev = FakeDevice(mqtt_ok=False)  # would fail the test, but it is not run
    device_session = ble.new_session("device", POP)
    client = ble_client.Client(ble_client.LoopbackTransport(device_session, dev), POP)
    asyncio.run(ble_client.provision(client, ssid="Home", password="x", bundle=BUNDLE,
                                     log=lambda s: None, skip_test=True))
    assert dev.committed
