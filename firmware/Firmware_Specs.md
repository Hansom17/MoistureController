# MoistureController — Project Plan

## Goal

A battery-powered ESP32 (DOIT ESP32 DevKit V1) controller that:
- Talks to a variable set of plug-in modules (moisture sensors, other sensors, a water pump) whose type-per-pin is configurable, not hardcoded per build.
- Publishes sensor readings and accepts commands (e.g. "run pump for N seconds") over MQTT via WiFi.
- Spends most of its life in deep sleep to survive on battery.

## Hardware constraints (DOIT ESP32 DevKit V1)

| Pins | Notes |
|---|---|
| GPIO0 | BOOT button, strapping pin — avoid for module I/O |
| GPIO2 | Onboard LED (used for status blink) — avoid for module I/O |
| GPIO1 / GPIO3 | UART0 TX/RX (console) — reserved |
| GPIO6–11 | Connected to internal SPI flash — reserved, do not expose |
| GPIO34, 35, 36, 39 | Input-only, no pull resistor, **ADC1 only** — fine for analog sensors, unusable for outputs (e.g. pump relay) |
| GPIO32, 33 | ADC1, usable as input or output |
| GPIO4, 12–15, 25–27 | **ADC2** channels |
| GPIO12 (MTDI), GPIO15 (MTDO) | Strapping pins — avoid driving high externally at boot; GPIO15 low at boot suppresses the ROM boot log |

**Critical constraint: ADC2 and WiFi conflict.** On the ESP32, ADC2 cannot be read reliably while the WiFi radio is active (Espressif hardware/driver limitation — the earlier D15 moisture demo uses ADC2 channel 3). This project needs WiFi, so:
- The wake cycle **must read all ADC2-backed sensors before enabling WiFi**, every cycle.
- New analog sensor slots should prefer **ADC1 pins (32, 33, 34, 35, 36, 39)** where possible, so they aren't subject to this ordering constraint at all.

## Module system (pluggable sensors/pump, runtime-configurable)

### Why not plain devicetree

Zephyr's normal pattern (device tree + `*_DT_SPEC_GET()` macros used for the LED/moisture demo so far) binds a peripheral to a fixed pin at **compile time**. That's wrong for this project: the requirement is to change which physical pin drives which module without reflashing.

### Design: module slots + runtime peripheral binding

- Devicetree still enables the underlying peripherals generically (all usable GPIOs, both ADC units, I2C, 1-Wire timer, etc.) — it just doesn't fix *what* is attached to *which* pin.
- At runtime, the app calls the **non-DT** Zephyr driver APIs (`gpio_pin_configure()`, `adc_channel_setup()` with a runtime-built `struct adc_channel_cfg`, etc.), parameterized by pin/channel numbers read from persisted settings. This is the standard escape hatch Zephyr provides for exactly this "software-defined pinout" case.
- A **module slot table** (fixed-size array, e.g. 6 slots) holds, per slot: `{ pin_or_channel, bus_type, module_type, calibration }`. This table is the single source of truth for "what's connected where."
- Each supported module type implements a small internal driver interface:
  ```c
  struct module_driver {
      const char *name;
      enum bus_type bus;                 /* GPIO_OUT, GPIO_IN, ADC, I2C, ONEWIRE */
      int (*probe)(struct module_slot *slot);   /* confidence check, not identity */
      int (*init)(struct module_slot *slot);
      int (*read)(struct module_slot *slot, struct module_reading *out);   /* sensors */
      int (*write)(struct module_slot *slot, const struct module_cmd *cmd); /* actuators, e.g. pump */
  };
  ```
- Drivers to implement, roughly in priority order: capacitive/resistive analog moisture sensor, GPIO relay/pump, then whatever else comes up (temperature/humidity, water level, etc.) — each is a small, independent file registering into a static driver table.

### Auto-detect: what's actually possible

Auto-detect capability depends entirely on the bus, not on wanting it to exist:

