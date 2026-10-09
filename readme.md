# MoistureController

Monitor the soil moisture of plants with small battery-powered Zigbee devices, see it in a web app, and water manually or by rule. Everything runs locally on one box at home, at no cost.

| Folder | What it is |
|---|---|
| [`PlantModule/`](PlantModule/) | The plant device: ESP32-C6 Zigbee end device (firmware to be written) and its KiCad carrier board |
| [`Gateway/`](Gateway/) | The box at home: Zigbee coordinator, Zigbee2MQTT, Mosquitto and the hub service with the API and the web app hosting (to be written) |
| [`App/`](App/) | Flutter app: the web UI served by the Gateway, later also a mobile app |

Each folder has a `specs.md` (design) and a `readme.md`. The system design, flows and decisions are in [`PROJECT.md`](PROJECT.md).

## State

Only the specifications, the carrier board and the Flutter app exist. The hub, the Zigbee firmware and the Zigbee2MQTT converter are still to be written; the plan and order of work are in `PROJECT.md` §9. The previous WiFi/MQTT implementation is in git history at commit `eb97b07`.

## What runs today

```bash
cd App && flutter run -d chrome -t lib/main_dev.dart   # the app with in-memory demo data
cd App && flutter test
```
