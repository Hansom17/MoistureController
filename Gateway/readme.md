# Gateway

The box at home that runs the whole system: Zigbee coordinator with Zigbee2MQTT, Mosquitto, and two services that talk only over MQTT: `hub` (devices, command queue, rules, alerts, Telegram) and `api` (login, REST + SSE, hosting of the Flutter web build; can run on another device). Design: [`specs.md`](specs.md).

**State:** specification, plus `hub` slices 1 and 2 in `firmware/hub` (see `specs.md` §18); the `api` service is not written yet. The target layout is in `specs.md` §15.3 (`firmware/hub`, `firmware/api`, compose files, `mqtt-contract.yaml`, `scripts/`, `hardware/`). The previous gateway and server implementation is in git history at commit `eb97b07`; `specs.md` §19 lists what to take from it.

## Planned run

```bash
docker compose up -d      # zigbee2mqtt, mosquitto, hub, api
```

The first start prints a one-time setup code in the `api` log; open `http://<gateway>/` and create the owner account.

## Developing the hub

```bash
cd Gateway/firmware/hub
../../../.venv/bin/python -m pytest -q          # tests run on an in-memory broker, no Mosquitto needed
MC_DATA_DIR=./data MC_MQTT_HOST=127.0.0.1 MC_MQTT_PORT=1884 PYTHONPATH=src ../../../.venv/bin/python -m mc_hub.cli run
```