| Bus | Auto-detect feasible? | How |
|---|---|---|
| I2C | Yes, reliably | Scan bus addresses; match against known device ID registers per driver |
| 1-Wire (e.g. DS18B20 temp probe) | Yes, reliably | ROM search / family code on the bus |
| Analog (moisture sensors) | Presence only, not type | A floating ADC pin reads noisy/mid-rail garbage; a connected sensor reads a stable value in its expected range. This can confirm "something is plugged in here" but **cannot tell which analog sensor type it is** — two different moisture sensor models can produce overlapping voltage ranges. Type must be set explicitly for analog slots. |
| Plain GPIO output (pump/relay) | No | An output has nothing to sense; there is no signal to detect. Must always be configured manually. |

**Conclusion:** auto-detect is a real feature for I2C/1-Wire slots, and a "confirm something is there" nicety for analog slots, but manual configuration is unavoidable for actuators and for disambiguating analog sensor type. The config system needs to support both paths, not just one.

### Configuration path

- Module slot table lives in **Zephyr settings** (NVS partition) — persists across reboots and sleep cycles.
- Two ways to change it:
  1. **Remote, via MQTT** — the server publishes the full desired config on `config/desired` (with a revision number); the device validates it, applies it atomically, persists it and reports back on `config/state`. See [`contracts/mqtt.md`](../contracts/mqtt.md) §6. This is the normal "on the fly" path once the device is deployed.
  2. **Local maintenance mode** — holding the BOOT button (GPIO0, already wired) for 3 s keeps the device awake and connected (skips the sleep cycle) so it can be reconfigured interactively over USB console or MQTT without racing the sleep timer, **and opens the BLE pairing window for 5 min**. Holding it for 10 s is a factory reset. Needed because during normal operation the wake window is short and easy to miss.

### Provisioning and pairing

WiFi credentials, the gateway address (hub on the LAN or cloud broker), the TLS-PSK key and the cloud-assigned device ID arrive over BLE using the PoP-authenticated, encrypted protocol in [`contracts/ble.md`](../contracts/ble.md). Firmware requirements from it:

- A **factory NVS partition** holding the 16-byte PoP, written at flash time by `tools/make_label.py` (which also prints the QR label) and never erased by factory reset.
- BLE advertising only while unprovisioned or in maintenance mode; closes after 5 failed handshakes.
- X25519, HKDF-SHA256, HMAC-SHA256 and AES-128-GCM via PSA Crypto / Mbed TLS.
- **MQTT over TLS-PSK** ([`contracts/mqtt.md`](../contracts/mqtt.md) §2): Zephyr TLS sockets with `TLS_CREDENTIAL_PSK` + `TLS_CREDENTIAL_PSK_ID`, Mbed TLS with `MBEDTLS_KEY_EXCHANGE_PSK_ENABLED` and the `TLS_PSK_WITH_AES_128_GCM_SHA256` suite only (keeps code size and RAM small). Same code path whether the gateway is a hub or the cloud broker.
- Early check needed: **BLE + WiFi coexistence** on the ESP32 under Zephyr (the `test` step runs WiFi while the BLE connection is up), and flash/RAM budget of the BLE stack.

## Connectivity: WiFi + MQTT

- Zephyr's native WiFi driver (esp32 already supports it, `&wifi` node exists in the board DT) + Zephyr's MQTT client (`zephyr/net/mqtt.h`).
- **Persistent session is required for the sleep model to work**: connect with `clean_session = false` and a stable client ID, subscribe with QoS 1. This tells the broker to **queue commands while the device is offline/asleep** instead of dropping them — the device then receives everything it missed the moment it reconnects. Without this, any command sent while the device is asleep is simply lost.
- Last Will and Testament (LWT) on `status` = `offline`. Before a normal sleep the device publishes `status` = `sleeping` (with `next_wake_s`) and disconnects cleanly, so the LWT only fires when the device really vanished.

### Topic scheme

Moved to **[`contracts/mqtt.md`](../contracts/mqtt.md)**, the single source of truth for topics, payloads, QoS/retain flags, command and config semantics. Summary: prefix `mc/v1/<device-id>/`; device publishes `status` (retained, + LWT), `telemetry` (all readings + health, one message per wake), `event`, `cmd/ack`, `config/state` (retained); device subscribes to `cmd` and `config/desired` (retained, full config with `rev`).

