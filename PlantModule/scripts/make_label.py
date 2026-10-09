#!/usr/bin/env python3
"""Factory step for a device: PoP, label (QR code) and the factory page, kept in a CSV.

The CSV (`PlantModule/scripts/factory/devices.csv`, git-ignored: it holds the secret PoPs) is the
single record of every device made. One row per device:

    ble_name, bt_mac, pop_hex, label, created_at, flashed_at

    make_label.py new   --port /dev/cu.usbserial-0001      # PoP + CSV row + QR png + page
    make_label.py flash --port /dev/cu.usbserial-0001      # write that row's page to the board
    make_label.py new   --port … --flash                   # both in one go
    make_label.py qr    MC-26EA                            # (re)draw the QR code of a row
    make_label.py new   --name MC-26EA --mac 68:FE:… --pop <32 hex>   # record a PoP made earlier
    make_label.py list

Without a board: `new --name MC-26EA [--mac 68:FE:71:81:26:EA]`. The label text is
`MCPOP1:<ble-name>:<pop>` (PlantModule/specs.md Part B §7.6); the PoP is never sent anywhere.

QR images: uses the `segno` package if installed, else on macOS the bundled Swift script
(tools/qr_png.swift); otherwise only the label text is printed.
"""

import argparse
import csv
import datetime as dt
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Shared" / "core" / "src"))

from mc_core import ble  # noqa: E402

FACTORY_ADDR = 0x3FF000
PAGE_SIZE = 0x1000
FIELDS = ["ble_name", "bt_mac", "pop_hex", "label", "created_at", "flashed_at"]
DEFAULT_DIR = ROOT / "PlantModule" / "scripts" / "factory"


class ToolError(Exception):
    pass


# --- the CSV ---------------------------------------------------------------------------------------


