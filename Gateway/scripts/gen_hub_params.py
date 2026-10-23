#!/usr/bin/env python3
"""Generates the hub's parameters from PlantModule/interface.yaml (decision D17): the ranges and defaults of the
device configuration and the battery tunables, so the hub repeats no number that the interface file owns.

    python Gateway/scripts/gen_hub_params.py           # writes hub/src/mc_hub/params.py
    python Gateway/scripts/gen_hub_params.py --check   # exits 1 when the committed file is out of date
"""
import argparse
import pprint
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "PlantModule" / "interface.yaml"
OUT = ROOT / "Gateway" / "firmware" / "hub" / "src" / "mc_hub" / "params.py"

HEADER = '''"""GENERATED from PlantModule/interface.yaml by Gateway/scripts/gen_hub_params.py. Do not edit:
change the interface file and run the generator again (a hub test fails while they differ)."""

'''


def build() -> dict:
    d = yaml.safe_load(SRC.read_text())
    config = {
        a["name"]: {"default": a["default"], "min": a["range"][0], "max": a["range"][1]}
        for a in d["custom_cluster"]["attributes"]
        if "rw" in a["access"] and "range" in a and "default" in a
    }
    b = d["battery"]
    battery = {
        "chemistry": b["chemistry"],
        "present_min_mv": b["classify"]["present_min_mv"],
        "history_reports": b["hub"]["history_reports"],
        "stale_factor": b["hub"]["stale_factor"],
        "percent_curves": {k: [tuple(p) for p in v] for k, v in b["hub"]["percent_curves"].items()},
    }
    return {"CONFIG": config, "BATTERY": battery}


def render() -> str:
    parts = [HEADER]
    for name, value in build().items():
        parts.append(f"{name} = {pprint.pformat(value, width=110, sort_dicts=False)}\n\n")
    return "".join(parts).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT.relative_to(ROOT)} is out of date: run Gateway/scripts/gen_hub_params.py", file=sys.stderr)
            return 1
        print("hub parameters are up to date")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
