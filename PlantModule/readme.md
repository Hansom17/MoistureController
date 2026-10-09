# PlantModule

Battery-powered ESP32 plant device. `firmware/` Zephyr firmware · `hardware/` KiCad carrier board · `scripts/` labels, BLE provisioning, firmware tests. Design: [`specs.md`](specs.md).

## Firmware

ESP32 plant controller on Zephyr (DOIT ESP32 DevKit V1). Wire protocol: [`../Gateway/specs.md`](../Gateway/specs.md) Part C.

```
firmware/src/core/   hardware independent: config + pin rules, commands, payloads, retained state,
            the wake cycle. Unit-tested on QEMU; mirrors Shared/core (Python) and the contract.
src/hal/    ESP32 / Zephyr: ADC, pump GPIO with RTC hold, settings, retained RAM, deep sleep,
            WiFi, SNTP, MQTT over TLS-PSK, BLE, `hal_button.c` (BOOT button monitor while awake).
            Implements `struct mc_io`.
src/main.c  boot → cycle → sleep (with `wake_interval_s = 0` it loops cycles and never sleeps).
tests/core/ ztest suites; scripts/test.py builds and runs them.
```

## Tests (no hardware needed)

```bash
PlantModule/scripts/test.py
```

Builds `tests/core` for `qemu_x86` and runs it. About 95 test cases (`ZTEST` count, not re-run for this edit), among them the whole wake cycle against a fake
broker and fake hardware (publish order, buffering, deep-sleep pump holds, config and command handling).
It also takes every message the firmware produced and validates it with the Python contract models
(`mc_core`) that the gateway and API use, and parses the JSON examples straight out of
the MQTT interface in `Gateway/specs.md`.

Needs the Zephyr workspace (`~/zephyrproject`) and SDK (`~/zephyr-sdk-*`); override with `ZEPHYR_BASE`,
`ZEPHYR_SDK_INSTALL_DIR`, `MC_ZEPHYR_VENV`.

## Build

Compile check (runs anywhere, WiFi and BT switched off, **not runnable**):

```bash
PlantModule/scripts/build-check.sh
```

The real build needs Espressif's radio libraries (closed source, all chips, fetched from GitHub):

```bash
cd ~/zephyrproject && west blobs fetch hal_espressif      # once
cp PlantModule/firmware/dev.conf.example PlantModule/firmware/dev.conf            # fill in WiFi, gateway, device id, key
PlantModule/scripts/build-check.sh --wifi -DEXTRA_CONF_FILE=$PWD/PlantModule/firmware/dev.conf
west flash -d /tmp/mc-fw-tests/app-wifi
```

## Status

Written and unit-tested; the network path is **verified on a board** (2026-10-02: WiFi join, DHCP, TLS-PSK MQTT
connect, a wake cycle published, deep sleep entered; the API shows the device `sleeping`). The full image with WiFi
and BLE builds and links; static data RAM was at 98 % at the last measurement (before the button monitor thread and the config changes; re-measure with `build-check.sh --wifi`), so there is little room left. The rest of `src/hal/` (ADC, pump
GPIO, timer wake) is still unverified on hardware.

Bring-up notes: the bench signal is marginal (about -70 dBm), so the WiFi join retries 3 times. mbedTLS has its own
heap (`MBEDTLS_HEAP_SIZE`); without it the TLS context failed with `-ENOMEM`.

| Area | State |
|---|---|
| Config: parse, validate (pins, limits), persist | done, tested |
| Moisture sensor (ADC, calibration), pump with safety limits | done; ADC/GPIO code untested on hardware |
| Commands: expiry, duplicates, cancel, long runs through deep sleep | done, tested |
| Telemetry buffer (6 cycles), pending acks, events | done, tested |
| WiFi, MQTT over TLS-PSK, persistent session | done; **verified on a board** (join, TLS-PSK connect, telemetry reaches the API) |
| SNTP, Last Will, retained commands/acks round trip | written, compiles, not yet checked on a board |
| Deep sleep | entered on a board; timer wake and retained RAM not yet checked. A BOOT-button wake stays awake at least `max(120 s, awake_s)` (service mode); not yet checked on a board |
| Wake interval 0 (factory default: never sleep), `awake_s` | done, tested; config blobs of earlier firmware are upgraded (settings v1 → v2) |
| `sensor.sample` (calibration capture), `|dry − wet| ≥ 300` rule | planned, not started |
| ESP32-C6 carrier board (`hardware/carrier`) | no board overlay yet |
| DS18B20, SHT3x, float switch drivers; I2C / 1-Wire auto-detect | not started (sensors report `not_found`) |
| BLE pairing: secure session, all messages, commit, factory page with the PoP | done; protocol byte-identical to the Python reference (tests), **verified on a board** (pairing, persistence, restart) |
| BLE: 3 s / 10 s BOOT button (maintenance window, factory reset), 5-failure lockout, WiFi `test` step | written, **not yet tried on a board** |
| OTA updates | not started |

