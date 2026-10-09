#!/usr/bin/env python3
"""Generates the C header of the Zigbee interface from PlantModule/interface.yaml (decision D17).

    python PlantModule/scripts/gen_interface_h.py           # writes components/mc_core/include/mc_interface.h
    python PlantModule/scripts/gen_interface_h.py --check   # exits 1 when the committed header is out of date
"""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "PlantModule" / "interface.yaml"
OUT = ROOT / "PlantModule" / "firmware" / "components" / "mc_core" / "include" / "mc_interface.h"


def up(name: str) -> str:
    return name.upper()


def render() -> str:
    d = yaml.safe_load(SRC.read_text())
    c = d["custom_cluster"]
    v = d["interface"]["version"]
    out = [
        "/* GENERATED from PlantModule/interface.yaml by PlantModule/scripts/gen_interface_h.py. Do not edit:",
        " * change the interface file and run the generator again (the host tests fail while they differ). */",
        "#ifndef MC_INTERFACE_H",
        "#define MC_INTERFACE_H",
        "",
        f'#define MC_MODEL "{d["identity"]["model"]}"',
        f'#define MC_MANUFACTURER "{d["identity"]["manufacturer"]}"',
        f'#define MC_ENDPOINT {d["identity"]["endpoint"]}',
        f'#define MC_CLUSTER_ID 0x{c["id"]:04X}',
        f'#define MC_MANUFACTURER_CODE 0x{c["manufacturer_code"]:04X}',
        f'#define MC_INTERFACE_VERSION 0x{(v["major"] << 8) | v["minor"]:04X}',
        f'#define MC_CONFIG_SCHEMA {d["interface"]["config_schema"]}',
        "",
        "/* attribute ids of the custom cluster */",
    ]
    for a in c["attributes"]:
        out.append(f'#define MC_ATTR_{up(a["name"])} 0x{a["id"]:04X}')
    out += ["", "/* limits and defaults of the writable configuration attributes */"]
    for a in c["attributes"]:
        if "rw" in a["access"] and "range" in a:
            lo, hi = a["range"]
            out.append(f'#define MC_CFG_{up(a["name"])}_MIN {lo}')
            out.append(f'#define MC_CFG_{up(a["name"])}_MAX {hi}')
        if "rw" in a["access"] and "default" in a:
            out.append(f'#define MC_CFG_{up(a["name"])}_DEFAULT {a["default"]}')
    out += ["", "/* cluster commands, coordinator to module */"]
    for x in c["commands_in"]:
        out.append(f'#define MC_CMD_IN_{up(x["name"])} 0x{x["id"]:02X}')
    out += ["", "/* cluster commands, module to coordinator */"]
    for x in c["commands_out"]:
        out.append(f'#define MC_CMD_OUT_{up(x["name"])} 0x{x["id"]:02X}')
    out += ["", "/* enumerations (values as on the air) */"]
    for name, members in d["enums"].items():
        out.append("typedef enum {")
        for value, label in members.items():
            out.append(f"    MC_{up(name)}_{up(label)} = {value},")
        out.append(f"}} mc_{name}_t;")
        out.append("")
    out += ["#endif /* MC_INTERFACE_H */", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT.relative_to(ROOT)} is out of date: run PlantModule/scripts/gen_interface_h.py", file=sys.stderr)
            return 1
        print("interface header is up to date")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
