# PlantModule — Specification

The PlantModule is the battery-powered plant device: an **ESP32-C6 running as a sleepy Zigbee end device** that measures soil moisture (and later other values), waters on command, and sleeps almost all the time. This file is its single specification: **Part A** the firmware, **Part B** its Zigbee interface (the contract with the Gateway's Zigbee2MQTT converter), **Part C** the carrier board.

Where it fits: the device talks only to the Gateway's Zigbee coordinator (`Gateway/specs.md` §7 and Part B); people never talk to it directly. System rules: [`PROJECT.md`](../PROJECT.md).

Folder: `firmware/` (ESP-IDF project), `hardware/` (KiCad carrier), `scripts/` (labels with install codes, firmware tests, build checks). Build and test commands: [`readme.md`](readme.md).

---

# Part A — Firmware

## 1. Requirements

- Read a configurable set of sensors and drive a pump; which module sits on which pin is **runtime configuration**, changed without reflashing.
- Report readings and health to the Gateway every wake; execute commands (e.g. "run pump for N s") and apply configs sent by the Gateway.
- Live on a battery: deep sleep between wakes, minutes-level command latency is accepted.
- Enforce hard safety limits locally, whatever the Gateway sends.
- Join the Gateway's Zigbee network without any credentials typed into the device.

## 2. Hardware target

**ESP32-C6** (RISC-V, 2.4 GHz WiFi 6 / BLE 5 / 802.15.4). Only the 802.15.4 radio is used; WiFi and BLE stay off. Final hardware is the carrier board in Part C (Waveshare ESP32-C6-Zero module), whose first revision (`carrier-v1`) exists and is the first development target. An ESP32-C6-DevKitC-1 board description (`devkitc-1`) is kept for bench work.

| Aspect | Notes |
|---|---|
| ADC | Only ADC1 (GPIO0–6); there is **no ADC2/WiFi conflict** any more, so sensors can be read at any time in the cycle. |
| Deep-sleep wake and pin hold | Low-power (LP) pins GPIO0–7 can wake the chip and **hold their output state through deep sleep**; a pump that must keep running across sleep has to sit on one of them (carrier ports 1–4 are GPIO1–4). |
| Strapping pins | GPIO8, 9, 15 and the USB pins are not used for modules. GPIO4 and GPIO5 are also strapping pins on the C6 (**verify** against the datasheet); on the carrier they carry port 4 and the battery sense. |
| Console | USB-Serial-JTAG. |

### 2.1 Board revisions and the board description

The carrier board will change between revisions, so no pin number is hard-coded in the application. Everything that depends on the PCB is in a **board description**, one file per revision (`firmware/boards/<name>.json`, for example `carrier-v1`, `devkitc-1`):

| Field | Meaning |
|---|---|
| `name`, `hw_version` | Board name (`carrier-v1`) and numeric hardware version, reported to the Gateway |
| `ports` | Logical ports `P1…Pn`: for each the GPIO, the ADC channel, whether it is a low-power pin that can **hold** an output through deep sleep, and which roles it supports (analog sensor, digital in, digital out/pump) |
| `i2c` | SDA/SCL GPIOs and whether the pull-ups can be switched |
| `battery` | Sense GPIO, ADC channel, divider ratio (carrier v1: 2.0) |
| `led`, `button` | GPIO, polarity, and for the button whether it can **wake** the chip from deep sleep (carrier v1: no) |
| `sensor_power` | Optional switched sensor supply: GPIO, polarity, settle time in ms; absent when the sensors are powered permanently (carrier v1) |
| `reserved` | Pins the application must not use (strapping, console, flash) |
| `allow_raw_gpio` | Whether slots may name raw GPIOs (true on dev kits, false on the carrier) |

- **One source:** the JSON files are the single source. The firmware build turns them into a C table; the Gateway ships the same files and serves them as `GET /meta/boards/{board}`, so the slot editor offers only ports and roles that exist on that board.
- **Which board am I:** the board name is stored in the `factory` partition next to the install code (§9), written at flashing time by the label tool. One firmware image therefore supports every revision, and the board of an already built v1 needs no hardware change. If the partition has no board entry, the firmware falls back to a build-time default (`CONFIG_MC_DEFAULT_BOARD`). From a later revision on, an ID resistor on a spare GPIO can be read as a second source and checked against the partition.
- **Reporting:** the device reports the board name and hardware version (Basic cluster `HWVersion` and the custom status), the Gateway looks up the matching description.
- **Sensor power:** if the board description has a `sensor_power` entry, the firmware switches the sensor supply on, waits the settle time, reads, and switches it off again around every read. Without the entry sensors are assumed to be powered permanently, and the spec's battery estimates must account for their current (Part C, limitations).
- **Unknown board:** a name the firmware does not know is a fatal configuration error reported on the console; the device does not drive any output.

## 3. Software stack

- **ESP-IDF** with **`esp-zigbee-sdk`** (Zigbee 3.0 end device, `ZB_ED_ROLE`, sleepy). Exact versions are pinned in the project; **verify** that the pinned release supports the ESP32-C6 sleepy end device with deep sleep and fast rejoin.
- FreeRTOS tasks: one for the Zigbee stack, one for the application cycle.
- Non-volatile storage: NVS (configuration, network and join state kept by the Zigbee stack, boot counters); `factory` partition for the install code; `ota_0`/`ota_1` for Zigbee OTA (later).
- Retained state across deep sleep: RTC memory (cycle state, reading ring buffer, pump-hold bookkeeping).

## 4. Module slots

A fixed table of slots (6) is the single source of truth for what is connected where. Each slot: `{module type, port, options}`. A slot refers to a **logical port** of the board (`P1…Pn`, I2C) from the board description (§2.1), never to a raw GPIO number, so a stored configuration keeps working when a new PCB revision wires the port to a different pin. Boards with `allow_raw_gpio` (dev kits) also accept raw GPIOs.

- At runtime the firmware resolves each slot's port through the board description and configures GPIO and ADC (IDF GPIO/ADC drivers); nothing is bound to a pin at compile time.
- Each module type is a small driver registered in a static table: `probe`, `init`, `read` (sensors), `write` (actuators such as the pump).
- Validation of a desired config (port exists on this board and supports the module's role, duplicates, pump on a hold-capable port when a long run is requested, limits) runs on the device as the final authority. The Python mirror (`mc_core.pins`) lets the Gateway reject bad configs earlier.

**Drivers.** To build first: `moisture_*` (analog, capacitive/resistive) and the GPIO pump (an implementation for the previous firmware is in git history, see 11). Later, until then reported `not_found` plus one `sensor_fault` event: DS18B20, SHT3x, `water_level_float`. I2C/1-Wire auto-detect stays a later feature (analog presence only; pumps are always configured manually).

**Configuration path.** The slot table lives in NVS and survives reboot and deep sleep. The Gateway sends a new configuration as attribute writes plus a commit command (Part B §4 and §5); the device validates, applies atomically, persists and reports the revision it runs.

## 5. Moisture calibration

Moisture slots map raw ADC counts to 0–100 % with a two-point calibration in the slot config, `cal: {dry, wet}` (raw counts at 0 % and at 100 %).

- **Polarity follows the two points.** `dry > wet`: small counts are wetter (typical capacitive sensor); `dry < wet`: the scale is reversed. `mc_moisture_convert()` handles both; results clamp to 0–100 %. A raw value more than 15 % of the span outside either point is `out_of_range`; counts at the ADC limits are `no_signal`.
- **Calibration is config, not device state.** The Gateway owns it; the device persists it and never changes it itself. A re-calibration is a normal new config revision.
- **Default** when absent: `dry` 3000 / `wet` 1200 (placeholders; the 12-bit ADC range of the C6 should be rechecked on the board).
- **Validation today:** `dry == wet` is rejected. **Planned:** both values within the ADC range and `|dry − wet| ≥ 300`, on both sides.
- **Raw values are always reported** next to the percentage, so the hub can recompute history after a re-calibration.
- **Planned: capture command** `sensor_sample` (Part B §5): reads the slot's ADC `samples` times (default 16, max 64) and answers with median, min and max, without touching the stored config. An empty or actuator slot is rejected with `slot_not_sensor`; a floating input fails with `hw_error`. The calibration wizard in the app is built on it.

## 6. Wake cycle and power

Nothing can reach a deep-sleeping device. The device wakes on its own schedule, **reports**, and stays reachable for a short **awake window**; the Gateway sends pending commands and configs inside that window (`Gateway/specs.md` §9.4).

### 6.1 Sequence (every wake)

1. Wake from deep sleep (RTC timer, or button).
2. Read all sensor slots; push the new record into the RTC ring buffer.
3. Restore the Zigbee stack from stored network state and **rejoin quickly** (no new commissioning). **Verify** time to reconnect and current draw.
4. Report: telemetry attributes (readings per slot, battery, `seq`), then the status attribute (`online`, wake interval, `next_wake_s`). Buffered records from earlier failed wakes are reported oldest first.
5. **Awake window:** stay awake with a fast poll interval for `awake_s` seconds (default 5 s, max 60). Each received command or configuration write re-arms the window by a few seconds so a sequence of messages completes.
6. Process what arrives: apply desired configuration (write + commit), execute commands, report results (`cmd_ack`, `config_state`).
7. Report status `sleeping` with `next_wake_s`, stop the Zigbee stack cleanly, set up the timer and pin holds, deep sleep.

### 6.2 If the network is not reachable

After a failed rejoin the device keeps the readings in the RTC ring buffer (oldest dropped when full), retries on the next wake with a growing interval (back-off up to one hour) and tries a fresh network search only after repeated failures, so a missing coordinator does not drain the battery. A device that never found a network sleeps with the default interval and waits for a button press (§8).

### 6.3 Pump runs

- Runs up to 15 s (`MC_PUMP_INLINE_MAX_S`) happen inside the awake window.
- Longer runs use **pin hold through deep sleep** on an LP pin: the pump output keeps its state and the device wakes at the end of the run to switch it off, then reports the result. A pump on another pin runs inside the window (up to `max_run_s`, at most 300 s).
- `pump_stop` and `cancel` are never refused for lack of time information: stopping a pump must always work.
- A `cancel` in the same delivery wins over its target; a cancel for a command not seen yet leaves a tombstone so the command is answered `cancelled` when it arrives.
- Outputs come up **off** after any reset; fatal errors restart the device.

### 6.4 Wake interval, awake window and commissioning

- **`wake_interval_s`**: 60–86400, default 600. The old "0 = never sleep" mode is replaced by the commissioning window below.
- **`awake_s`**: 2–60, default 5. Window after each report. It must be long enough for the Gateway to deliver a few messages one by one (about a second each); the value is a trade-off between latency and battery.
- **Commissioning window:** after joining a network and after a button wake the device stays awake and fast-polling for **5 minutes** (`MC_COMMISSION_S`), so a new device can be named and configured and commands arrive within seconds; it then follows the normal cycle. Status `service` is reported meanwhile.
- **Low battery** (< 3.3 V): one `low_battery` event and the interval is multiplied by 3 until the battery recovers (> 3.5 V).
- The wake interval is the main battery lever; Zigbee reconnect and the awake window dominate a wake's energy, deep-sleep current only matters at long intervals. Measure both early.

### 6.5 Buffering and time

- The new record goes into the RTC ring buffer **before** any radio activity. After the Zigbee stack confirms delivery of a report, the record is dropped. A failed wake loses nothing until the buffer is full.
- The device has **no wall clock**: no SNTP. Reports carry a monotonically increasing `seq`; the Gateway stamps messages with its receive time. Commands carry a **time to live** in seconds (`ttl_s`) instead of an absolute expiry; the device converts it to a local deadline using its RTC timer, which keeps counting through deep sleep. Min-pause bookkeeping uses the same timer.

## 7. Zigbee behaviour

- **Role:** sleepy end device, one parent (the coordinator or a router).
- **Joining:** the device searches for a network only when it is not on one: on first boot after flash or factory reset, or after a 3 s BOOT press (§8). Joining uses the install code from the factory partition when the coordinator has one registered for the device (the Gateway offers it, `Gateway/specs.md` §7.3).
- **Rejoin:** after losing its parent (for example the coordinator was replaced), the device tries rejoin with the stored network key a few times with back-off; if that fails it needs a button press to join again.
- **Reporting:** configured attribute reporting is switched off; the firmware sends reports itself at the end of the read phase so that report and awake window are tied together.
- **Standard clusters** on endpoint 1: Basic (identity, model `MC-PLANT`, software build), Power Configuration (battery voltage and percentage), Identify. The soil-moisture cluster of the first moisture slot may be mirrored for compatibility with generic Zigbee tools (**verify** support in the SDK; otherwise custom-only).
- **Custom cluster** `0xFC11` (manufacturer-specific): everything else, see Part B.
- **OTA** (later): Zigbee OTA Upgrade cluster, images served through Zigbee2MQTT; two OTA partitions are reserved in the partition table from the start so a later firmware can add it.

## 8. Buttons and LED

BOOT/user button (on the carrier: SW1, see the pin note in Part C):

- **3 s hold:** open the join/commissioning mode: leave nothing, but search for a network (if not on one) or start the 5-minute commissioning window (if on one).
- **10 s hold:** factory reset: leave the network, clear configuration and joined state; the install code in the factory partition stays.

LED: solid while awake, slow blink while searching for a network, fast blink for the "keep holding" cue at 3 s, off in deep sleep.

On the carrier board the button is not on a wake-capable pin (Part C); until it is moved to GPIO0, a button press cannot wake a sleeping device, so the commissioning window after join (and a power cycle) is the way to reconfigure it.

## 9. Install code and labels

- Each device has an **install code** (Zigbee install code: 128-bit code plus CRC16, shown as 36 hex characters) generated at flashing time and stored in the `factory` partition together with the **board name** (§2.1) and a serial number, never erased by factory reset.
- `scripts/make_label.py --board carrier-v1` generates it, writes the factory page (install code, board, serial), and prints a label with a QR code of the form `MCIC1:<model>:<install-code>`. The CSV of devices (`scripts/factory/devices.csv`) holds the secrets and is git-ignored.
- The Gateway registers the code with Zigbee2MQTT before the device joins; the coordinator then accepts only a device that proves it knows the code, which keeps a neighbour from joining while the network is open.
- Without an install code the device joins with the default (well-known) link key while permit-join is open. This is acceptable for development, not for a deployed household.

## 10. Safety

- Hard limits per pump (`max_run_s`, `min_pause_s` and a hard ceiling in firmware) are enforced on the device. The Gateway checks commands again before sending, but the device is the final authority.
- Commands past their time to live are dropped.
- Outputs come up off after any restart.
- Sensor errors (`no_signal`, `out_of_range`, `not_found`) are reported, never turned into a value.

## 11. Code layout (target)

```
firmware/
├── CMakeLists.txt · sdkconfig.defaults · partitions.csv
├── main/                  app_main: boot → cycle → sleep
├── components/
│   ├── mc_core/           portable logic: config + pin rules, commands, moisture conversion, retained state, the wake cycle (mc_cycle)
│   ├── mc_hal/            ESP32-C6: ADC, pump GPIO + pin hold, NVS, RTC retained state, deep sleep, button, LED, battery
│   ├── mc_zigbee/         esp-zigbee-sdk: network join/rejoin, endpoint and clusters, reports, command handling, OTA later
│   └── mc_drivers/        module drivers (moisture, pump, later more)
├── boards/                ESP32-C6-DevKitC-1 and the carrier board description
└── tests/                 host tests of mc_core
scripts/                   make_label.py (install codes), build and test helpers
hardware/                  carrier board (Part C)
```

- The wake cycle depends only on a small I/O interface (sensors, pump, radio, clock, storage), so the exact sequence runs in unit tests against fakes. The host-test framework for `mc_core` (for example Unity on an ESP-IDF host build) is **pending**.
- The previous firmware (Zephyr, WiFi + MQTT, BLE pairing) was removed; it is in git history at `eb97b07`. Its portable core (`PlantModule/firmware/src/core`: `mc_config`, `mc_cmd`, `mc_cycle`, `mc_sensor`, `mc_pins`, `mc_rtc`, and their ztest suites) is the reference for `mc_core`; its hardware layer is a reference for `mc_hal`.

## 12. Status, prototype plan and open points

Status: this specification and the **carrier board v1** (built, in hand, untested) exist. No firmware is in the repository yet.

### 12.1 Prototype 1 (on carrier v1, with a Zigbee coordinator and Zigbee2MQTT)

Goal: answer the open Zigbee and power questions on the real board before the real firmware is written.

1. Minimal ESP-IDF + `esp-zigbee-sdk` image (sleepy end device, board `carrier-v1` hard-coded): join, report a dummy value, deep sleep on a timer, rejoin fast.
2. Measure on the carrier: deep-sleep current with no sensor, with a sensor on a port, and with the battery divider; energy per wake (rejoin + report + awake window).
3. Awake window: how many sequential Zigbee2MQTT writes and one command round trip fit in it; which poll interval is needed.
4. Pump pin hold: a port output holds its level through deep sleep, and the wake at the end of a run switches it off.
5. ADC: read a real moisture sensor and the battery through the divider; fix the divider ratio and sensor ranges.
6. Button: confirm GPIO21 cannot wake from deep sleep; test a wire from the button to GPIO0 (TP1) as the v1 workaround.
7. Range: join and report through a wall; check the antenna placement on the carrier.
8. Record the results in this spec (sleep current, energy per wake, awake window, poll interval) and fix the Part B IDs.

### 12.2 Open points

- Does `esp-zigbee-sdk` on the C6 give a **deep-sleeping sleepy end device with fast rejoin**, and what are the sleep current and the energy per wake?
- Length of the awake window and poll interval needed for the Gateway to deliver several messages reliably.
- Sensor supply on v1 (permanently powered): battery life with the sensors you use, and whether a mod wire from a spare GPIO is worth it; the switched supply is a v2 item (Part C).
- Whether the first moisture slot can also appear as the standard soil-moisture cluster.
- Final cluster layout (Part B) and the Zigbee2MQTT converter; manufacturer code.
- Host-test framework for `mc_core`.
- Strapping behaviour of GPIO4/GPIO5 with sensors attached.
- I2C/1-Wire auto-detect and more drivers; Zigbee OTA.
- Reading buffer size in RTC memory.
- A Zigbee coordinator stick and its firmware version for the prototype.

---

# Part B — Zigbee interface (device ↔ Gateway)

The contract between the PlantModule firmware and the Gateway's Zigbee2MQTT external converter. It carries the normalized messages of `Gateway/specs.md` Part B.

**Status:** design proposal, to be fixed on the prototype. Cluster and attribute IDs below are provisional. Attribute reporting is done by the firmware itself (Part A §7), and one Zigbee message carries at most about 80 bytes of payload without fragmentation, so every item is kept small.

## 1. Device model

| Item | Value |
|---|---|
| Device type | Zigbee 3.0 sleepy end device, one endpoint (1), profile Home Automation, device ID configuration tool or custom |
| Model identifier (Basic cluster) | `MC-PLANT`; manufacturer name `MoistureController` |
| Standard clusters | Basic (0x0000), Power Configuration (0x0001), Identify (0x0003) |
| Custom cluster | `0xFC11`, manufacturer-specific (manufacturer code to be assigned; a test code is used in development) |
| Identity | The IEEE address; there is no other device ID |

## 2. Encoding rules

- Integers are little endian as in ZCL. Strings and blobs are ZCL octet strings (length byte first, ≤ 32 bytes here).
- Percent values use fixed point (value × 100, signed 16-bit); unknown/error is `0x8000`.
- Commands carry a 32-bit `cmd_id` chosen by the Gateway per command (it keeps the mapping to its own ID) and a `ttl_s`.

## 3. Telemetry attributes (device → Gateway, read-only)

| ID | Name | Type | Meaning |
|---|---|---|---|
| 0x0100 | `seq` | uint16 | Wake counter, increments per wake (wraps) |
| 0x0101 | `boot` | uint16 | Boot counter |
| 0x0110 + n | `slot_n` (n = 0…5) | octet string (8) | `type` uint8 · `error` uint8 (0 ok, 1 no_signal, 2 out_of_range, 3 not_found, 4 hw_error) · `value` int16 (×100) · `raw` uint16 · `cfg_rev` uint16 |
| 0x0120 | `status` | uint8 | 0 online, 1 sleeping, 2 service |
| 0x0121 | `next_wake_s` | uint32 | Seconds until the next planned wake |
| 0x0122 | `wake_reason` | uint8 | 0 timer, 1 button, 2 pump_end, 3 reset |
| 0x0123 | `awake_left_s` | uint8 | Remaining awake window, so the Gateway can plan the sender |

Standard clusters carry battery voltage (0x0001/0x0020, 100 mV units) and percentage (0x0001/0x0021).

## 4. Configuration (Gateway → device)

Attributes are written with Write Attributes; nothing becomes active until the commit command.

| ID | Name | Type | Meaning |
|---|---|---|---|
| 0x0001 | `wake_interval_s` | uint32 | 60–86400 |
| 0x0002 | `awake_s` | uint16 | 2–60 |
| 0x0003 | `batt_low_mv` | uint16 | Low-battery threshold |
| 0x0010 + n | `slot_cfg_n` (n = 0…5) | octet string (≤ 24) | `module` uint8 (0 empty, 1 moisture, 2 pump, …) · `port` uint8 (0 = P1 … 5 = P6; `0x80 + n` = raw GPIO n on boards that allow it) · `flags` uint8 · parameters by module: moisture `cal_dry` uint16, `cal_wet` uint16, `samples` uint8; pump `max_run_s` uint16, `min_pause_s` uint16 (bit 0 of `flags`: active high) |

Reported back (read-only, reported after each commit and at each wake):

| ID | Name | Type | Meaning |
|---|---|---|---|
| 0x0030 | `cfg_rev` | uint16 | Revision the device runs |
| 0x0031 | `cfg_result` | uint8 | 0 ok, 1 rejected |
| 0x0032 | `cfg_error` | uint8 + uint8 | Error code (as in the previous config contract (git history, see 11): `port_invalid`, `port_conflict`, `out_of_range`, …) and the slot it applies to |

## 5. Cluster commands

Client → device (sent by the Gateway):

| ID | Command | Payload | Meaning |
|---|---|---|---|
| 0x00 | `commit_config` | `rev` uint16 | Validate the written attributes as revision `rev`, apply atomically, persist, report `cfg_*` |
| 0x01 | `pump_run` | `cmd_id` uint32 · `slot` uint8 · `seconds` uint16 · `ttl_s` uint16 | Run the pump; answers with `cmd_ack` |
| 0x02 | `pump_stop` | `cmd_id` uint32 · `slot` uint8 | Stop at once |
| 0x03 | `cancel` | `cmd_id` uint32 · `target` uint32 | Cancel a not yet started command |
| 0x04 | `device_action` | `cmd_id` uint32 · `action` uint8 (identify, service, reboot) · `arg` uint16 | Identify blink, keep awake (commissioning), reboot |
| 0x05 | `sensor_sample` *(planned)* | `cmd_id` uint32 · `slot` uint8 · `samples` uint8 | Capture raw values for calibration |

Device → client (generated by the device):

| ID | Command | Payload | Meaning |
|---|---|---|---|
| 0x00 | `cmd_ack` | `cmd_id` uint32 · `state` uint8 (0 running, 1 done, 2 failed, 3 rejected, 4 cancelled) · `reason` uint8 · `ends_in_s` uint16 · `result` (for `sensor_sample`: median, min, max uint16) | Result of a command; `running` is sent right away for long runs, `done` when the pump has stopped |
| 0x01 | `event` | `code` uint8 · `slot` uint8 · `arg` uint16 | `low_battery`, `sensor_fault`, `safety_stop`, `boot`, … |

Reason codes follow the old contract (`expired`, `busy`, `limit`, `slot_not_actuator`, `slot_not_sensor`, `hw_error`, …) as small integers.

## 6. Timing

- The device reports once per wake, then listens for `awake_s` (re-armed per received message). The Gateway's sender (`Gateway/specs.md` §9.4) sends one item at a time and waits for its acknowledgement (the Zigbee APS ack, plus `cmd_ack` for commands).
- A command's `ttl_s` starts when the device receives it; the device answers `rejected` with reason `expired` if it cannot run it in time.
- A device that has not reported for 3 intervals is `offline` for the hub.

## 7. Zigbee2MQTT converter

The converter lives in `Gateway/firmware/zigbee2mqtt/` and maps Part B to the hub's normalized messages: report attributes → `telemetry`/`status`/`config_state` messages, cluster commands from the device → `cmd_ack`/`event`, and the hub's `set` payloads → attribute writes and cluster commands. Its definition (exposes, fromZigbee, toZigbee, model `MC-PLANT`) is part of the pinned Zigbee2MQTT setup.


---

# Part C — Carrier board (hardware)

A 70 × 58 mm two-layer carrier for the **Waveshare ESP32-C6-Zero** (the ESP32-C6 provides the 802.15.4 radio for Zigbee), soldered flat onto it through its castellated edge pads, USB-C end flush with the top edge. Source: `hardware/` (open `carrier.kicad_pro` in KiCad 10).

> **Firmware status:** the Zigbee firmware for this board is not built yet (Part A). The button behaviour in Part A §8 (3 s join/commissioning, 10 s factory reset, wake from deep sleep) assumes a button on a wake-capable pin. SW1 is on GPIO21, which is not one, so a press cannot wake a sleeping device; moving it to GPIO0 (TP1) is the planned revision. Until then the commissioning window after joining or power-up is how a device is reconfigured.

## What is on it

| Ref | What | Pins (pin 1 first) |
|---|---|---|
| J1–J4 | 3-pin JST-XH ports, sensor or pump signal | 3V3, SIG, GND |
| J5, J6 | 2× I2C, JST-XH 4-pin, one shared bus | 3V3, GND, SDA, SCL |
| J7 | power in, JST-XH 3-pin | VIN (5 V), GND, VBAT (raw cell, sense only) |
| JP1 | source select, 1×3 header with a shunt | VIN, COM, VBAT |
| J8 + JP4 | optional power switch (cut JP4 when J8 is used) | |
| D1 | B5819W Schottky, COM → module 5 V pad | blocks USB back-feed and reverse polarity |
| R3/R4/C7 | battery divider, 330k/330k, 100 nF | firmware divider = 200 % |
| SW1 | user button, not on the BOOT line | |
| D2 + R6 | status LED, active high | |
| J9 | optional UART0 header | GND, TX, RX |
| TP1 | spare GPIO0 test pad (low-power pin) | |
| JP2, JP3 | I2C pull-up solder jumpers, closed by default | cut to disable |

Ports J1–J4 take pin 1 from the module's always-on 3V3. For a pump use SIG and GND only and power the pump separately.

## Pin map (ESP32-C6)

| Function | GPIO |
|---|---|
| Ports 1–4 (ADC1, low-power pins) | 1, 2, 3, 4 |
| Battery sense (ADC1) | 5 |
| I2C SDA / SCL | 18 / 19 |
| Status LED | 20 |
| User button | 21 |
| UART0 TX / RX | 16 / 17 |
| Spare (test pad) | 0 |
| Not used, left open | 14, 15 (strapping), 22 |

GPIO21 is not a low-power pin, so the button cannot wake the chip from deep sleep. To get that, move the button to GPIO0 (TP1).

## Power

- `JP1` on 1–2: the board runs from VIN (5 V from a charger/boost board).
- `JP1` on 2–3: the raw cell feeds the module's 5 V pad through D1. The module's LDO needs about 3.5 V or more on the cell, so the last part of the capacity is unused.
- No charging on this board; use a charger/boost module on J7 (VIN, GND, VBAT).
- Revision A: never connect the module's USB-C and a charger at the same time.

## Files and regeneration

`hardware/design.py` is the single source (parts, nets, pin map) read by `gen_sch.py`, `gen_pcb.py`, `router.py` and `jlc_export.py`; the KiCad files are generated. `bom.csv` is the readable bill of materials, `lib/` holds the project's symbols and footprints, `carrier-backups/` KiCad's automatic snapshots.

Run from `PlantModule/hardware/`:

```
python3 gen_sch.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 gen_pcb.py   # needs pcbnew; places and routes
kicad-cli pcb drc --refill-zones --save-board carrier.kicad_pcb                                          # fills the GND pours
```

## Ordering

`python3 jlc_export.py` (KiCad closed or saved) writes `jlcpcb/`: `carrier_gerber.zip`, `bom_jlcpcb.csv` (LCSC numbers, which live in `jlc_export.py`), `cpl_jlcpcb.csv` (SMD placement) and `parts_overview.csv` (everything, including what to buy elsewhere). `jlcpcb/` is generated output; re-run after every board change.

- JLCPCB assembles the SMD parts (top side); check the part rotations in their preview.
- Hand-solder the ESP32-C6-Zero (bought without headers), the pin headers and the XH headers unless the quote offers through-hole assembly.
- Bastelgarage: the module (Waveshare, "ohne Headers") and JST-XH pigtail cables for the mating side.

## Status

- Schematic: no ERC violations, netlist matches `design.py`.
- PCB: no DRC errors or unconnected nets, passes schematic parity. Silkscreen-over-copper notes remain on the solder jumpers and mounting holes.
- **The routing is an autorouted baseline**: tidy and review it in KiCad (long diagonals, vias, pour stitching) before ordering.
- The module footprint comes from the dimension drawing on Waveshare's wiki (18.00 × 23.50 mm, 2.54 mm pitch, first pad 1.59 mm from the USB end); compare against a real module or the 3D files before ordering. The pad length is a soldering choice.
- Revision **v1** is fabricated and in hand; it has not been tested yet (sensors, connectors, ADC readings, sleep current, range).

## Known limitations of v1 and wishlist for the next revision

| Topic | v1 | Next revision |
|---|---|---|
| Sensor supply | Pin 1 of every port is the always-on 3V3, so sensors draw current during deep sleep and limit battery life | A switched sensor rail (load switch on a GPIO) so sensors are powered only around a read; the board description then gains a `sensor_power` entry |
| Button | On GPIO21, which cannot wake the chip from deep sleep | On GPIO0 (low-power pin); until then the commissioning window after power-up is the way to reconfigure |
| Board ID | None; the board name is stored in the factory partition by the label tool | An ID resistor divider on a spare GPIO read at boot |
| Battery divider | 330k/330k permanently connected (about 5 µA at 3.7 V) | Optional switch or higher resistance |
| Strapping pins | Port 4 (GPIO4) and the battery sense (GPIO5) are strapping pins on the C6 (**verify**) | Move to non-strapping low-power pins if the check shows a problem |
| Pump | Ports carry SIG and GND only; an external driver module is needed | Optional on-board MOSFET driver for one port |
| Battery connector | Raw cell and charger come in through J7 | Dedicated battery connector and charger/protection |
| Antenna | Keep-out around the module's antenna not verified | Verified in the range test (prototype step 7) |
