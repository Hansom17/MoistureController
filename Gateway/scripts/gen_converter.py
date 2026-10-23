#!/usr/bin/env python3
"""Generates the data part of the Zigbee2MQTT converter from PlantModule/interface.yaml (decision D17).

    python Gateway/scripts/gen_converter.py            # writes external_converters/mc-plant/interface.mjs
    python Gateway/scripts/gen_converter.py --check    # exits 1 when the committed file is out of date

The hand-written logic (codec, definition) lives next to it and only reads this data.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "PlantModule" / "interface.yaml"
OUT = ROOT / "Gateway" / "firmware" / "zigbee2mqtt" / "external_converters" / "mc-plant" / "interface.mjs"

HEADER = """// GENERATED from PlantModule/interface.yaml by Gateway/scripts/gen_converter.py. Do not edit:
// change the interface file and run the generator again (a test fails while they differ).
"""


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.capitalize() for p in rest)


def build() -> dict:
    d = yaml.safe_load(SRC.read_text())
    c = d["custom_cluster"]

    def command(cmd: dict) -> dict:
        # optional fields (the planned sensor_sample result) are not part of the wire format yet
        return {
            "id": cmd["id"],
            "name": camel(cmd["name"]),
            "interfaceName": cmd["name"],
            "fields": [dict(f) for f in cmd["fields"] if not f.get("optional")],
            "mqtt": cmd.get("mqtt_set") or cmd.get("mqtt"),
        }

    return {
        "interfaceVersion": [d["interface"]["version"]["major"], d["interface"]["version"]["minor"]],
        "configSchema": d["interface"]["config_schema"],
        "identity": {"manufacturer": d["identity"]["manufacturer"], "model": d["identity"]["model"],
                     "endpoint": d["identity"]["endpoint"]},
        "cluster": {"id": c["id"], "manufacturerCode": c["manufacturer_code"]},
        "attributes": [
            {"id": a["id"], "name": a["name"], "type": a["type"], "access": a["access"], "mqtt": a.get("mqtt"),
             "layout": a.get("layout"), "enum": a.get("enum"), "range": a.get("range"), "default": a.get("default")}
            for a in c["attributes"]
        ],
        "commandsIn": [command(x) for x in c["commands_in"] if x.get("status") != "planned"],
        "commandsOut": [command(x) for x in c["commands_out"]],
        "enums": {name: {str(k): v for k, v in m.items()} for name, m in d["enums"].items()},
        "reporting": d["reporting"],
    }


def render() -> str:
    return HEADER + "export default " + json.dumps(build(), indent=2) + ";\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT.relative_to(ROOT)} is out of date: run Gateway/scripts/gen_converter.py", file=sys.stderr)
            return 1
        print("converter data is up to date")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
