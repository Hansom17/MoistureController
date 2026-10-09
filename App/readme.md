# MoistureController app

Flutter client (Android, iOS, web). Spec and design system: [specs.md](specs.md).

## Run

```bash
flutter run -t lib/main_dev.dart          # device/simulator
flutter run -d chrome -t lib/main_dev.dart
flutter run -t lib/main_local.dart --dart-define=API_URL=http://<host>:8000 --dart-define=DEV_UID=<uid>   # real API on the LAN
flutter test
```

`main_dev.dart` uses `FakeMoistureRepository` — an in-memory backend with two households, sample plants, devices and alerts. Watering goes queued → delivered → running → done over a few seconds with live events, like a sleeping device. Settings → Demo switches your role per household to try the role-aware UI.

`main_local.dart` talks to a real API (`ApiMoistureRepository`, hand-written Dio) with dev tokens and finds the server through mDNS: start the stack (`docker compose -f Server/docker-compose.yml --env-file Server/.env.dev up`, bound to `0.0.0.0` in `.env.dev`) and `python Server/scripts/advertise_mdns.py` on the host. `API_URL` is only the first address to try; the Settings → Server screen switches servers.

## Theme

Colours come from `design/material-theme.json` (Material Theme Builder export). After re-exporting:

```bash
dart run tool/gen_color_scheme.dart
```

## Status

Done: theme + design tokens, dashboard, household switcher, plant detail (chart, water now, commands, rules), devices, device detail, alerts, settings (theme, language), role-aware UI, live-update wiring, DE/EN, gateway screen, BLE pairing wizard with label scanner, API discovery on the LAN with connection banner and Server screen, API repository. Tests cover discovery, the repository, pairing, permissions and the gateway screen.

Not yet: generated API client (needs the OpenAPI file, which is not committed) and `main_prod.dart`, Firebase login/push, slot editor, sensor calibration wizard, members/invites, export, Widgetbook catalog.
