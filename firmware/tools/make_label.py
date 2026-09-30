#!/usr/bin/env python3
"""Factory step for one device: a PoP, the factory page for flash, and the label (ble.md §2, §7).

    make_label.py --port /dev/cu.usbserial-0001 --flash

generates a random PoP, reads the board's Bluetooth MAC (name MC-XXXX), writes the 4 KB factory
page to the `factory` partition (0x3ff000) and prints the label text (and a QR code if the
`qrcode` package is installed). Without --flash the page is only written to --out.
The PoP is never sent anywhere else: keep the printed label with the device.

    make_label.py --show <32 hex>      print the label for a known PoP (needs --name)
"""

import argparse
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core" / "src"))

from mc_core import ble  # noqa: E402

FACTORY_ADDR = 0x3FF000
PAGE_SIZE = 0x1000


def esptool(*args: str, port: str) -> str:
    cmd = ["esptool", "--port", port, *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True, env=os.environ).stdout


def bluetooth_name(port: str) -> str:
    """The ESP32's Bluetooth MAC is the base MAC + 2; the name carries its last two bytes."""
    out = esptool("read-mac", port=port)
    m = re.search(r"MAC:\s*((?:[0-9a-f]{2}:){5}[0-9a-f]{2})", out, re.I)
    if not m:
        raise SystemExit("could not read the MAC from the board:\n" + out)
    mac = bytearray(int(x, 16) for x in m.group(1).split(":"))
    value = (int.from_bytes(mac, "big") + 2) & ((1 << 48) - 1)
    bt = value.to_bytes(6, "big")
    return f"MC-{bt[4]:02X}{bt[5]:02X}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", help="serial port of the board")
    p.add_argument("--flash", action="store_true", help="write the page to the board")
    p.add_argument("--out", default="factory-page.bin", help="where to write the 4 KB page")
    p.add_argument("--name", help="BLE name (MC-XXXX) if no board is connected")
    p.add_argument("--show", metavar="POP_HEX", help="only print the label for this PoP")
    args = p.parse_args()

    pop = bytes.fromhex(args.show) if args.show else secrets.token_bytes(16)
    name = args.name or (bluetooth_name(args.port) if args.port else None)
    if name is None:
        raise SystemExit("need --port (to read the MAC) or --name")
    text = ble.label(name, pop)

    if not args.show:
        Path(args.out).write_bytes(ble.factory_page(pop, PAGE_SIZE))
        if args.flash:
            if not args.port:
                raise SystemExit("--flash needs --port")
            esptool("write-flash", hex(FACTORY_ADDR), args.out, port=args.port)
            print(f"factory page written to {hex(FACTORY_ADDR)}")
        else:
            print(f"page written to {args.out}; flash it with: esptool write-flash {hex(FACTORY_ADDR)} {args.out}")
    print("PoP (hex) ", pop.hex(), "  <- secret: only on the label")
    print("label     ", text)
    try:
        import qrcode

        q = qrcode.QRCode(border=1)
        q.add_data(text)
        q.print_ascii(invert=True)
    except ImportError:
        print("(install `qrcode` for a QR code of the label)")


if __name__ == "__main__":
    main()
