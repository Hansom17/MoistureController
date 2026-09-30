"""BLE pairing session, both roles (contracts/ble.md §4, §7).

The reference the firmware (`firmware/src/core/mc_ble*.c`) and the app are checked against
through `contracts/ble_vectors.json`. Transport independent: bytes in, frames out.
"""

import base64
import hashlib
import hmac
import json
import struct
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

VERSION = 1
SERVICE_UUID = "6d630001-8a3f-4b6e-9d2c-7f1e5a9b0c01"
RX_UUID = "6d630002-8a3f-4b6e-9d2c-7f1e5a9b0c01"  # app -> device (write)
TX_UUID = "6d630003-8a3f-4b6e-9d2c-7f1e5a9b0c01"  # device -> app (notify)
MAX_MESSAGE = 1024
MAX_BODY = MAX_MESSAGE + 16
APP_TO_DEV, DEV_TO_APP = 0, 1
INFO = b"mc-ble-v1"

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class SessionError(Exception):
    """The session must end: bad frame, bad tag, wrong counter, failed confirmation."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# --- label (§7.6) ---------------------------------------------------------------------------


def pop_encode(pop: bytes) -> str:
    n = int.from_bytes(pop, "big")
    bits = len(pop) * 8
    chars = -(-bits // 5)
    n <<= chars * 5 - bits
    return "".join(_CROCKFORD[(n >> (5 * (chars - 1 - i))) & 31] for i in range(chars))


def pop_decode(text: str, size: int = 16) -> bytes:
    text = text.strip().upper().replace("O", "0").replace("I", "1").replace("L", "1")
    chars = -(-size * 8 // 5)
    if len(text) != chars or any(c not in _CROCKFORD for c in text):
        raise ValueError("not a PoP code")
    n = 0
    for c in text:
        n = (n << 5) | _CROCKFORD.index(c)
    n >>= chars * 5 - size * 8
    return n.to_bytes(size, "big")


def label(ble_name: str, pop: bytes) -> str:
    return f"MCPOP1:{ble_name}:{pop_encode(pop)}"


def parse_label(text: str) -> tuple[str, bytes]:
    parts = text.strip().split(":")
    if len(parts) != 3 or parts[0] != "MCPOP1":
        raise ValueError("not a MoistureController label")
    return parts[1], pop_decode(parts[2])


# --- factory page (§7.7) ---------------------------------------------------------------------------


def factory_page(pop: bytes, size: int = 0x1000) -> bytes:
    """The 4 KB page of the `factory` partition: "MCFP", version 1, PoP, CRC32 (little endian)."""
    import binascii

    body = b"MCFP" + bytes([1]) + pop
    page = body + struct.pack("<I", binascii.crc32(body) & 0xFFFFFFFF)
    return page + b"\xff" * (size - len(page))


# --- frames (§7.2) --------------------------------------------------------------------------------


def frame(body: bytes) -> bytes:
    if len(body) > MAX_BODY:
        raise ValueError("frame body too large")
    return struct.pack(">H", len(body)) + body


class FrameReader:
    """Turns the chunks of a stream back into frame bodies."""

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, data: bytes) -> list[bytes]:
        self._buf += data
        out = []
        while len(self._buf) >= 2:
            (n,) = struct.unpack(">H", self._buf[:2])
            if n > MAX_BODY:
                raise SessionError("frame_too_large")
            if len(self._buf) < 2 + n:
                break
            out.append(self._buf[2 : 2 + n])
            self._buf = self._buf[2 + n :]
        return out


def chunks(data: bytes, mtu: int) -> list[bytes]:
    """One ATT write / notification each: at most `mtu - 3` bytes (§7.2)."""
    size = max(mtu - 3, 1)
    return [data[i : i + size] for i in range(0, len(data), size)] or [b""]


# --- key schedule (§4, §7.3) --------------------------------------------------------------------


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def unb64(text: str) -> bytes:
    return base64.b64decode(text, validate=True)


def public_bytes(priv: X25519PrivateKey) -> bytes:
    return priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


@dataclass
class Keys:
    shared: bytes
    k: bytes
    k_enc: bytes
    k_mac: bytes


def derive(priv: X25519PrivateKey, peer_pub: bytes, pop: bytes, a: bytes, b: bytes,
           nonce_d: bytes) -> Keys:
    shared = priv.exchange(X25519PublicKey.from_public_bytes(peer_pub))
    k = HKDF(algorithm=hashes.SHA256(), length=32, salt=pop, info=INFO + a + b + nonce_d).derive(
        shared)
    return Keys(shared, k, k[:16], k[16:])


def confirm_mac(k_mac: bytes, who: str, a: bytes, b: bytes, nonce_d: bytes) -> bytes:
    return hmac.new(k_mac, who.encode() + a + b + nonce_d, hashlib.sha256).digest()


def nonce_for(direction: int, counter: int) -> bytes:
    return bytes([direction, 0, 0, 0]) + struct.pack(">Q", counter)


# --- the session ---------------------------------------------------------------------------------------


@dataclass
class Session:
    """One side of a session. `role` is "app" or "device".

    `feed(data)` takes bytes from the peer and returns `(frames_to_send, messages)`;
    `seal(message)` encrypts one message once the session is open.
    """

    role: str
    pop: bytes
    priv: X25519PrivateKey
    nonce_d: bytes = b""          # the device generates it; the app learns it
    state: str = "new"            # new -> hello_sent|hello_acked -> open
    _reader: FrameReader = field(default_factory=FrameReader)
    _keys: Keys | None = None
    _a: bytes = b""
    _b: bytes = b""
    _send: int = 0
    _recv: int = 0

    @property
    def is_app(self) -> bool:
        return self.role == "app"

    @property
    def open(self) -> bool:
        return self.state == "open"

    @property
    def keys(self) -> Keys | None:
        return self._keys

    def hello(self) -> bytes:
        """App: the first frame."""
        assert self.is_app and self.state == "new"
        self._a = public_bytes(self.priv)
        self.state = "hello_sent"
        return frame(_json({"t": "hello", "v": VERSION, "pub": b64(self._a)}))

    def feed(self, data: bytes) -> tuple[list[bytes], list[dict]]:
        out: list[bytes] = []
        messages: list[dict] = []
        for body in self._reader.feed(data):
            if self.state == "open":
                messages.append(self._open(body))
            else:
                out.extend(self._handshake(body))
        return out, messages

    # handshake --------------------------------------------------------------------------------------

    def _handshake(self, body: bytes) -> list[bytes]:
        try:
            msg = json.loads(body)
            kind = msg["t"]
        except (ValueError, KeyError, TypeError):
            raise SessionError("bad_handshake") from None
        if kind == "error":
            raise SessionError(msg.get("error", "peer_error"))
        try:
            if self.is_app:
                return self._app_handshake(kind, msg)
            return self._device_handshake(kind, msg)
        except (KeyError, ValueError, TypeError):
            raise SessionError("bad_handshake") from None

    def _device_handshake(self, kind: str, msg: dict) -> list[bytes]:
        if kind == "hello" and self.state == "new":
            if msg.get("v") != VERSION:
                raise SessionError("unsupported_version")
            self._a = unb64(msg["pub"])
            if len(self._a) != 32:
                raise SessionError("bad_handshake")
            self._b = public_bytes(self.priv)
            self._keys = derive(self.priv, self._a, self.pop, self._a, self._b, self.nonce_d)
            self.state = "hello_acked"
            return [frame(_json({"t": "hello_ack", "pub": b64(self._b),
                                 "nonce": b64(self.nonce_d)}))]
        if kind == "confirm" and self.state == "hello_acked":
            want = confirm_mac(self._keys.k_mac, "app", self._a, self._b, self.nonce_d)
            if not hmac.compare_digest(unb64(msg["mac"]), want):
                raise SessionError("confirm_failed")
            self.state = "open"
            mac_d = confirm_mac(self._keys.k_mac, "dev", self._a, self._b, self.nonce_d)
            return [frame(_json({"t": "confirm", "mac": b64(mac_d)}))]
        raise SessionError("bad_handshake")

    def _app_handshake(self, kind: str, msg: dict) -> list[bytes]:
        if kind == "hello_ack" and self.state == "hello_sent":
            self._b = unb64(msg["pub"])
            self.nonce_d = unb64(msg["nonce"])
            if len(self._b) != 32 or len(self.nonce_d) != 16:
                raise SessionError("bad_handshake")
            self._keys = derive(self.priv, self._b, self.pop, self._a, self._b, self.nonce_d)
            self.state = "hello_acked"
            mac_a = confirm_mac(self._keys.k_mac, "app", self._a, self._b, self.nonce_d)
            return [frame(_json({"t": "confirm", "mac": b64(mac_a)}))]
        if kind == "confirm" and self.state == "hello_acked":
            want = confirm_mac(self._keys.k_mac, "dev", self._a, self._b, self.nonce_d)
            if not hmac.compare_digest(unb64(msg["mac"]), want):
                raise SessionError("confirm_failed")  # wrong device or wrong code
            self.state = "open"
            return []
        raise SessionError("bad_handshake")

    # encrypted frames -----------------------------------------------------------------------------

    def seal(self, message: dict | bytes) -> bytes:
        assert self.open and self._keys
        plain = message if isinstance(message, bytes) else _json(message)
        if len(plain) > MAX_MESSAGE:
            raise ValueError("message too large")
        direction = APP_TO_DEV if self.is_app else DEV_TO_APP
        body = AESGCM(self._keys.k_enc).encrypt(nonce_for(direction, self._send), plain, None)
        self._send += 1
        return frame(body)

    def _open(self, body: bytes) -> dict:
        assert self._keys
        direction = DEV_TO_APP if self.is_app else APP_TO_DEV
        try:
            plain = AESGCM(self._keys.k_enc).decrypt(nonce_for(direction, self._recv), body, None)
            msg = json.loads(plain)
        except (InvalidTag, ValueError):
            raise SessionError("bad_frame") from None
        self._recv += 1
        return msg


def _json(obj: dict) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()


def new_session(role: str, pop: bytes, priv: X25519PrivateKey | None = None,
                nonce_d: bytes | None = None) -> Session:
    import os

    return Session(role, pop, priv or X25519PrivateKey.generate(),
                   nonce_d if nonce_d is not None else (os.urandom(16) if role == "device" else b""))


# --- test vectors (ble.md §8) ---------------------------------------------------------------------------

VECTOR_POP = bytes(range(16))
_VECTOR_APP = [
    {"id": 1, "op": "info"},
    {"id": 2, "op": "set_wifi", "ssid": "Home \"5G\"", "password": "pa\\ss wörd"},
    {"id": 3, "op": "set_mqtt", "device_id": "mc-8f3kq2v7xw1m9hzt", "host": "192.168.1.20",
     "port": 8883, "psk": "ab" * 32},
    {"id": 4, "op": "fly"},
    {"id": 5, "op": "commit"},
]
_VECTOR_DEVICE = [
    {"id": 1, "ok": True, "hw_mac": "24:6F:28:AA:BB:CC", "fw": "0.1.0", "provisioned": False},
    {"id": 2, "ok": True},
    {"id": 3, "ok": True},
    {"id": 4, "ok": False, "error": "unknown_op"},
    {"id": 5, "ok": True},
]


def clamp(scalar: bytes) -> bytes:
    """RFC 7748 §5 clamping. Stored clamped so every implementation imports the same scalar."""
    b = bytearray(scalar)
    b[0] &= 248
    b[31] &= 127
    b[31] |= 64
    return bytes(b)


_OPS_APP = [
    {"id": 1, "op": "wifi_scan"},
    {"id": 2, "op": "test"},
    {"id": 3, "op": "set_wifi", "ssid": "", "password": "x"},
    {"id": 4, "op": "set_wifi", "ssid": "Home", "password": ""},
    {"id": 5, "op": "set_mqtt", "device_id": "mc-8f3kq2v7xw1m9hzt", "host": "h", "port": 8883,
     "psk": "12"},
    {"id": 6, "op": "set_mqtt", "device_id": "mc-8f3kq2v7xw1m9hzt", "host": "192.168.1.20",
     "port": 8883, "psk": "ab" * 32},
    {"id": 7, "op": "test"},
    {"id": 8, "op": "abort"},
    {"id": 9, "op": "commit"},
    {"id": 10},
]
_OPS_DEVICE = [
    {"id": 1, "ok": True, "networks": [{"ssid": "Home", "rssi": -50, "secure": True},
                                        {"ssid": "Guest", "rssi": -70, "secure": False}]},
    {"id": 2, "ok": False, "error": "not_ready", "detail": "set_wifi and set_mqtt first"},
    {"id": 3, "ok": False, "error": "bad_request", "detail": "ssid 1-32 bytes, password 0-64 bytes"},
    {"id": 4, "ok": True},
    {"id": 5, "ok": False, "error": "bad_request", "detail": "device_id, host, port, psk (64 hex)"},
    {"id": 6, "ok": True},
    {"id": 7, "ok": True, "wifi": "ok", "mqtt": "err", "detail": "tls handshake failed"},
    {"id": 8, "ok": True},
    {"id": 9, "ok": False, "error": "not_ready", "detail": "set_wifi and set_mqtt first"},
    {"id": 10, "ok": False, "error": "bad_request"},
]


def _session_frames(reqs: list[dict], rsps: list[dict], app_seed: bytes, dev_seed: bytes,
                    nonce_d: bytes) -> tuple[list[dict], Session]:
    app = new_session("app", VECTOR_POP, X25519PrivateKey.from_private_bytes(app_seed))
    dev = new_session("device", VECTOR_POP, X25519PrivateKey.from_private_bytes(dev_seed), nonce_d)
    frames: list[dict] = []

    def log(direction: str, data: bytes, note: str) -> None:
        frames.append({"dir": direction, "note": note, "frame": data.hex()})

    h = app.hello()
    log("app->dev", h, "hello")
    (ack,), _ = dev.feed(h)
    log("dev->app", ack, "hello_ack")
    (conf_a,), _ = app.feed(ack)
    log("app->dev", conf_a, "confirm")
    (conf_d,), _ = dev.feed(conf_a)
    log("dev->app", conf_d, "confirm")
    app.feed(conf_d)
    assert app.open and dev.open
    for req, rsp in zip(reqs, rsps, strict=True):
        f = app.seal(req)
        log("app->dev", f, json.dumps(req, separators=(",", ":"), ensure_ascii=False))
        _, msgs = dev.feed(f)
        assert msgs == [req]
        g = dev.seal(rsp)
        log("dev->app", g, json.dumps(rsp, separators=(",", ":")))
        _, msgs = app.feed(g)
        assert msgs == [rsp]
    return frames, app


def vectors() -> dict:
    """Two whole sessions with fixed keys: inputs, intermediates and the exact frames."""
    app_seed = clamp(hashlib.sha256(b"mc-ble-app").digest())
    dev_seed = clamp(hashlib.sha256(b"mc-ble-device").digest())
    nonce_d = hashlib.sha256(b"mc-ble-nonce").digest()[:16]
    app_pub = public_bytes(X25519PrivateKey.from_private_bytes(app_seed))
    dev_pub = public_bytes(X25519PrivateKey.from_private_bytes(dev_seed))
    frames, app = _session_frames(_VECTOR_APP, _VECTOR_DEVICE, app_seed, dev_seed, nonce_d)
    ops_frames, _ = _session_frames(_OPS_APP, _OPS_DEVICE, app_seed, dev_seed, nonce_d)
    k = app.keys
    return {
        "note": "Generated by core/src/mc_core/ble.py; see contracts/ble.md §8. Hex = lowercase.",
        "pop": VECTOR_POP.hex(),
        "app_private": app_seed.hex(),
        "device_private": dev_seed.hex(),
        "nonce_d": nonce_d.hex(),
        "app_public": app_pub.hex(),
        "device_public": dev_pub.hex(),
        "shared": k.shared.hex(),
        "k": k.k.hex(),
        "k_enc": k.k_enc.hex(),
        "k_mac": k.k_mac.hex(),
        "mac_app": confirm_mac(k.k_mac, "app", app_pub, dev_pub, nonce_d).hex(),
        "mac_dev": confirm_mac(k.k_mac, "dev", app_pub, dev_pub, nonce_d).hex(),
        "label": label("MC-3F9A", VECTOR_POP),
        "factory_page": factory_page(VECTOR_POP)[:25].hex(),
        "requests": _VECTOR_APP,
        "responses": _VECTOR_DEVICE,
        "frames": frames,
        "ops_requests": _OPS_APP,
        "ops_responses": _OPS_DEVICE,
        "ops_frames": ops_frames,
    }


def vectors_json() -> str:
    return json.dumps(vectors(), indent=2, ensure_ascii=False) + "\n"
