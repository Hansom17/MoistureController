# PlantModule

Plant device: an ESP32-C6 Zigbee end device, always awake for now (low power comes later). Design: [`specs.md`](specs.md).

```
firmware/    ESP-IDF project: main/, components/{mc_core,mc_hal,mc_zigbee}; host tests in firmware/test
hardware/    KiCad carrier board for the Waveshare ESP32-C6-Zero (specs.md Part C)
interface.yaml   the Zigbee interface definition (source for firmware header, converter and hub models)
scripts/     qr_png.swift (QR image for labels); the provisioning/label tool (make_label.py) is to be written
```

**State:** carrier board v1 is built and in hand (untested); the firmware core (host-tested) and the hardware layer build; the Zigbee layer is still a stub. The previous Zephyr/WiFi/MQTT/BLE firmware and its tests were removed and are in git history at commit `eb97b07`.

## Hardware

Regenerate and order from `hardware/`: `gen_sch.py` (schematic), `gen_pcb.py` (needs KiCad's bundled Python), `jlc_export.py` (JLCPCB files). `design.py` is the single source. Details and status in Part C of the spec.
