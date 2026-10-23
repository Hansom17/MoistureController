"""Board descriptions (Gateway/specs.md section 6, PlantModule/specs.md 2.1).

These files are a copy of the PlantModule's `firmware/boards/*.json`; once the firmware exists
the build copies them here. They back the `boards` snapshot and the config validation.
"""
import json
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "boards"


@lru_cache
def all_boards() -> dict[str, dict]:
    out = {}
    for f in sorted(DIR.glob("*.json")):
        b = json.loads(f.read_text())
        out[b["name"]] = b
    return out


def get(name: str | None) -> dict | None:
    return all_boards().get(name or "")
