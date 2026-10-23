#!/usr/bin/env python3
"""Generates the C table of the board descriptions from PlantModule/firmware/boards/*.json.

    python PlantModule/scripts/gen_boards.py           # writes components/mc_core/src/mc_boards_table.c
    python PlantModule/scripts/gen_boards.py --check   # exits 1 when the generated file or a hub copy is out of date

The JSON files are the single source; the hub keeps byte-identical copies (Gateway/firmware/hub/src/mc_hub/boards).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARDS = ROOT / "PlantModule" / "firmware" / "boards"
HUB_COPY = ROOT / "Gateway" / "firmware" / "hub" / "src" / "mc_hub" / "boards"
OUT = ROOT / "PlantModule" / "firmware" / "components" / "mc_core" / "src" / "mc_boards_table.c"
ROLES = {"moisture": "MC_ROLE_MOISTURE", "pump": "MC_ROLE_PUMP"}


def load() -> list[dict]:
    boards = [json.loads(p.read_text()) for p in sorted(BOARDS.glob("*.json"))]
    for b in boards:
        assert b["schema"] == 1, f"{b['name']}: unknown schema"
        assert 1 <= len(b["ports"]) <= 6, f"{b['name']}: 1..6 ports"
        for i, p in enumerate(b["ports"]):
            assert p["id"] == f"P{i + 1}", f"{b['name']}: ports must be P1..Pn in order"
            assert set(p["roles"]) <= set(ROLES), f"{b['name']}: unknown role"
    return boards


def render() -> str:
    out = [
        "/* GENERATED from the JSON files in PlantModule/firmware/boards by PlantModule/scripts/gen_boards.py. Do not edit. */",
        '#include "mc_board.h"',
        "",
        "#include <string.h>",
        "",
    ]
    for b in load():
        ident = b["name"].replace("-", "_")
        out.append(f"static const mc_board_t board_{ident} = {{")
        out.append(f'    .name = "{b["name"]}",')
        out.append(f'    .hw_version = {b["hw_version"]},')
        out.append(f'    .allow_raw_gpio = {"true" if b["allow_raw_gpio"] else "false"},')
        out.append(f'    .port_count = {len(b["ports"])},')
        led, btn, bat = b.get("led"), b.get("button"), b.get("battery")
        out.append(f'    .led = {{ .gpio = {led["gpio"] if led else -1}, .active_high = {"true" if not led or led["active_high"] else "false"} }},')
        out.append(f'    .button = {{ .gpio = {btn["gpio"] if btn else -1}, .active_high = {"false" if not btn or btn["active_low"] else "true"} }},')
        out.append(f'    .battery_gpio = {bat["gpio"] if bat else -1},')
        out.append(f'    .battery_divider_x100 = {round(bat["divider"] * 100) if bat else 100},')
        out.append("    .ports = {")
        for p in b["ports"]:
            roles = " | ".join(ROLES[r] for r in p["roles"]) or "0"
            out.append(f'        {{ .gpio = {p["gpio"]}, .roles = {roles} }},')
        out.append("    },")
        out.append("};")
        out.append("")
    names = [b["name"].replace("-", "_") for b in load()]
    out.append("static const mc_board_t *const all_boards[] = {")
    out += [f"    &board_{n}," for n in names]
    out += ["};", "",
            "const mc_board_t *mc_board_find(const char *name)",
            "{",
            "    for (size_t i = 0; i < sizeof all_boards / sizeof all_boards[0]; i++) {",
            "        if (strcmp(all_boards[i]->name, name) == 0) {",
            "            return all_boards[i];",
            "        }",
            "    }",
            "    return NULL;",
            "}", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = render()
    if args.check:
        bad = []
        if not OUT.exists() or OUT.read_text() != text:
            bad.append(f"{OUT.relative_to(ROOT)} is out of date")
        for p in sorted(BOARDS.glob("*.json")):
            copy = HUB_COPY / p.name
            if not copy.exists() or copy.read_bytes() != p.read_bytes():
                bad.append(f"{copy.relative_to(ROOT)} differs from {p.relative_to(ROOT)}")
        if bad:
            print("\n".join(bad) + "\nrun PlantModule/scripts/gen_boards.py", file=sys.stderr)
            return 1
        print("board tables and hub copies are up to date")
        return 0
    OUT.write_text(text)
    for p in sorted(BOARDS.glob("*.json")):
        (HUB_COPY / p.name).write_bytes(p.read_bytes())
    print(f"wrote {OUT.relative_to(ROOT)} and the hub copies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
