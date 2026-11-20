# Gateway

The box at home that runs the whole system: Zigbee coordinator with Zigbee2MQTT, Mosquitto, and two services that talk only over MQTT: `hub` (devices, command queue, rules, alerts, Telegram) and `api` (login, REST + SSE, hosting of the Flutter web build; can run on another device). Design: [`specs.md`](specs.md).

**State:** specification, plus the `hub` (`firmware/hub`) and the `api` (`firmware/api`) services (see `specs.md` §18). The target layout is in `specs.md` §15.3 (`firmware/hub`, `firmware/api`, `mqtt-contract.yaml`, `scripts/`, `hardware/`). The previous gateway and server implementation is in git history at commit `eb97b07`; `specs.md` §19 lists what to take from it.

## Install and run

The gateway runs as a Yocto image (systemd services, Zigbee2MQTT, Mosquitto) built in the repository [Hansom17/moisture-gateway](https://github.com/Hansom17/moisture-gateway), which is also where installing and flashing it is described. The app code (`hub`, `api`, web build, converter) is updated from the releases of this repository.

To try the system on a development machine without a gateway: `scripts/bench.sh` (hub, api and a Zigbee2MQTT bench setup on the host), or `scripts/z2m_sim.py` as the Zigbee side; set `MC_WEB_DIR` to `App/build/web`. Details in `specs.md` §15. Backup and restore of a gateway: [docs/BACKUP.md](docs/BACKUP.md).

## Releases and updates

A tag `vX.Y.Z` publishes a signed update bundle for the gateway image: see [docs/RELEASING.md](docs/RELEASING.md) (what a release holds, `app_generation`, key handling, migration rules).

## Developing

```bash
cd Gateway/firmware/api && ../../../.venv/bin/python -m pytest -q   # runs the api against the real hub on an in-memory broker
```

### The hub

`scripts/test_converter.sh` tests the Zigbee2MQTT converter (needs a Zigbee2MQTT checkout with `node_modules`, `Z2M_DIR`); `scripts/gen_converter.py` regenerates its data from `PlantModule/interface.yaml`.

`scripts/z2m_sim.py` plays Zigbee2MQTT and PlantModules on the broker (`--pending 1` makes a module join when the join window is opened).

```bash
cd Gateway/firmware/hub
../../../.venv/bin/python -m pytest -q          # tests run on an in-memory broker, no Mosquitto needed
MC_DATA_DIR=./data MC_MQTT_HOST=127.0.0.1 MC_MQTT_PORT=1884 PYTHONPATH=src ../../../.venv/bin/python -m mc_hub.cli run
```
