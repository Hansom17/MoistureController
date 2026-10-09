# PlantModule

Battery-powered plant device: an ESP32-C6 Zigbee end device. Design: [`specs.md`](specs.md).

```
firmware/    src/core/  portable logic from the previous firmware (config + pin rules, commands, payloads,
                        retained state, wake cycle). The Zigbee/ESP-IDF firmware is not built yet.
             tests/core/ ztest suites for src/core
hardware/    KiCad carrier board for the Waveshare ESP32-C6-Zero (Part C of the spec)
scripts/     test.py, check_contract.py, gen_contract_examples.py, qr_png.swift
```

**State:** the Zephyr app layer (WiFi, MQTT, BLE pairing, hardware abstraction, `main.c`) and the BLE pairing code were removed with the redesign; only the hardware-independent core and its tests remain, as the base for the ESP-IDF port. The removed code is in git history (commit `900b08f`).

## Tests

```bash
PlantModule/scripts/test.py
```

Builds `firmware/tests/core` for `qemu_x86` and runs it. Needs the Zephyr workspace (`~/zephyrproject`) and SDK (`~/zephyr-sdk-*`); override with `ZEPHYR_BASE`, `ZEPHYR_SDK_INSTALL_DIR`, `MC_ZEPHYR_VENV`. These tests were not re-run after the removals. The host-test setup for the ESP-IDF version is still to be decided (see the spec).

## Hardware

See Part C of the spec; regenerate and order from `hardware/` (`gen_sch.py`, `gen_pcb.py`, `jlc_export.py`).
