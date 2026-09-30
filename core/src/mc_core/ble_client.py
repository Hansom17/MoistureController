"""App side of the BLE pairing flow (contracts/ble.md §6, §7), transport independent.

The reference for what the Flutter wizard does; `firmware/tools/ble_provision.py` runs it over
a real Bluetooth connection (bleak), the tests over a loopback to `mc_core.ble`.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from . import ble


class Transport(Protocol):
    """One BLE connection, notifications already enabled."""

    mtu: int

    async def write(self, data: bytes) -> None:
        """One ATT write (at most mtu - 3 bytes)."""

    async def read(self, timeout: float) -> bytes:
        """The next notification's bytes; raises TimeoutError."""


class RequestError(Exception):
    """The device answered `ok: false`."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class Client:
    def __init__(self, transport: Transport, pop: bytes):
        self.t = transport
        self.session = ble.new_session("app", pop)
        self._next_id = 0
        self._inbox: list[dict] = []

    async def _send(self, data: bytes) -> None:
        for chunk in ble.chunks(data, self.t.mtu):
            await self.t.write(chunk)

    async def _pump(self, timeout: float) -> None:
        out, messages = self.session.feed(await self.t.read(timeout))
        for frame in out:
            await self._send(frame)
        self._inbox.extend(messages)

    async def open(self, timeout: float = 10) -> None:
        """The handshake. Raises ble.SessionError('confirm_failed') for a wrong device or code."""
        await self._send(self.session.hello())
        while not self.session.open:
            await self._pump(timeout)

    async def request(self, op: str, timeout: float = 15, **fields) -> dict:
        self._next_id += 1
        rid = self._next_id
        await self._send(self.session.seal({"id": rid, "op": op, **fields}))
        while True:
            for i, msg in enumerate(self._inbox):
                if msg.get("id") == rid:
                    del self._inbox[i]
                    if not msg.get("ok"):
                        raise RequestError(msg.get("error", "failed"), msg.get("detail", ""))
                    return msg
            await self._pump(timeout)

    # the operations of §7.5 -----------------------------------------------------------------

    async def info(self) -> dict:
        return await self.request("info")

    async def wifi_scan(self) -> list[dict]:
        return (await self.request("wifi_scan", timeout=20))["networks"]

    async def set_wifi(self, ssid: str, password: str) -> None:
        await self.request("set_wifi", ssid=ssid, password=password)

    async def set_mqtt(self, device_id: str, host: str, port: int, psk: str) -> None:
        await self.request("set_mqtt", device_id=device_id, host=host, port=port, psk=psk)

    async def test(self) -> dict:
        return await self.request("test", timeout=60)

    async def commit(self) -> None:
        await self.request("commit")

    async def abort(self) -> None:
        await self.request("abort")


async def provision(client: Client, *, ssid: str, password: str, bundle: dict,
                    log: Callable[[str], None] = print,
                    confirm_test: Callable[[dict], Awaitable[bool]] | None = None,
                    skip_test: bool = False) -> dict:
    """The app flow after the API call: handshake, settings, test, commit.

    `bundle` is the pairing bundle the API returned: {"device_id", "mqtt": {"host", "port", "psk"}}.
    Returns the `test` result; raises RequestError / ble.SessionError.
    """
    await client.open()
    info = await client.info()
    log(f"device {info['hw_mac']}, firmware {info['fw']}, provisioned={info['provisioned']}")
    await client.set_wifi(ssid, password)
    m = bundle["mqtt"]
    await client.set_mqtt(bundle["device_id"], m["host"], m["port"], m["psk"])
    if skip_test:  # bench only: the app always tests before it commits
        await client.commit()
        log("committed without a test: the device restarts")
        return {"wifi": "skipped", "mqtt": "skipped"}
    log("testing WiFi and the gateway connection …")
    result = await client.test()
    log(f"test: wifi {result['wifi']}, mqtt {result['mqtt']} {result.get('detail', '')}")
    if result["wifi"] != "ok" or result["mqtt"] != "ok":
        await client.abort()
        raise RequestError("test_failed", result.get("detail", ""))
    if confirm_test is not None and not await confirm_test(result):
        await client.abort()
        raise RequestError("cancelled")
    await client.commit()
    log("committed: the device restarts")
    return result


class LoopbackTransport:
    """A device session (mc_core.ble) wired straight to a client, for tests."""

    def __init__(self, device: "ble.Session", handler: Callable[[dict], dict], mtu: int = 23):
        self.mtu = mtu
        self._device = device
        self._handler = handler
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.closed = False

    async def write(self, data: bytes) -> None:
        assert len(data) <= self.mtu - 3, "ATT write too large"
        out, messages = self._device.feed(data)
        for frame in out:
            await self._notify(frame)
        for msg in messages:
            await self._notify(self._device.seal(self._handler(msg)))

    async def _notify(self, frame: bytes) -> None:
        for chunk in ble.chunks(frame, self.mtu):
            await self._queue.put(chunk)

    async def read(self, timeout: float) -> bytes:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError from e
