# PlantModule

Battery-powered plant device: an ESP32-C6 Zigbee end device. Design: [`specs.md`](specs.md).

```
firmware/    ESP-IDF project (to be written; target layout in specs.md Part A §11)
hardware/    KiCad carrier board for the Waveshare ESP32-C6-Zero (specs.md Part C)
scripts/     qr_png.swift (QR image for labels); the install-code label tool is to be written
```

**State:** the carrier board is designed (not fabricated); there is no firmware in the repository yet. The previous Zephyr/WiFi/MQTT/BLE firmware and its tests were removed and are in git history at commit `eb97b07`.

## Hardware

Regenerate and order from `hardware/`: `gen_sch.py` (schematic), `gen_pcb.py` (needs KiCad's bundled Python), `jlc_export.py` (JLCPCB files). `design.py` is the single source. Details and status in Part C of the spec.
