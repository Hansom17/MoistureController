"""Single source of truth for the carrier board: parts, nets and the C6 pin map.

generate.py turns this into the KiCad schematic and PCB. Edit here, regenerate, never hand-edit
the generated files for connectivity.
"""

# ESP32-C6-Zero pads, top (USB-C end) to bottom. Pad numbers 1-9 are the left edge, 10-18 right.
MODULE_LEFT = ["5V", "GND", "3V3", "IO0", "IO1", "IO2", "IO3", "IO4", "IO5"]
MODULE_RIGHT = ["TX", "RX", "IO14", "IO15", "IO18", "IO19", "IO20", "IO21", "IO22"]

# Module pad name -> net. None = not connected (the pad is still soldered for strength).
MODULE_NETS = {
    "5V": "+5V", "GND": "GND", "3V3": "+3V3",
    "IO0": "IO0",        # spare, test pad
    "IO1": "SENS1", "IO2": "SENS2", "IO3": "SENS3", "IO4": "SENS4",
    "IO5": "VSENSE",     # battery divider (ADC1)
    "TX": "TXD", "RX": "RXD",
    "IO14": None, "IO15": None,   # IO15 is a strapping pin: keep it free
    "IO18": "SDA", "IO19": "SCL",
    "IO20": "LED_DRV",
    "IO21": "BTN",
    "IO22": None,
}

FP_XH3 = "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"
FP_XH4 = "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical"
FP_HDR3 = "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"
FP_HDR2 = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
FP_R = "Resistor_SMD:R_0603_1608Metric"
FP_C = "Capacitor_SMD:C_0603_1608Metric"
FP_C10U = "Capacitor_SMD:C_0805_2012Metric"
FP_SJ = "Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm"
FP_MOD = "carrier:ESP32-C6-Zero"


def part(ref, sym, value, fp, pins, group, desc=""):
    return {"ref": ref, "sym": sym, "value": value, "fp": fp, "pins": pins, "group": group,
            "desc": desc}


PARTS = []

# Module
PARTS.append(part("U1", "carrier:ESP32-C6-Zero", "ESP32-C6-Zero", FP_MOD, {}, "module",
                  "Waveshare ESP32-C6-Zero, castellated, USB-C end overhangs the board edge"))

# 4x 3-pin ports (sensor or pump signal): 1 = 3V3, 2 = SIG, 3 = GND
for n in range(1, 5):
    PARTS.append(part(f"J{n}", "Connector:Conn_01x03_Pin", f"PORT{n}", FP_XH3,
                      {"1": "+3V3", "2": f"SENS{n}", "3": "GND"}, "ports",
                      "3V3 | SIG | GND (sensor, or pump driver SIG+GND only)"))
    PARTS.append(part(f"C{n}", "Device:C", "100nF", FP_C, {"1": f"SENS{n}", "2": "GND"}, "ports",
                      "ADC filter, DNP if the sensor has its own"))

# 2x I2C on the same bus: 1 = 3V3, 2 = GND, 3 = SDA, 4 = SCL
for n in (5, 6):
    PARTS.append(part(f"J{n}", "Connector:Conn_01x04_Pin", f"I2C{n - 4}", FP_XH4,
                      {"1": "+3V3", "2": "GND", "3": "SDA", "4": "SCL"}, "i2c",
                      "3V3 | GND | SDA | SCL, both ports share one bus"))
PARTS += [
    part("R1", "Device:R", "4.7k", FP_R, {"1": "+3V3", "2": "PU_SDA"}, "i2c", "SDA pull-up"),
    part("JP2", "Jumper:SolderJumper_2_Bridged", "PU_SDA", FP_SJ, {"1": "PU_SDA", "2": "SDA"},
         "i2c", "cut to remove the SDA pull-up"),
    part("R2", "Device:R", "4.7k", FP_R, {"1": "+3V3", "2": "PU_SCL"}, "i2c", "SCL pull-up"),
    part("JP3", "Jumper:SolderJumper_2_Bridged", "PU_SCL", FP_SJ, {"1": "PU_SCL", "2": "SCL"},
         "i2c", "cut to remove the SCL pull-up"),
]

# Power: J7 -> JP1 source select -> optional switch -> D1 -> module 5V pad
PARTS += [
    part("J7", "Connector:Conn_01x03_Pin", "POWER", FP_XH3,
         {"1": "VIN", "2": "GND", "3": "VBAT"}, "power",
         "VIN = 5V from a charger/boost board, VBAT = raw cell (sense, or direct supply)"),
    part("JP1", "Connector:Conn_01x03_Pin", "SRC_SEL", FP_HDR3,
         {"1": "VIN", "2": "COM", "3": "VBAT"}, "power",
         "shunt 1-2: supply from VIN (5V). shunt 2-3: supply from the raw cell"),
    part("JP4", "Jumper:SolderJumper_2_Bridged", "PWR_SW", FP_SJ, {"1": "COM", "2": "PWR_IN"},
         "power", "cut when a power switch is wired to J8"),
    part("J8", "Connector:Conn_01x02_Pin", "SWITCH", FP_HDR2, {"1": "COM", "2": "PWR_IN"},
         "power", "optional power switch"),
    part("D1", "Device:D_Schottky", "B5819W", "Diode_SMD:D_SOD-123", {"1": "+5V", "2": "PWR_IN"},
         "power", "reverse-polarity and USB back-feed protection"),
    part("C9", "Device:C", "10uF", FP_C10U, {"1": "+5V", "2": "GND"}, "power", "5V bulk"),
    part("C10", "Device:C", "10uF", FP_C10U, {"1": "+3V3", "2": "GND"}, "power", "3V3 bulk"),
    part("R3", "Device:R", "330k", FP_R, {"1": "VBAT", "2": "VSENSE"}, "power",
         "battery divider top (firmware divider = 200%)"),
    part("R4", "Device:R", "330k", FP_R, {"1": "VSENSE", "2": "GND"}, "power",
         "battery divider bottom"),
    part("C7", "Device:C", "100nF", FP_C, {"1": "VSENSE", "2": "GND"}, "power",
         "ADC sample-and-hold buffer"),
]

# User interface
PARTS += [
    part("SW1", "Switch:SW_Push", "USER", "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2",
         {"1": "BTN", "2": "GND"}, "ui", "user button, not the BOOT line"),
    part("R5", "Device:R", "10k", FP_R, {"1": "+3V3", "2": "BTN"}, "ui", "button pull-up"),
    part("C8", "Device:C", "100nF", FP_C, {"1": "BTN", "2": "GND"}, "ui", "debounce"),
    part("R6", "Device:R", "1k", FP_R, {"1": "LED_DRV", "2": "LED_A"}, "ui", "LED resistor"),
    part("D2", "Device:LED", "STATUS", "LED_SMD:LED_0603_1608Metric",
         {"1": "GND", "2": "LED_A"}, "ui", "status LED, active high"),
    part("J9", "Connector:Conn_01x03_Pin", "UART", FP_HDR3,
         {"1": "GND", "2": "TXD", "3": "RXD"}, "ui", "optional UART0"),
    part("TP1", "Connector:TestPoint", "IO0", "TestPoint:TestPoint_Pad_D1.5mm", {"1": "IO0"}, "ui",
         "spare GPIO0 (low-power pin)"),
]

for n in range(1, 5):
    PARTS.append(part(f"H{n}", "Mechanical:MountingHole", "M3", "MountingHole:MountingHole_3.2mm_M3",
                      {}, "mech"))
