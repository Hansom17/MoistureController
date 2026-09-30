# Firmware

ESP32 plant controller on Zephyr (DOIT ESP32 DevKit V1). Design: [`Firmware_Specs.md`](Firmware_Specs.md);
wire protocol: [`../contracts/mqtt.md`](../contracts/mqtt.md).

```
src/core/   hardware independent: config + pin rules, commands, payloads, retained state,
            the wake cycle. Unit-tested on QEMU; mirrors core/ (Python) and the contract.
src/hal/    ESP32 / Zephyr: ADC, pump GPIO with RTC hold, settings, retained RAM, deep sleep,
            WiFi, SNTP, MQTT over TLS-PSK. Implements `struct mc_io`.
src/main.c  boot → one cycle → sleep.
tests/core/ ztest suites; scripts/test.py builds and runs them.
```

## Tests (no hardware needed)

```bash
firmware/scripts/test.py
```

Builds `tests/core` for `qemu_x86` and runs it. ~70 tests, among them the whole wake cycle against a fake
broker and fake hardware (publish order, buffering, deep-sleep pump holds, config and command handling).
It also takes every message the firmware produced and validates it with the Python contract models
(`mc_core`) that the gateway and API use, and parses the JSON examples straight out of
`contracts/mqtt.md`.

Needs the Zephyr workspace (`~/zephyrproject`) and SDK (`~/zephyr-sdk-*`); override with `ZEPHYR_BASE`,
`ZEPHYR_SDK_INSTALL_DIR`, `MC_ZEPHYR_VENV`.

## Build

Compile check (runs anywhere, WiFi and BT switched off, **not runnable**):

```bash
firmware/scripts/build-check.sh
```

The real build needs Espressif's radio libraries (closed source, all chips, fetched from GitHub):

```bash
cd ~/zephyrproject && west blobs fetch hal_espressif      # once
cp firmware/dev.conf.example firmware/dev.conf            # fill in WiFi, gateway, device id, key
firmware/scripts/build-check.sh --wifi -DEXTRA_CONF_FILE=$PWD/firmware/dev.conf
west flash -d /tmp/mc-fw-tests/app-wifi
```

## Status

Written and unit-tested, **never run on a board**. The full image with WiFi builds and links (2026-09-30: 655 KB
flash = 16 %, main RAM 66 %, 0 warnings; BLE will add to that). `src/hal/` is unverified on hardware: it is the
part to bring up first.

| Area | State |
|---|---|
| Config: parse, validate (pins, limits), persist | done, tested |
| Moisture sensor (ADC, calibration), pump with safety limits | done; ADC/GPIO code untested on hardware |
| Commands: expiry, duplicates, cancel, long runs through deep sleep | done, tested |
| Telemetry buffer (6 cycles), pending acks, events | done, tested |
| WiFi, SNTP, MQTT over TLS-PSK, persistent session, Last Will | written, compiles, untested |
| Deep sleep, timer wake, retained RAM, BOOT button → service mode | written, compiles, untested |
| DS18B20, SHT3x, float switch drivers; I2C / 1-Wire auto-detect | not started (sensors report `not_found`) |
| BLE pairing, factory PoP partition, factory reset by button | not started (`MC_DEV_PROVISION` until then) |
| OTA updates | not started |

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
   - BOOT button held during sleep wakes the board into service mode.
   - Battery voltage: calibrate `MC_BATT_DIVIDER_PERCENT` against a multimeter.
6. Measure the current of a full cycle (WiFi connect + MQTT dominate) and set the default interval.
