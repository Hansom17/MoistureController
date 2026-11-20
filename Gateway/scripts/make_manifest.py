#!/usr/bin/env python3
"""Writes manifest.json for a release bundle (the bytes that get signed).

  make_manifest.py <bundle.tar.gz> <app_generation file> <output manifest.json> [released_at]

released_at defaults to the current UTC time. The manifest is written with sorted keys and one trailing newline, and must
be uploaded byte for byte as signed.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SEMVER = r"[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?"


def main() -> int:
    bundle, gen_file, out = (Path(a) for a in sys.argv[1:4])
    m = re.fullmatch(rf"moisture-app-({SEMVER})\.tar\.gz", bundle.name)
    if not m:
        sys.exit(f"unexpected bundle name {bundle.name}")
    version = m.group(1)
    gen = gen_file.read_text().strip()
    if not gen.isdigit():
        sys.exit(f"{gen_file} must hold one integer")
    released = sys.argv[4] if len(sys.argv) > 4 else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = bundle.read_bytes()
    manifest = {
        "schema": 1,
        "version": version,
        "channel": "prerelease" if "-" in version else "stable",
        "app_generation": int(gen),
        "asset": bundle.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "released_at": released,
    }
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
