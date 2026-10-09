# MoistureController app

Flutter client (Android, iOS, web). Spec and design system: [specs.md](specs.md).

## Run

```bash
flutter run -t lib/main_dev.dart          # device/simulator
flutter run -d chrome -t lib/main_dev.dart
flutter run -t lib/main_local.dart --dart-define=API_URL=http://<host>:8000 --dart-define=DEV_UID=<uid>   # real API (the hub, once it exists)
flutter test
```

`main_dev.dart` uses `FakeMoistureRepository` — an in-memory backend with two households, sample plants, devices and alerts. Watering goes queued → delivered → running → done over a few seconds with live events, like a sleeping device. Settings → Demo switches your role per household to try the role-aware UI.

`main_local.dart` talks to a real API (`ApiMoistureRepository`, hand-written Dio) with dev tokens and can find the server through mDNS. It was written against the previous API; there is no server to run it against until the hub exists, and it has to be adapted to the hub API (see `specs.md` §14).

## Theme

Colours come from `design/material-theme.json` (Material Theme Builder export). After re-exporting:

```bash
dart run tool/gen_color_scheme.dart
```

## Status

Done: theme + design tokens, dashboard, household switcher, plant detail (chart, water now, commands, rules), devices, device detail, alerts, settings (theme, language), role-aware UI, live-update wiring, DE/EN, gateway screen, API discovery on the LAN with connection banner and Server screen, API repository. Tests cover discovery, the repository, permissions and the gateway screen.

Removed with the redesign: the BLE pairing wizard and its dependencies. Still to do for the hub design (see `specs.md`): hub login (setup, login, join, tokens), the Zigbee join screen, users and invites, adapting the API repository to the hub API, calibration wizard, export.
