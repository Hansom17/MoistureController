#!/usr/bin/env python3
"""Pairs a device over Bluetooth from the command line: the app's wizard, for the bench.

    ble_provision.py --label 'MCPOP1:MC-3F9A:…' --bundle bundle.json --ssid Home
    ble_provision.py --label '…' --scan            # list the WiFi networks the device sees

`bundle.json` is what the API returns for a new device (`POST /households/{h}/devices` →
`{"device": …, "bundle": {"device_id", "mqtt": {host, port, psk}}}`, or just the bundle).
The WiFi password is asked for (or MC_WIFI_PASSWORD). Needs `bleak` (pip install bleak).
"""

import argparse
import asyncio
import getpass
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core" / "src"))

from mc_core import ble, ble_client  # noqa: E402


class BleakTransport:
    """mc_core.ble_client.Transport over a bleak connection."""

    def __init__(self, bleak_client) -> None:
        self._c = bleak_client
        self._q: asyncio.Queue[bytes] = asyncio.Queue()
        self.mtu = max(getattr(bleak_client, "mtu_size", 23), 23)

    def _on_notify(self, _sender, data: bytearray) -> None:
        self._q.put_nowait(bytes(data))

    async def start(self) -> None:
        await self._c.start_notify(ble.TX_UUID, self._on_notify)

    async def write(self, data: bytes) -> None:
        await self._c.write_gatt_char(ble.RX_UUID, data, response=True)

    async def read(self, timeout: float) -> bytes:
        try:
            return await asyncio.wait_for(self._q.get(), timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError("no answer from the device") from e


async def run(args) -> int:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("this tool needs bleak: pip install bleak", file=sys.stderr)
        return 2

    name, pop = ble.parse_label(args.label)
    bundle, password = {}, ""
    if not args.scan:
        # asked before connecting: the device drops a connection without a handshake after 10 s
        bundle = json.loads(Path(args.bundle).read_text())
        bundle = bundle.get("bundle", bundle)
        if args.host:  # the bundle carries the gateway's own idea of its address (e.g. localhost)
            bundle["mqtt"]["host"] = args.host
        password = os.environ.get("MC_WIFI_PASSWORD") or getpass.getpass(
            f"WiFi password for {args.ssid}: ")

    print(f"looking for {name} …")
    device = await BleakScanner.find_device_by_name(name, timeout=args.timeout)
    if device is None:
        print(f"{name} not found: is the pairing window open (unpaired device, or BOOT held 3 s)?",
              file=sys.stderr)
        return 1

    async with BleakClient(device, timeout=20) as bc:
        transport = BleakTransport(bc)
        await transport.start()
        print(f"connected, ATT MTU {transport.mtu}")
        client = ble_client.Client(transport, pop)

        if args.scan:
            await client.open()
            for n in await client.wifi_scan():
                print(f"  {n['rssi']:4d} dBm  {'secured' if n['secure'] else 'open   '}  {n['ssid']}")
            return 0

        try:
            await ble_client.provision(client, ssid=args.ssid, password=password, bundle=bundle,
                                       skip_test=args.skip_test)
        except ble.SessionError as e:
            why = "wrong device or wrong code" if e.code == "confirm_failed" else e.code
            print(f"pairing failed: {why}", file=sys.stderr)
            return 1
        except ble_client.RequestError as e:
            print(f"pairing failed: {e}", file=sys.stderr)
            return 1
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", required=True, help="MCPOP1:<name>:<pop> from the device label")
    p.add_argument("--bundle", help="JSON file with the pairing bundle from the API")
    p.add_argument("--ssid", help="WiFi network name")
    p.add_argument("--scan", action="store_true", help="only list the device's WiFi networks")
    p.add_argument("--host", help="gateway LAN address to give the device (overrides the bundle's)")
    p.add_argument("--skip-test", action="store_true", help="commit without the WiFi/broker test (bench only)")
    p.add_argument("--timeout", type=float, default=20, help="seconds to look for the device")
    args = p.parse_args()
    if not args.scan and not (args.bundle and args.ssid):
        p.error("need --bundle and --ssid (or --scan)")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
