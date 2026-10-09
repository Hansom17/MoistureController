# MoistureController

Monitor the soil moisture of plants with small battery-powered ESP32 devices, see it in an app, and water manually or by rule — also when the internet is down.

| Folder | What it is |
|---|---|
| [`PlantModule/`](PlantModule/) | The plant device: Zephyr firmware, KiCad carrier board, label/provisioning scripts |
| [`Gateway/`](Gateway/) | At home: Mosquitto + gateway service (adapters, local rules, offline buffer) |
| [`Server/`](Server/) | Central FastAPI + PostgreSQL API, Firebase config |
| [`App/`](App/) | Flutter app (web + mobile) |
| [`Shared/core/`](Shared/core/) | Python package `mc_core` used by Gateway and Server: contract models, rules engine, command checks |
| [`scripts/`](scripts/) | `dev-start.sh` / `dev-stop.sh`: the whole system on one machine |

Each product folder has a `specs.md` (design) and a `readme.md` (build, run, test). The system-level architecture, flows and decisions are in [`PROJECT.md`](PROJECT.md).

## Try it on one machine

Needs Docker, Python 3.13 and Flutter.

```bash
scripts/dev-start.sh        # API + PostgreSQL, gateway + Mosquitto, simulated plant device, web app on :8420
scripts/dev-stop.sh --wipe  # stop and delete the dev data
```

## Tests

```bash
cd Shared/core && ../../.venv/bin/python -m pytest
cd Server && ../.venv/bin/python -m pytest
cd Gateway/firmware && ../../.venv/bin/python -m pytest
cd App && flutter test
PlantModule/scripts/test.py        # firmware unit tests on QEMU (needs the Zephyr workspace)
```
