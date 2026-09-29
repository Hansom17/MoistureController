# MoistureController app

Flutter client (Android, iOS, web). Spec: [App_Specs.md](App_Specs.md), design: [Design_System.md](Design_System.md).

## Run

```bash
flutter run -t lib/main_dev.dart          # device/simulator
flutter run -d chrome -t lib/main_dev.dart
flutter test
```

`main_dev.dart` uses `FakeMoistureRepository` — an in-memory backend with two households, sample plants, devices and alerts. Watering goes queued → delivered → running → done over a few seconds with live events, like a sleeping device. Settings → Demo switches your role per household to try the role-aware UI.

## Theme

Colours come from `design/material-theme.json` (Material Theme Builder export). After re-exporting:

```bash
dart run tool/gen_color_scheme.dart
```

## Status

Done: theme + design tokens, dashboard, household switcher, plant detail (chart, water now, commands, rules), devices, device detail, alerts, settings (theme, language), role-aware UI, live-update wiring, DE/EN.

Not yet: generated API client (needs `contracts/api.yaml` from the API server) and `main_prod.dart`, Firebase login/push, BLE pairing, slot editor, members/invites, export, Widgetbook catalog. The hub screen becomes the gateway screen (App_Specs §12, PROJECT D33).
