#!/usr/bin/env python3
"""Dependency gate: the Python dependencies of the api and the hub must match what the gateway image provides.

  check_deps.py            compare pyproject.toml of api and hub with Gateway/update/deps-<app_generation>.txt
  check_deps.py --write    (re)write that snapshot, only for a deliberate generation bump

The snapshot holds one normalised requirement per line (api and hub merged, extras `dev` excluded) and the
`requires-python` constraint. Anything that differs needs new packages on the device, which only an image can bring.
"""
import difflib
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
UPDATE = ROOT / "update"
PROJECTS = [ROOT / "firmware" / "api" / "pyproject.toml", ROOT / "firmware" / "hub" / "pyproject.toml"]
MESSAGE = "bump app_generation and reflash required"


def current() -> list[str]:
    reqs: dict[str, str] = {}
    pythons: set[str] = set()
    for p in PROJECTS:
        project = tomllib.loads(p.read_text())["project"]
        pythons.add(project["requires-python"].replace(" ", ""))
        for line in project.get("dependencies", []):
            r = Requirement(line)
            spec = ",".join(sorted(str(s) for s in r.specifier))
            extras = f"[{','.join(sorted(r.extras))}]" if r.extras else ""
            text = f"{r.name.lower().replace('_', '-')}{extras}{spec}"
            if r.marker:
                text += f" ; {r.marker}"
            # the api and the hub may state different bounds for one package: keep both, so any change shows up
            reqs[text] = text
    if len(pythons) != 1:
        sys.exit(f"api and hub disagree on requires-python: {sorted(pythons)}")
    return [f"python{pythons.pop()}"] + sorted(reqs)


def main() -> int:
    gen_file = UPDATE / "app_generation"
    gen = gen_file.read_text().strip()
    if not gen.isdigit():
        print(f"error: {gen_file} must hold one integer, got {gen!r}")
        return 1
    snap = UPDATE / f"deps-{gen}.txt"
    now = current()
    if "--write" in sys.argv:
        snap.write_text("\n".join(now) + "\n")
        print(f"wrote {snap.relative_to(ROOT.parent)}")
        return 0
    if not snap.is_file():
        print(f"error: {snap.relative_to(ROOT.parent)} is missing for app_generation {gen}: {MESSAGE}")
        return 1
    old = snap.read_text().splitlines()
    if old != now:
        print("\n".join(difflib.unified_diff(old, now, f"deps-{gen}.txt (the image)", "pyproject.toml (this change)", lineterm="")))
        print(f"\nerror: the Python dependencies differ from what the image provides: {MESSAGE}")
        return 1
    print(f"dependencies match deps-{gen}.txt ({len(now) - 1} requirements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