class Registry:
    def __init__(self, path: Path):
        self.path = path

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(newline="") as f:
            return list(csv.DictReader(f))

    def _write(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        os.chmod(tmp, 0o600)  # secrets
        tmp.replace(self.path)

    def find(self, name: str | None = None, mac: str | None = None) -> dict | None:
        """By MAC if known (unique), else by name; two devices with one name need the MAC."""
        rows = self.rows()
        if mac:
            hits = [r for r in rows if r["bt_mac"].lower() == mac.lower()]
        elif name:
            hits = [r for r in rows if r["ble_name"].upper() == name.upper()]
        else:
            return None
        if len(hits) > 1:
            raise ToolError(f"{len(hits)} devices are called {name}: pass --mac to pick one")
        return hits[0] if hits else None

    def add(self, name: str, mac: str, pop: bytes) -> dict:
        if self.find(name=name if not mac else None, mac=mac or None):
            raise ToolError(f"{mac or name} is already in {self.path} (use `flash` or `qr`)")
        row = {
            "ble_name": name, "bt_mac": mac, "pop_hex": pop.hex(), "label": ble.label(name, pop),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "flashed_at": "",
        }
        self._write([*self.rows(), row])
        return row

    def mark_flashed(self, row: dict) -> None:
        rows = self.rows()
        for r in rows:
            if r["pop_hex"] == row["pop_hex"]:
                r["flashed_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        self._write(rows)


# --- board access (esptool) ----------------------------------------------------------------------------


def esptool(*args: str, port: str) -> str:
    cmd = ["esptool", "--port", port, *args]
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    except FileNotFoundError as e:
        raise ToolError("esptool not found: activate the Zephyr venv (~/zephyrproject/.venv)") from e
    except subprocess.CalledProcessError as e:
        raise ToolError(f"esptool failed:\n{e.stdout}{e.stderr}") from e


def bluetooth_identity(port: str) -> tuple[str, str]:
    """(BLE name, Bluetooth MAC). The ESP32's Bluetooth MAC is the base MAC + 2."""
    out = esptool("read-mac", port=port)
    m = re.search(r"MAC:\s*((?:[0-9a-f]{2}:){5}[0-9a-f]{2})", out, re.I)
    if not m:
        raise ToolError("could not read the MAC from the board:\n" + out)
    value = (int(m.group(1).replace(":", ""), 16) + 2) & ((1 << 48) - 1)
    bt = value.to_bytes(6, "big")
    return f"MC-{bt[4]:02X}{bt[5]:02X}", ":".join(f"{b:02X}" for b in bt)


def write_page(port: str, row: dict, directory: Path) -> Path:
    page = directory / "pages" / f"{row['ble_name']}.bin"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_bytes(ble.factory_page(bytes.fromhex(row["pop_hex"]), PAGE_SIZE))
    esptool("write-flash", hex(FACTORY_ADDR), str(page), port=port)
    return page


# --- QR code -------------------------------------------------------------------------------------------------


def qr_png(text: str, out: Path) -> str | None:
    """Writes the QR code; returns how, or None if no generator is available."""
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        import segno

        segno.make(text, error="m").save(str(out), scale=12, border=4)
        return "segno"
    except ImportError:
        pass
    if sys.platform == "darwin" and shutil.which("swift"):
        script = Path(__file__).with_name("qr_png.swift")
        r = subprocess.run(["swift", str(script), text, str(out)], capture_output=True, text=True)
        if r.returncode == 0:
            return "swift"
    return None


# --- commands ------------------------------------------------------------------------------------------------


def cmd_new(args, reg: Registry) -> None:
    name, mac = args.name, args.mac or ""
    if args.port:
        name, mac = bluetooth_identity(args.port)
    if not name:
        raise ToolError("need --port (read the MAC from the board) or --name")
    if not re.fullmatch(r"MC-[0-9A-F]{4}", name):
        raise ToolError("the BLE name looks like MC-3F9A")
    pop = bytes.fromhex(args.pop) if args.pop else secrets.token_bytes(16)
    if len(pop) != 16:
        raise ToolError("a PoP is 16 bytes (32 hex characters)")
    row = reg.add(name, mac, pop)
    print(f"added {name} to {reg.path}")
    cmd_qr_row(row, args)
    if args.flash:
        if not args.port:
            raise ToolError("--flash needs --port")
        flash_row(row, args, reg)


def flash_row(row: dict, args, reg: Registry) -> None:
    write_page(args.port, row, Path(args.dir))
    reg.mark_flashed(row)
    print(f"factory page of {row['ble_name']} written to {hex(FACTORY_ADDR)}")


def cmd_flash(args, reg: Registry) -> None:
    name, mac = args.name, args.mac
    if args.port and not (name or mac):
        name, mac = bluetooth_identity(args.port)  # which board is this?
    row = reg.find(name=name, mac=mac)
    if row is None:
        raise ToolError(f"{mac or name} is not in {reg.path}: run `new` first")
    if not args.port:
        raise ToolError("flash needs --port")
    flash_row(row, args, reg)


def cmd_qr_row(row: dict, args) -> None:
    out = Path(args.dir) / "labels" / f"{row['ble_name']}.png"
    how = qr_png(row["label"], out)
    print("label    ", row["label"])
    print("QR code  ", f"{out} ({how})" if how else "not written: pip install segno (or use macOS with Xcode)")


def cmd_qr(args, reg: Registry) -> None:
    row = reg.find(name=args.name, mac=args.mac)
    if row is None:
        raise ToolError(f"{args.name} is not in {reg.path}")
    cmd_qr_row(row, args)


def cmd_list(args, reg: Registry) -> None:
    rows = reg.rows()
    for r in rows:
        print(f"{r['ble_name']:8} {r['bt_mac']:17} created {r['created_at'][:10]}  "
              f"{'flashed ' + r['flashed_at'][:10] if r['flashed_at'] else 'not flashed'}")
    if not rows:
        print(f"no devices in {reg.path}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="factory directory (CSV, labels, pages)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def board(sp, need_name=False):
        sp.add_argument("--port", help="serial port of the board")
        sp.add_argument("--name", help="BLE name MC-XXXX")
        sp.add_argument("--mac", help="Bluetooth MAC (AA:BB:…), to tell same-named devices apart")

    n = sub.add_parser("new", help="make a PoP, CSV row, QR code and page for a device")
    board(n)
    n.add_argument("--flash", action="store_true", help="also write the page to the board")
    n.add_argument("--pop", metavar="HEX", help="record an already assigned PoP instead of making one")
    f = sub.add_parser("flash", help="write a device's page from the CSV to the board")
    board(f)
    q = sub.add_parser("qr", help="(re)draw the QR code of a device in the CSV")
    q.add_argument("name")
    q.add_argument("--mac")
    sub.add_parser("list", help="the devices in the CSV")

    args = p.parse_args(argv)
    reg = Registry(Path(args.dir) / "devices.csv")
    try:
        {"new": cmd_new, "flash": cmd_flash, "qr": cmd_qr, "list": cmd_list}[args.cmd](args, reg)
    except ToolError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
