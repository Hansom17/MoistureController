#!/usr/bin/env python3
"""Validates `MCPUB <suffix> <payload>` lines (from the unit tests) with the contract models.

Reads stdin; exits non-zero if any message does not validate or exceeds 2048 bytes.
Run with the repository's Python (`.venv/bin/python`): it needs mc_core and pydantic.
"""

import sys

from mc_core.contract.device import CmdAck, ConfigState, Event, Status, Telemetry

MODELS = {"status": Status, "telemetry": Telemetry, "event": Event, "cmd/ack": CmdAck,
          "config/state": ConfigState}

seen: dict[str, int] = {}
bad = 0
for line in sys.stdin:
    if not line.startswith("MCPUB "):
        continue
    _, suffix, payload = line.rstrip("\n").split(" ", 2)
    model = MODELS.get(suffix)
    try:
        if model is None:
            raise ValueError(f"unknown topic {suffix}")
        if len(payload.encode()) > 2048:
            raise ValueError("payload over 2048 bytes (mqtt.md §9)")
        model.model_validate_json(payload)
        seen[suffix] = seen.get(suffix, 0) + 1
    except Exception as e:  # noqa: BLE001
        bad += 1
        print(f"INVALID {suffix}: {e}\n  {payload}")

print("contract check:", ", ".join(f"{n}× {s}" for s, n in sorted(seen.items())) or "no messages")
missing = set(MODELS) - set(seen)
if missing:
    bad += 1
    print("not covered:", ", ".join(sorted(missing)))
sys.exit(1 if bad else 0)
