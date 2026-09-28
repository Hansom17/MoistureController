# Client App — Design System

**Status:** draft · **Last change:** 2026-09-28

Defines the UI component library, the component catalog and the colour palette of the Flutter app. General design rules (Material 3, responsive breakpoints, accessibility, localization) are in [App_Specs §9](App_Specs.md#9-design); this document makes them concrete.

---

## 1. Component library and catalog

| Concern | Choice | React equivalent | Notes |
|---|---|---|---|
| Base components | **Material 3** (`package:flutter/material.dart`, `useMaterial3: true`) | MUI | Ships with Flutter, native feel on Android, good accessibility defaults, light/dark from one `ColorScheme`. |
| Own components | **`lib/ui/`** — thin layer of app-specific widgets built on Material | shadcn/ui (own copies of components) | Screens use these instead of styling Material widgets ad hoc (§4). |
| Component catalog | **[Widgetbook](https://pub.dev/packages/widgetbook)** (`widgetbook`, `widgetbook_annotation`, `widgetbook_generator`) | Storybook | Separate Flutter app in `app/widgetbook/`; every `lib/ui/` component has use cases for light/dark, DE/EN, text scale 100 %/200 % and phone/tablet. Built for web in CI and deployable as an internal preview. |
| Golden tests | `alchemist` | Chromatic / visual regression | Golden images for `lib/ui/` components in both themes; run in CI. |

Rejected: `shadcn_ui` / `forui` (Flutter ports of the shadcn look) — nice on web, but non-native on Android/iOS and a second styling system next to Material; revisit only if the app gets a web-first redesign.

---

## 2. Colour palette

All colours live in code in `lib/app/theme/` — **no hex values in feature code**. Material roles come from `Theme.of(context).colorScheme`, app-specific colours from `ThemeExtension`s (§2.3, §2.4).

### 2.1 Material colour scheme — from Material Theme Builder

**Source of truth:** [`design/material-theme.json`](design/material-theme.json), exported from [Material Theme Builder](https://material-foundation.github.io/material-theme-builder/) (seed `#2D391C`, "Moss"). To change the palette, re-export from the builder and overwrite that file — never edit single roles by hand.

The app uses the **exported schemes as-is**, not `ColorScheme.fromSeed(...)`: `fromSeed` with the same seed produces slightly different values than the builder's custom export. `lib/app/theme/color_scheme.dart` is the builder's Dart export (or generated from the JSON) and contains six `ColorScheme`s:

| Scheme | Selected when |
|---|---|
| `light` / `dark` | Default, following the system brightness (or the user's choice in account settings) |
| `light-medium-contrast` / `dark-medium-contrast` | Not used in v1 |
| `light-high-contrast` / `dark-high-contrast` | `MediaQuery.highContrastOf(context)` is true (iOS "Increase contrast", Android high-contrast text) → `MaterialApp.highContrastTheme` / `highContrastDarkTheme` |

Key roles (from the export, `light` / `dark`):

| Role | Light | Dark | Use |
|---|---|---|---|
| `primary` / `onPrimary` | `#4D662A` / `#FFFFFF` | `#B3D088` / `#213600` | The one accent (App_Specs §9): primary buttons ("Water now"), selection, FAB |
| `primaryContainer` | `#CFEDA2` | `#364E14` | Selected plant card, active tab indicator |
| `secondary` / `secondaryContainer` | `#586249` / `#DCE7C7` | `#C0CBAC` / `#414A33` | Filter chips, tonal buttons |
| `tertiary` / `tertiaryContainer` | `#386662` / `#BCECE6` | `#A0D0CA` / `#1F4E4A` | Secondary chart series, info accents |
| `error` / `errorContainer` | `#BA1A1A` / `#FFDAD6` | `#FFB4AB` / `#93000A` | Errors, offline, destructive actions |
| `surface` | `#F9FAEF` | `#12140E` | Page background |
| `surfaceContainerLow` | `#F4F4E9` | `#1A1C16` | Cards (plant cards, device rows) |
| `surfaceContainerHigh` | `#E8E9DE` | `#282B24` | Dialogs, bottom sheets, nav bar |
| `onSurface` / `onSurfaceVariant` | `#1A1C16` / `#44483D` | `#E2E3D8` / `#C5C8B9` | Text / secondary text |
| `outline` / `outlineVariant` | `#75796C` / `#C5C8B9` | `#8F9285` / `#44483D` | Borders, dividers, chart thresholds |

Android 12+ dynamic colour (wallpaper-based) is **off** — the app keeps its own identity and the colours below are tuned against these surfaces.

### 2.2 Extended colours

The theme builder export has no `extendedColors`; the moisture scale and the status colours are defined in code as `ThemeExtension`s (§2.3, §2.4), because they need hand-tuned contrast and a colour-blind-safe order that the builder's automatic harmonisation would change. In high-contrast mode they use the same values (they already meet the contrast rules below).

### 2.3 Moisture scale — `MoistureColors` extension

Sequential dry → wet scale (sand → leaf → teal → water), colour-blind safe (no red/green pair, hue plus lightness change). Values between stops are interpolated linearly in `MoistureColors.of(percent)`.

| Stop | Moisture | Light | Dark | Name |
|---|---|---|---|---|
| 0 | 0 % | `#A06C0A` | `#F0C45C` | Sand |
| 1 | 25 % | `#5E8A2C` | `#B5D67A` | Leaf |
| 2 | 50 % | `#1F7F73` | `#5CC8B8` | Teal |
| 3 | 75 % | `#246FA8` | `#6FB4EC` | Water |
| 4 | 100 % | `#243F8F` | `#A3B2F7` | Deep water |

Rules:

- **Never colour alone** (App_Specs §9): the percentage is always shown next to any moisture colour, as text in `onSurface` — the moisture colour is used for fills (gauge, bar, chart line, dot), never for text.
- Every stop has ≥ 3 : 1 contrast (WCAG 1.4.11, graphical objects) against `surface`, `surfaceContainerLow` and `surfaceContainerHigh` of its theme.
- The scale is absolute (0–100 %), not relative to a plant's rule thresholds; thresholds are drawn as lines on the chart instead.

### 2.4 Status colours — `StatusColors` extension

Every status is shown as **icon + label + colour** (chip), never colour alone.

| Status | Light | Dark | Icon | Used for |
|---|---|---|---|---|
| `ok` | `#27692B` | `#81C784` | `check_circle` | Device online, command done, hub in sync |
| `sleeping` | `#505D6B` | `#AAB6C2` | `bedtime` | Device sleeping as expected (normal state, deliberately calm) |
| `pending` | `#0F5AAE` | `#9CC3F5` | `schedule` | Queued / delivered / running commands, config pending |
| `warning` | `#8A5100` | `#FFB95C` | `warning` | Device late, low battery, hub offline banner |
| `error` | = `colorScheme.error` | = `colorScheme.error` | `error` | Device offline, command failed / expired, config rejected |

Chip background: the status colour at 12 % opacity (light) / 16 % (dark) over the card surface; label and icon in the full status colour. Label text has ≥ 4.5 : 1 contrast against that tinted chip background on `surface` and `surfaceContainerLow`. On `surfaceContainerHigh` (dialogs, sheets) `warning` and `error` drop just below that, so chips there use the untinted surface (no 12 % background).

### 2.5 Charts

- Moisture line: `MoistureColors` gradient along the value axis; min/max band at 20 % opacity.
- Other series (temperature, battery, RSSI): `primary`, `tertiary`, `secondary` in that order.
- Rule thresholds: dashed `outline` line with a label. Watering events: `pending` colour markers.

---

## 3. Other tokens

| Token | Values |
|---|---|
| Spacing | 4, 8, 12, 16, 24, 32 (`Spacing.xs … xxl`) |
| Radius | 8 (chips, inputs), 12 (cards), 28 (dialogs, bottom sheets — M3 default) |
| Typography | Material 3 type scale, default platform font (Roboto / SF). Numbers (moisture, battery, times) use tabular figures (`FontFeature.tabularFigures()`). |
| Elevation | M3 tonal elevation only; no custom shadows |
| Icons | Material Symbols (rounded) |

---

## 4. `lib/ui/` components (initial set)

| Component | Content |
|---|---|
| `MoistureGauge` | Ring or bar with `MoistureColors` fill + big percentage; sizes S/M/L |
| `StatusChip` | One of the §2.4 statuses + optional detail ("last seen 2 h ago") |
| `PlantCard` | Dashboard card: name, `MoistureGauge`, trend arrow, reading age, battery, `StatusChip`, pending-command badge |
| `CommandStateTile` | Queued / delivered / running / done / failed / expired / cancelled with times (App_Specs §7) |
| `HouseholdBanner` | Hub-offline / offline-data banner (`warning`) |
| `RoleGate` | Hides or disables its child based on `can(action)` with tooltip (App_Specs §8) |
| `EmptyState`, `ErrorState` | Illustration-free icon + text + action |

Code layout additions:

```
app/
├── lib/
│   ├── app/theme/           # color_scheme.dart (from design/material-theme.json), moisture_colors.dart, status_colors.dart, tokens.dart
│   └── ui/                  # components above, no feature logic, no providers
├── design/material-theme.json  # Material Theme Builder export (palette source of truth)
└── widgetbook/              # catalog app (Widgetbook), imports lib/ui/
```
