# PlantModule

Plant device: an ESP32-C6 Zigbee end device, always awake for now (low power comes later). Design: [`specs.md`](specs.md).

```
firmware/    ESP-IDF project (build and flash: see below): main/, components/{mc_core,mc_hal,mc_zigbee}; host tests in firmware/test
hardware/    KiCad carrier board for the Waveshare ESP32-C6-Zero (specs.md Part C)
interface.yaml   the Zigbee interface definition (source for firmware header, converter and hub models)
scripts/     qr_png.swift (QR image for labels); the provisioning/label tool (make_label.py) is to be written
```

**State:** carrier board v1 is built and in hand; the firmware (host-tested core, hardware layer, esp-zigbee-sdk layer) builds, runs on the bench module and works with Zigbee2MQTT and the gateway (join, configuration, readings, watering, battery detection). Not done: provisioning (`make_label.py`, factory data, install codes), low power, a real battery cell test. The previous Zephyr/WiFi/MQTT/BLE firmware and its tests were removed and are in git history at commit `eb97b07`.

## Hardware

Regenerate and order from `hardware/`: `gen_sch.py` (schematic), `gen_pcb.py` (needs KiCad's bundled Python), `jlc_export.py` (JLCPCB files). `design.py` is the single source. Details and status in Part C of the spec.


## Build and flash the firmware

Needs **ESP-IDF v6.0.2** (installed with Espressif's installer; `~/.espressif/v6.0.2`), a USB cable to the module's USB-C port and, to see anything useful, a Zigbee coordinator with Zigbee2MQTT (the gateway, or `Gateway/scripts/bench.sh`).

### 1. Set up the shell (once per terminal)

```bash
source ~/.espressif/tools/activate_idf_v6.0.2.sh
cd PlantModule/firmware
```

### 2. Build

For a **bench module** (no factory data yet: it runs as the `carrier-v1` board and joins with the default Zigbee link key):

```bash
rm -f sdkconfig        # only when you switch between a bench and a release configuration
idf.py -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.dev" build
```

For a **release build** (no dev options; a module without valid factory data then enters safe mode, which is intended):

```bash
idf.py build
```

The target (ESP32-C6) is in `sdkconfig.defaults`, no `set-target` is needed. The first build downloads the Zigbee components (`espressif/esp-zigbee-lib`, `esp-zboss-lib`, pinned in `dependencies.lock`). Other options are in `idf.py menuconfig` under "PlantModule" and "PlantModule Zigbee": the development board and join flag, `CONFIG_MC_ZB_TX_POWER` (default 10 dBm) and `CONFIG_MC_ZIGBEE_STUB` (log instead of radio, for bench tests without a coordinator).

If the build stops with "build log version is too new" or a `build.ninja` error, the `build/` folder came from another ninja version: `idf.py fullclean`, then build again.

### 3. Find the module's port

```bash
ls /dev/cu.usb*          # macOS; Linux: ls /dev/ttyACM*
```

The ESP32-C6 shows up as `usbmodem…` (macOS) or `ttyACM…` (Linux). A Zigbee dongle shows up as `usbserial…`: do **not** flash that. The name changes when you use another USB port.

### 4. Flash

```bash
idf.py -p /dev/cu.usbmodem1101 flash
```

That writes the bootloader, the partition table and the app and **keeps the settings and the Zigbee network** (NVS and `zb_storage` are not touched). For a faster app-only update:

```bash
python -m esptool --port /dev/cu.usbmodem1101 write-flash 0x20000 build/plantmodule.bin
```

### Flashing all partitions (a new module, or a clean start)

`idf.py flash` writes the bootloader, the partition table, OTA data and the app. The **data partitions** are not written: `nvs` (settings, counters), `factory` (board name, serial, install code) and the Zigbee storage `zb_storage`/`zb_fct`. The layout is in `firmware/partitions.csv`:

| Partition | Offset | Size | Written by |
|---|---|---|---|
| bootloader | `0x0` | | `idf.py flash` |
| partition table | `0x8000` | | `idf.py flash` |
| `nvs` | `0x9000` | `0x6000` | the firmware at run time |
| `otadata` | `0xf000` | `0x2000` | `idf.py flash` |
| `phy_init` | `0x11000` | `0x1000` | the firmware at run time |
| `factory` | `0x12000` | `0x1000` | **`scripts/factory_image.py`, below** |
| `zb_storage`, `zb_fct` | `0x13000`, `0x17000` | `0x4000`, `0x1000` | the Zigbee stack at run time |
| `ota_0` (the app) | `0x20000` | `0x1a0000` | `idf.py flash` |

**A module from scratch** (all partitions, including the factory data):

```bash
python -m esptool --port /dev/cu.usbmodem1101 erase-flash                      # wipes everything, also the factory data
../scripts/factory_image.py --board carrier-v1 --serial MC000001 --out factory.bin
idf.py -p /dev/cu.usbmodem1101 flash                                           # bootloader, table, otadata, app
python -m esptool --port /dev/cu.usbmodem1101 write-flash 0x12000 factory.bin # the factory partition
```

`scripts/factory_image.py` builds the 4 KB image of the `factory` partition (layout in `specs.md` §10 and `mc_factory.h`; the C parser accepts what it writes). Add `--install-code <32 hex characters>` for a module that must use an install code and `--require-install-code` so that it refuses to join without one. Keep the install code and the image out of git: the code is a secret, and the gateway needs the same code to accept the module.

Without factory data a module enters safe mode (`factory_invalid`), unless it is a bench build (`sdkconfig.dev`), which runs as `carrier-v1`. A module with factory data is not touched by a normal `idf.py flash`, and a factory reset (10 s button) keeps it.

**One file** (for a production line, or to flash from another machine that has no ESP-IDF):

```bash
idf.py merge-bin                       # build/merged-binary.bin: bootloader, table, otadata and app in one image
python -m esptool --port /dev/cu.usbmodem1101 write-flash 0x0 build/merged-binary.bin
python -m esptool --port /dev/cu.usbmodem1101 write-flash 0x12000 factory.bin     # then the factory data
```

The merged image **fills the gaps between its parts with `0xFF`**, so writing it also **erases `nvs`, `factory` and the Zigbee storage**: the module forgets its settings and its network, and the factory data must be written again afterwards (the last line). Use it only for a clean start, never as an update of a module in use.

### 5. Look at the log

```bash
idf.py -p /dev/cu.usbmodem1101 monitor     # Ctrl+] leaves
```

**Opening the USB port of the C6 resets the module** (most serial tools do). That is harmless, but a module that is working would restart and rejoin. The log shows `boot reason`, `stack ready, joined` or `factory new`, and the Zigbee signals.

### 6. Join the module to the gateway

1. Open the join window (app: **Devices → Add device**).
2. A module that has never joined starts looking for a network by itself (fast LED blink, about three minutes). One that belonged to another network: **hold the button for 10 seconds** (factory reset), it restarts and looks for a network. A short press only identifies it (LED blinks); a 3 s hold starts a search when it is not joined.
3. The module appears in the app (joined, interview, configure, ready); set its slots in **Edit configuration**.

### When the Zigbee storage must be erased

A firmware that **changes the Zigbee attribute set** (new, removed or re-ordered attributes in `interface.yaml`) aborts at boot (`zb_assert`) with the Zigbee data of the old firmware. Erase it (and the settings, so the module searches for a network by itself) and let the module join again:

```bash
python -m esptool --port /dev/cu.usbmodem1101 erase-region 0x9000 0x6000     # NVS: settings, counters, "has booted" flag
python -m esptool --port /dev/cu.usbmodem1101 erase-region 0x13000 0x5000    # Zigbee storage and its factory-test partition
```

Then open the join window, wait for the module, and the gateway's configure step runs again. The same erase also helps a module whose network is gone (new coordinator).

### Changing a value of the interface

Values in `interface.yaml` (ranges, defaults, battery tunables) are compiled into the firmware; after editing it regenerate and rebuild:

```bash
python3 scripts/gen_interface_h.py && python3 ../Gateway/scripts/gen_converter.py && python3 ../Gateway/scripts/gen_hub_params.py
```

Not everything needs a flash: the table in `specs.md` §6.1 shows for each battery setting whether the module, the hub or both use it. Hub-only values (the percentage curve) need only the regenerate step and a hub restart; thresholds and calibration are set from the app and need no rebuild.

### Tests (no hardware, no ESP-IDF)

```bash
scripts/test_host.sh       # generated files are current, then the 127 host tests with ASan/UBSan
```

CI runs this on every pull request and also builds the firmware for the ESP32-C6 (`firmware-build` job in `.github/workflows/ci.yml`).
