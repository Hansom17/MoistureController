# Gateway

The box at home that runs the whole system: Zigbee coordinator with Zigbee2MQTT, Mosquitto, and two services that talk only over MQTT: `hub` (devices, command queue, rules, alerts, Telegram) and `api` (login, REST + SSE, hosting of the Flutter web build; can run on another device). Design: [`specs.md`](specs.md).

**State:** specification, plus the `hub` (`firmware/hub`) and the `api` (`firmware/api`) services (see `specs.md` §18); Dockerfiles and compose files are in `firmware/`. The target layout is in `specs.md` §15.3 (`firmware/hub`, `firmware/api`, compose files, `mqtt-contract.yaml`, `scripts/`, `hardware/`). The previous gateway and server implementation is in git history at commit `eb97b07`; `specs.md` §19 lists what to take from it.

## Run (not tried on a real box yet)

```bash
cd Gateway/firmware
../scripts/setup.sh          # .env with generated MQTT passwords, Mosquitto password file
# edit .env: ZIGBEE_DEVICE (ls /dev/serial/by-id/), WEB_DIR (flutter build web in App/)
docker compose up -d         # mosquitto, zigbee2mqtt, hub, api
docker compose logs api | grep 'SETUP CODE'
```

Open `http://<gateway>/` and create the owner account with that setup code. More: `../scripts/remote-api.sh` (api on another device), `../scripts/backup.sh`; details in `specs.md` §15.

## Developing

```bash
cd Gateway/firmware/api && ../../../.venv/bin/python -m pytest -q   # runs the api against the real hub on an in-memory broker
```

### The hub

`scripts/z2m_sim.py` plays Zigbee2MQTT and PlantModules on the broker (`--pending 1` makes a module join when the join window is opened).

```bash
cd Gateway/firmware/hub
../../../.venv/bin/python -m pytest -q          # tests run on an in-memory broker, no Mosquitto needed
MC_DATA_DIR=./data MC_MQTT_HOST=127.0.0.1 MC_MQTT_PORT=1884 PYTHONPATH=src ../../../.venv/bin/python -m mc_hub.cli run
```
