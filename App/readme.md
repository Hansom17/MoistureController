# MoistureController app

Flutter app, served as a **web app by the gateway** (`Gateway/`); Android and iOS later from the same code. Spec and design system: [specs.md](specs.md).

## Run

```bash
cd App
flutter run -d chrome -t lib/main_dev.dart                       # fake backend, no gateway needed
flutter test                                                      # unit and widget tests (fake backend, mocked HTTP)

flutter build web --release --no-web-resources-cdn                # the product: App/build/web, served by the gateway's api
flutter run -d chrome --dart-define=API_URL=http://localhost:8000 # against a running api, for development
```

- `lib/main_dev.dart` uses `FakeMoistureRepository`: sample plants, devices, alerts and users in memory. Sign in as `demo` / `demo` (owner), `anna` / `anna` (member) or `ben` / `ben` (viewer); setup code `DEMOCODE`, invite code `DEMOINVITE`. Watering goes queued → running → done over a few seconds with live events; a join window brings a new device in. Settings → Demo switches your role.
- `lib/main.dart` talks to the gateway's `api` (`ApiMoistureRepository`, hand-written Dio, SSE for live updates). On web it uses the page's own origin.
- The web build is self-contained: CanvasKit and Roboto come from the gateway, nothing from a CDN. Texts may only use characters Roboto has (`test/l10n_test.dart` guards this).
- To try the whole stack on one machine: `Gateway/firmware/` (compose) or the processes described in `Gateway/readme.md`, with `scripts/z2m_sim.py` as the Zigbee side; set `MC_WEB_DIR` to `App/build/web`.

## Theme

Colours come from `design/material-theme.json` (Material Theme Builder export). After re-exporting:

```bash
dart run tool/gen_color_scheme.dart
```

## Status

Adapted to the gateway `api`: setup, login, invite join, dashboard with plant create/edit, plant detail (chart over the whole range, water now, command history, rules with quiet hours / daily limit / notifications and "why did it water"), devices, add device (Zigbee join window with steps), device detail (diagnostics, events, safe mode, rename, remove with password), slot editor (modules, ports from the board description, report intervals), alerts, users and invites, my devices (tokens, password), installation settings (name, timezone, battery, Telegram), gateway status, backup and export, live updates, role-aware UI, DE/EN. 97 tests; the full flow was also run in a browser against the real api, hub and simulator.

Not done: the calibration wizard, QR code for invites (the link can be copied), browser push, the mobile flavor (secure token storage, mDNS discovery is kept but not wired in), golden tests.