## Pairing over Bluetooth (PlantModule/specs.md Part B)

Once per device, at the factory bench. `make_label.py` keeps every device in one CSV
(`PlantModule/scripts/factory/devices.csv`: BLE name, Bluetooth MAC, PoP, label text; **git-ignored, it holds the secret
PoPs**) and draws the QR code of the label (`PlantModule/scripts/factory/labels/MC-XXXX.png`):

```bash
PlantModule/scripts/make_label.py new   --port /dev/cu.usbserial-0001   # PoP, CSV row, QR image, page
PlantModule/scripts/make_label.py flash --port /dev/cu.usbserial-0001   # write that device's page to the board
PlantModule/scripts/make_label.py new --port … --flash                  # both in one go
PlantModule/scripts/make_label.py list                                  # what was made, what was flashed
PlantModule/scripts/make_label.py qr MC-XXXX                            # redraw a label's QR code
PlantModule/scripts/make_label.py new --name MC-XXXX --mac AA:BB:… --pop <hex>   # record an already assigned device
```

The flash step asks the board for its Bluetooth MAC and looks the PoP up in the CSV, so re-flashing or
replacing a board never loses its label. QR images come from the `segno` package if installed, otherwise on
macOS from `tools/qr_png.swift` (no packages). Print the PNG on the label.

Flash the firmware **without** `MC_DEV_PROVISION`: an unpaired device opens the pairing window on every
boot (10 min, LED blinks slowly) and advertises as `MC-XXXX`. Then, from a machine with Bluetooth (on macOS
from your own Terminal app: other apps are killed by the system without a Bluetooth permission):

```bash
.venv/bin/python PlantModule/scripts/ble_provision.py --label "MCPOP1:MC-26EA:…" --bundle bundle.json \
    --ssid "<wifi>" --host <gateway LAN address>     # add --skip-test to commit without joining the WiFi
.venv/bin/python PlantModule/scripts/ble_provision.py --label "…" --scan    # WiFi networks the device sees
```

`bundle.json` is the API's reply when adding a device. The same flow is what the app's wizard does
(`App/lib/features/pairing/`, in Dart; `Shared/core/src/mc_core/ble_client.py` is the Python reference). Both are
checked against `firmware/tests/ble_vectors.json`, like the firmware.

Bench tips learned on the first board: on a weak USB port or cable the supply dips when WiFi transmits and the
USB serial chip drops off the bus; `CONFIG_MC_LOW_TX_POWER=y` (Bluetooth -9 dBm, WiFi 8 dBm) avoids it.
An iPhone hotspot is only visible to the board while its Personal Hotspot screen is open (and needs
"Maximize Compatibility": the ESP32 is 2.4 GHz only).

## First bring-up on a board

1. `west blobs fetch hal_espressif`, build with `--wifi`, flash, watch the console (115200).
2. Console shows `firmware 0.1.0, wake: power_on` and `provisioning from the build`.
3. WiFi joins, TLS-PSK handshake with the gateway's broker (`mc-gateway` / Mosquitto log: client `mc-…`).
4. App shows the device online and a moisture reading within the first cycle.
5. Check, in this order, because the unit tests cannot:
   - ADC: readings move when the sensor goes from air to water; `raw` within 0–4095.
   - Deep sleep: after the cycle the board sleeps, wakes by timer at `next_wake_s`, `boot` counts up,
     `seq` continues (retained RAM survives), clock continues without SNTP.
   - Pump relay: a 5 s `pump.run` switches the right pin the right way (`active_high`); the pin is
     **off** after boot and after a reset.
   - Long run (> 15 s) on an RTC pin (25, 26, 27, 32, 33, 4, 12-15): the pump stays on through sleep
     and is switched off by the wake at its end. Verify with a multimeter, not the log.
   - BOOT button pressed during sleep wakes the board and keeps it awake for at least `max(120 s, awake_s)`; holding it 3 s / 10 s while awake gives the fast-blink cue / factory reset (`hal_button.c`).
   - Battery voltage (`MC_BATT_ADC_PIN`, off by default): wire a divider, set the pin and calibrate
     `MC_BATT_DIVIDER_PERCENT` against a multimeter.
6. Measure the current of a full cycle (WiFi connect + MQTT dominate) and set the default interval.