## Power management: the sleep/command question, resolved

**Decision (confirmed with you): battery-powered, minutes-level command latency is acceptable.** That rules out staying WiFi-associated between commands (light-sleep/modem-sleep) as the primary mode — it costs far more average power for a responsiveness requirement we don't have. It also rules out any notion of the broker "waking" the device asynchronously: **nothing can reach a device in ESP32 deep sleep** — the radio and TCP session are gone. The only two working shapes are:

1. Poll on a wake timer (chosen).
2. Stay associated to save wake latency (rejected — costs too much power for no benefit given "minutes is fine").

So: **the command is read during the wake window, not before it — the ESP always wakes on its own schedule and checks, it never wakes because of an incoming command.**

### Wake cycle sequence (every cycle)

1. Wake from deep sleep (RTC timer, e.g. every 5–15 min — tunable, see below).
2. Read all sensor slots, **including ADC2 slots, before touching WiFi** (see ADC2/WiFi constraint above).
3. Bring up WiFi, connect to MQTT broker with `clean_session=false`.
4. Publish `status` = online, then telemetry (buffered cycles first, then the current one).
5. Apply `config/desired` if its `rev` is newer. Drain any commands the broker queued while offline (subscribe already registered from a prior session; broker delivers backlog on reconnect). Process each: actuate pump/module, publish ack.
6. Publish `config/state` if the slot table changed this cycle.
7. Publish `status` = sleeping, disconnect MQTT cleanly, disable WiFi.
8. Go back to deep sleep.

### Pump duration vs. wake window

If a commanded pump run (e.g. "water for 10 minutes") outlasts the time budget of one wake window, the ESP can't just stay awake burning power to babysit a GPIO — but it also loses all peripheral state on deep sleep. The ESP32 solves this specific case with **RTC GPIO hold**: a pump output on an RTC-capable GPIO can be latched (`rtc_gpio_hold_en`-equivalent) so it **stays in its last state through deep sleep**, then the device wakes again after the requested duration (via RTC timer) purely to turn it back off. This needs to be a deliberate exception in the wake-cycle logic — most cycles are pure poll-and-sleep, but an active pump run schedules an early wake for its own shutoff.

### Wake interval — tunable, not fixed

There's no single right number; it's a battery-life vs. responsiveness tradeoff that depends on your battery capacity, which you haven't fixed yet. Suggest starting at **10 minutes**, config it as a normal setting (persisted, changeable via `config/desired` → `wake_interval_s`), and revisit after measuring actual current draw per wake cycle (WiFi connect + MQTT handshake will dominate — likely 1–3 seconds of ~150–250mA versus microamps in deep sleep, so the wake interval is the main lever on battery life, not sleep current).

## Implementation phases

1. **Module abstraction, static config** — slot table, driver interface, port the existing moisture-sensor code into a driver, add a pump/GPIO-output driver. No persistence yet, no networking yet — table is hardcoded, provable on the bench.
2. **Settings persistence** — move the slot table into Zephyr settings/NVS; survive reboot.
3. **I2C/1-Wire auto-detect** — only meaningful once there's at least one such sensor to test against; analog "presence check" can be added here too.
4. **WiFi + MQTT connectivity** — always-on first (no sleep yet), get publish/subscribe/topic scheme working and reliable.
5. **Deep sleep integration** — wake cycle sequence, RTC timer wake, RTC GPIO hold for long pump runs, wake interval as a setting.
6. **Remote config over MQTT** — `config/desired`/`config/state`, plus the BOOT-button "stay awake" service mode.

## Open decisions (yours to make, not architectural)

- Exact wake interval default and whether it should adapt (e.g. shorter during active watering schedules, longer otherwise).
- MQTT broker: self-hosted vs. cloud, TLS or not, auth scheme — affects connect-time power cost and code in phase 4.
- Full list of sensor types beyond moisture (affects how many driver files phase 1 needs, not the architecture itself).
