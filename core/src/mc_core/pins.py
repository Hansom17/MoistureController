"""Pin rules for the DOIT ESP32 DevKit V1 (firmware/Firmware_Specs.md).

Used by the backend to validate desired configs and served to the app via
`GET /meta/boards/{board}`, so the slot editor never duplicates these rules.
The firmware validates again (mqtt.md §6.2) — it stays the final authority.
"""

from dataclasses import dataclass

from .contract.device import ConfigDesired, ConfigError, Limits

BOARD = "doit_esp32_devkit_v1"

RESERVED = {
    0: "BOOT button / strapping",
    1: "UART0 TX",
    2: "onboard LED",
    3: "UART0 RX",
    6: "SPI flash",
    7: "SPI flash",
    8: "SPI flash",
    9: "SPI flash",
    10: "SPI flash",
    11: "SPI flash",
}
INPUT_ONLY = {34, 35, 36, 39}
ADC1 = {32, 33, 34, 35, 36, 39}
ADC2 = {4, 12, 13, 14, 15, 25, 26, 27}
# GPIOs broken out on the DevKit V1 header.
EXPOSED = {4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33, 34, 35, 36, 39}
OUTPUT_CAPABLE = EXPOSED - INPUT_ONLY
STRAPPING_WARN = {12: "MTDI strapping pin — keep low at boot", 15: "MTDO strapping pin"}

# Defaults until the device reports its own `limits` (config/state).
DEFAULT_LIMITS = Limits(max_run_s_hard=300, slots_max=6)


@dataclass(frozen=True)
class ModuleSpec:
    bus: str  # adc | gpio_out | gpio_in | onewire | i2c
    pins: frozenset[int]  # allowed pins; empty for I2C (address instead)
    actuator: bool = False
    detectable: bool = False


MODULES: dict[str, ModuleSpec] = {
    "moisture_capacitive": ModuleSpec("adc", frozenset(ADC1 | ADC2)),
    "moisture_resistive": ModuleSpec("adc", frozenset(ADC1 | ADC2)),
    "pump_relay": ModuleSpec("gpio_out", frozenset(OUTPUT_CAPABLE), actuator=True),
    "ds18b20": ModuleSpec("onewire", frozenset(OUTPUT_CAPABLE), detectable=True),
    "sht3x": ModuleSpec("i2c", frozenset(), detectable=True),
    "water_level_float": ModuleSpec("gpio_in", frozenset(EXPOSED)),
}


def board_description() -> dict:
    """Payload of `GET /meta/boards/doit_esp32_devkit_v1`."""
    return {
        "board": BOARD,
        "reserved_pins": [{"pin": p, "reason": r} for p, r in sorted(RESERVED.items())],
        "input_only_pins": sorted(INPUT_ONLY),
        "adc2_pins": sorted(ADC2),
        "warnings": [{"pin": p, "detail": d} for p, d in sorted(STRAPPING_WARN.items())],
        "modules": [
            {
                "module": name,
                "bus": spec.bus,
                "actuator": spec.actuator,
                "auto_detect": spec.detectable,
                "allowed_pins": sorted(spec.pins),
            }
            for name, spec in MODULES.items()
        ],
        "limits": DEFAULT_LIMITS.model_dump(),
    }


def validate_config(cfg: ConfigDesired, limits: Limits | None = None) -> list[ConfigError]:
    """All problems of a desired config; empty list = valid (mqtt.md §6.2)."""
    limits = limits or DEFAULT_LIMITS
    errors: list[ConfigError] = []
    used: dict[int, int] = {}
    slots_seen: set[int] = set()

    if len(cfg.slots) > limits.slots_max:
        errors.append(ConfigError(code="out_of_range", detail=f"at most {limits.slots_max} slots"))

    for s in cfg.slots:
        spec = MODULES.get(s.module)
        if spec is None:
            errors.append(ConfigError(slot=s.slot, code="unknown_module"))
            continue
        if s.slot >= limits.slots_max or s.slot in slots_seen:
            errors.append(ConfigError(slot=s.slot, code="out_of_range", detail="invalid slot index"))
        slots_seen.add(s.slot)

        if spec.bus == "i2c":
            if s.addr is None or not 0x08 <= s.addr <= 0x77:
                errors.append(ConfigError(slot=s.slot, code="out_of_range", detail="I2C address"))
        else:
            if s.pin is None:
                errors.append(ConfigError(slot=s.slot, code="out_of_range", detail="pin missing"))
                continue
            if s.pin in RESERVED:
                errors.append(ConfigError(
                    slot=s.slot, code="pin_reserved", detail=f"GPIO {s.pin}: {RESERVED[s.pin]}"))
            elif spec.actuator and s.pin in INPUT_ONLY:
                errors.append(ConfigError(
                    slot=s.slot, code="pin_not_output", detail=f"GPIO {s.pin} is input-only"))
            elif s.pin not in spec.pins:
                errors.append(ConfigError(
                    slot=s.slot, code="out_of_range",
                    detail=f"GPIO {s.pin} not usable for {s.module}"))
            if s.pin in used:
                errors.append(ConfigError(
                    slot=s.slot, code="pin_conflict",
                    detail=f"GPIO {s.pin} also used by slot {used[s.pin]}"))
            used.setdefault(s.pin, s.slot)

        if spec.actuator:
            if s.max_run_s is None or not 1 <= s.max_run_s <= limits.max_run_s_hard:
                errors.append(ConfigError(
                    slot=s.slot, code="out_of_range",
                    detail=f"max_run_s must be 1–{limits.max_run_s_hard}"))
            if s.min_pause_s is not None and s.min_pause_s < 0:
                errors.append(ConfigError(slot=s.slot, code="out_of_range", detail="min_pause_s"))
    return errors
