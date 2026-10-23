#!/usr/bin/env python3
"""Builds the image of the `factory` partition (PlantModule/specs.md §10): board name, serial, optional install code.

    scripts/factory_image.py --board carrier-v1 --serial MC000001 --out factory.bin
    scripts/factory_image.py --board carrier-v1 --serial MC000001 --install-code 83FED3407A9397389D3A6B1B1D8A7F34 \\
                             --require-install-code --out factory.bin

Prints the esptool command that writes it at the partition's offset (read from firmware/partitions.csv).
The layout is the one of firmware/components/mc_core/include/mc_factory.h; the host tests check that the C parser
accepts what this writes. The install code is a secret: keep the image and the code out of git.
"""
import argparse
import re
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARTITIONS = HERE.parent / "firmware" / "partitions.csv"
SIZE = 0x1000
HEADER = 64
VERSION = 1


def crc16_x25(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc ^ 0xFFFF


def build(board: str, serial: str, install_code: bytes | None, required: bool) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,16}", board):
        raise SystemExit("board: 1-16 characters (letters, digits . _ -)")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,12}", serial):
        raise SystemExit("serial: 1-12 characters (letters, digits . _ -)")
    if required and install_code is None:
        raise SystemExit("--require-install-code needs --install-code")
    out = bytearray(b"\xff" * SIZE)
    head = bytearray(HEADER)
    head[0:4] = b"MCF2"
    head[4] = VERSION
    head[5:21] = board.encode().ljust(16, b"\0")
    head[21:33] = serial.encode().ljust(12, b"\0")
    if install_code is None:
        head[33:51] = b"\xff" * 18
    else:
        head[33:49] = install_code
        head[49:51] = struct.pack("<H", crc16_x25(install_code))
    head[51] = 1 if required else 0
    # 52..59 reserved (zero), 60..63 CRC32 over 0..59
    head[60:64] = struct.pack("<I", zlib.crc32(bytes(head[:60])) & 0xFFFFFFFF)
    out[:HEADER] = head
    return bytes(out)


def partition_offset(name: str = "factory") -> int:
    for line in PARTITIONS.read_text().splitlines():
        cols = [c.strip() for c in line.split(",")]
        if cols and cols[0] == name and len(cols) >= 5:
            return int(cols[3], 0)
    raise SystemExit(f"no {name} partition in {PARTITIONS}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", required=True, help="board name, as in firmware/boards/<name>.json")
    ap.add_argument("--serial", required=True)
    ap.add_argument("--install-code", help="32 hex characters (16 bytes); the CRC is added")
    ap.add_argument("--require-install-code", action="store_true", help="the module refuses to join without it")
    ap.add_argument("--out", default="factory.bin")
    args = ap.parse_args()
    code = None
    if args.install_code:
        clean = re.sub(r"[ :-]", "", args.install_code)
        if not re.fullmatch(r"[0-9A-Fa-f]{32}", clean):
            raise SystemExit("install code: 32 hex characters")
        code = bytes.fromhex(clean)
    Path(args.out).write_bytes(build(args.board, args.serial, code, args.require_install_code))
    print(f"wrote {args.out} ({SIZE} bytes)")
    print(f"flash:  python -m esptool --port <port> write-flash 0x{partition_offset():x} {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
