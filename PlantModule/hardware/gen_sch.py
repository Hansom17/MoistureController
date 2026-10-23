"""Writes carrier.kicad_sch, lib/carrier.kicad_sym and the module footprint from design.py.

Plain python3 is enough, no pcbnew needed. Every pin gets a short wire and a net label, so the
connectivity is exactly the tables in design.py.
"""
import re
import uuid
from pathlib import Path

import design

HERE = Path(__file__).parent
KICAD = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport")
NS = uuid.UUID("3b1c2d3e-0000-4000-8000-00000000c6c6")
ROOT_UUID = str(uuid.uuid5(NS, "root"))


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(parts)))


def sym_uuid(ref):
    return uid("sym", ref)


# --- library handling ---------------------------------------------------------------------------

_lib_cache = {}


def lib_text(path):
    if path not in _lib_cache:
        _lib_cache[path] = Path(path).read_text()
    return _lib_cache[path]


def extract_symbol(path, name):
    """Return the raw text of one top-level symbol of a .kicad_sym file."""
    text = lib_text(path)
    start = text.index(f'\t(symbol "{name}"')
    depth, i = 0, start
    while True:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1


def symbol_pins(block):
    """[(number, x, y, angle)] in library coordinates."""
    pins = []
    for m in re.finditer(r"\(pin\s+\w+\s+\w+\s*\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)", block):
        num = re.search(r'\(number\s+"([^"]+)"', block[m.end():]).group(1)
        pins.append((num, float(m.group(1)), float(m.group(2)), float(m.group(3))))
    return pins


def lib_path(libname):
    if libname == "carrier":
        return HERE / "lib" / "carrier.kicad_sym"
    return KICAD / "symbols" / f"{libname}.kicad_sym"


# --- custom module symbol and footprint ---------------------------------------------------------

PITCH = 2.54


def write_module_symbol():
    rows = len(design.MODULE_LEFT)
    top = (rows - 1) * PITCH / 2
    half_h = top + PITCH
    pins = []
    for i, name in enumerate(design.MODULE_LEFT):
        y = top - i * PITCH
        pins.append(f'\t\t\t(pin passive line (at -12.7 {y:.2f} 0) (length 2.54) '
                    f'(name "{name}" (effects (font (size 1.27 1.27)))) '
                    f'(number "{i + 1}" (effects (font (size 1.27 1.27)))))')
    for i, name in enumerate(design.MODULE_RIGHT):
        y = top - i * PITCH
        pins.append(f'\t\t\t(pin passive line (at 12.7 {y:.2f} 180) (length 2.54) '
                    f'(name "{name}" (effects (font (size 1.27 1.27)))) '
                    f'(number "{rows + i + 1}" (effects (font (size 1.27 1.27)))))')
    prop = lambda k, v, y, hide="": (  # noqa: E731
        f'\t\t(property "{k}" "{v}" (at 0 {y} 0) (effects (font (size 1.27 1.27)){hide}))')
    body = "\n".join([
        '(kicad_symbol_lib',
        '\t(version 20251024)',
        '\t(generator "carrier_gen")',
        '\t(symbol "ESP32-C6-Zero"',
        '\t\t(exclude_from_sim no) (in_bom yes) (on_board yes)',
        prop("Reference", "U", half_h + 2),
        prop("Value", "ESP32-C6-Zero", -half_h - 2),
        prop("Footprint", design.FP_MOD, 0, " hide"),
        prop("Datasheet", "https://docs.waveshare.com/ESP32-C6-Zero", 0, " hide"),
        '\t\t(symbol "ESP32-C6-Zero_0_1"',
        f'\t\t\t(rectangle (start -10.16 {half_h:.2f}) (end 10.16 {-half_h:.2f}) '
        '(stroke (width 0.254) (type default)) (fill (type background)))',
        '\t\t)',
        '\t\t(symbol "ESP32-C6-Zero_1_1"',
        *pins,
        '\t\t)',
        '\t)',
        ')',
    ])
    (HERE / "lib").mkdir(exist_ok=True)
    (HERE / "lib" / "carrier.kicad_sym").write_text(body + "\n")
    _lib_cache.pop(str(lib_path("carrier")), None)


# Module geometry from Waveshare's dimension drawing: 18.00 x 23.50 mm, 9 castellated pads per
# side at 2.54 mm pitch, first pad centre 1.59 mm from the USB-C end.
MOD_W, MOD_L, PAD_FIRST = 18.0, 23.5, 1.59
PAD_LEN, PAD_H = 2.0, 1.4  # carrier pad: 1.2 mm outside the module edge, 0.8 mm under it
PAD_OFFSET = 0.2          # pad centre sits this far outside the module edge


def pad_y(i):
    """y of pad i (0-8) relative to the module centre, USB end up."""
    return -MOD_L / 2 + PAD_FIRST + i * PITCH


def write_module_footprint():
    pads = []
    n = 1
    for side, sign in (("L", -1), ("R", 1)):
        for i in range(9):
            x = sign * (MOD_W / 2 + PAD_OFFSET)
            pads.append(f'\t(pad "{n}" smd rect (at {x:.2f} {pad_y(i):.2f}) (size {PAD_LEN} {PAD_H}) '
                        f'(layers "F.Cu" "F.Mask" "F.Paste"))')
            n += 1
    hw, hl = MOD_W / 2, MOD_L / 2
    cw, cl = hw + 2.0, hl + 1.0
    lines = [
        '(footprint "ESP32-C6-Zero"',
        '\t(version 20260206)',
        '\t(generator "carrier_gen")',
        '\t(layer "F.Cu")',
        '\t(descr "Waveshare ESP32-C6-Zero, castellated, soldered flat onto carrier pads")',
        '\t(attr smd)',
        '\t(property "Reference" "REF**" (at 0 -14 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
        '\t(property "Value" "ESP32-C6-Zero" (at 0 14 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
        f'\t(fp_line (start {-hw} {-hl + 0.4}) (end {-hw} {hl}) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
        f'\t(fp_line (start {hw} {-hl + 0.4}) (end {hw} {hl}) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
        f'\t(fp_line (start {-hw} {hl}) (end {hw} {hl}) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
        f'\t(fp_rect (start {-cw} {-cl}) (end {cw} {cl}) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))',
        f'\t(fp_text user "USB-C" (at 0 {-hl + 2:.2f} 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
        f'\t(fp_text user "no copper under module" (at 0 3 0) (layer "Cmts.User") (effects (font (size 0.8 0.8) (thickness 0.12))))',
        *pads,
        ')',
    ]
    d = HERE / "lib" / "carrier.pretty"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ESP32-C6-Zero.kicad_mod").write_text("\n".join(lines) + "\n")


# --- schematic ----------------------------------------------------------------------------------

GROUP_ORIGIN = {  # group -> (x, y) of the first part, mm on an A3 sheet
    "module": (60, 120), "ports": (150, 40), "i2c": (150, 115), "power": (150, 190),
    "ui": (310, 40), "mech": (310, 190),
}
GROUP_TITLE = {
    "module": "ESP32-C6-Zero (castellated)", "ports": "4x 3-pin ports: 3V3 | SIG | GND",
    "i2c": "2x I2C, shared bus", "power": "power input, source select, battery sense",
    "ui": "button, status LED, UART, spare pin", "mech": "mounting holes",
}


def label_angle(dx, dy):
    return {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[(dx, dy)]


def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def build_schematic():
    lib_syms = {}
    body = []
    group_count = {}
    for p in design.PARTS:
        libname, symname = p["sym"].split(":")
        path = lib_path(libname)
        if p["sym"] not in lib_syms:
            raw = extract_symbol(path, symname)
            raw = raw.replace(f'(symbol "{symname}"', f'(symbol "{p["sym"]}"', 1)
            lib_syms[p["sym"]] = raw
        pins = symbol_pins(extract_symbol(path, symname))

        k = group_count.get(p["group"], 0)
        group_count[p["group"]] = k + 1
        gx, gy = GROUP_ORIGIN[p["group"]]
        if p["group"] == "module":
            x, y = gx, gy
        else:
            per_row = 4 if p["group"] != "mech" else 4
            x = gx + (k % per_row) * 38
            y = gy + (k // per_row) * 34
        x, y = round(x / 1.27) * 1.27, round(y / 1.27) * 1.27

        if p["group"] == "module":
            nets = {str(i + 1): design.MODULE_NETS[n] for i, n in enumerate(design.MODULE_LEFT)}
            nets.update({str(i + 10): design.MODULE_NETS[n] for i, n in enumerate(design.MODULE_RIGHT)})
        else:
            nets = p["pins"]

        bom = "no" if p["sym"].split(":")[1] in ("MountingHole", "TestPoint", "SolderJumper_2_Bridged") else "yes"
        inst_pins = "".join(f'\n\t\t(pin "{num}" (uuid "{uid("pin", p["ref"], num)}"))'
                            for num, *_ in pins)
        body.append(
            f'\t(symbol (lib_id "{p["sym"]}") (at {fmt(x)} {fmt(y)} 0) (unit 1)\n'
            f'\t\t(exclude_from_sim no) (in_bom {bom}) (on_board yes) (dnp no)\n'
            f'\t\t(uuid "{sym_uuid(p["ref"])}")\n'
            f'\t\t(property "Reference" "{p["ref"]}" (at {fmt(x + 2.54)} {fmt(y - 5.08)} 0) '
            f'(effects (font (size 1.27 1.27)) (justify left)))\n'
            f'\t\t(property "Value" "{p["value"]}" (at {fmt(x + 2.54)} {fmt(y - 3.5)} 0) '
            f'(effects (font (size 1.27 1.27)) (justify left)))\n'
            f'\t\t(property "Footprint" "{p["fp"]}" (at {fmt(x)} {fmt(y)} 0) '
            f'(effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'\t\t(property "Datasheet" "" (at {fmt(x)} {fmt(y)} 0) '
            f'(effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'\t\t(property "Description" "{p["desc"]}" (at {fmt(x)} {fmt(y)} 0) '
            f'(effects (font (size 1.27 1.27)) (hide yes)))'
            f'{inst_pins}\n'
            f'\t\t(instances (project "carrier" (path "/{ROOT_UUID}" '
            f'(reference "{p["ref"]}") (unit 1))))\n\t)')

        for num, px, py, ang in pins:
            net = nets.get(num)
            sx, sy = x + px, y - py
            dx, dy = round(-1 * round(__import__("math").cos(__import__("math").radians(ang)))), \
                round(__import__("math").sin(__import__("math").radians(ang)))
            ex, ey = sx + dx * 5.08, sy + dy * 5.08
            if net is None:
                body.append(f'\t(no_connect (at {fmt(sx)} {fmt(sy)}) (uuid "{uid("nc", p["ref"], num)}"))')
                continue
            body.append(
                f'\t(wire (pts (xy {fmt(sx)} {fmt(sy)}) (xy {fmt(ex)} {fmt(ey)})) '
                f'(stroke (width 0) (type default)) (uuid "{uid("w", p["ref"], num)}"))')
            body.append(
                f'\t(global_label "{net}" (shape passive) (at {fmt(ex)} {fmt(ey)} {label_angle(dx, dy)}) '
                f'(effects (font (size 1.27 1.27)) (justify left)) '
                f'(uuid "{uid("l", p["ref"], num)}")\n'
                f'\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {fmt(ex)} {fmt(ey)} 0) '
                f'(effects (font (size 1.27 1.27)) (hide yes))))')

    for g, (gx, gy) in GROUP_ORIGIN.items():
        body.append(f'\t(text "{GROUP_TITLE[g]}" (at {gx - 10} {gy - 22} 0) '
                    f'(effects (font (size 2.5 2.5)) (justify left)) (uuid "{uid("t", g)}"))')

    head = [
        "(kicad_sch",
        "\t(version 20251024)",
        '\t(generator "carrier_gen")',
        '\t(generator_version "1")',
        f'\t(uuid "{ROOT_UUID}")',
        '\t(paper "A3")',
        '\t(title_block (title "Moisture controller carrier") (rev "A") '
        '(comment 1 "Generated by hardware/carrier/generate.py from design.py"))',
        "\t(lib_symbols",
        *["\t" + s.replace("\n", "\n\t") for s in lib_syms.values()],
        "\t)",
    ]
    tail = ['\t(sheet_instances (path "/" (page "1")))', ")"]
    (HERE / "carrier.kicad_sch").write_text("\n".join(head + body + tail) + "\n")


if __name__ == "__main__":
    write_module_symbol()
    write_module_footprint()
    build_schematic()
    print("wrote carrier.kicad_sch, lib/carrier.kicad_sym, lib/carrier.pretty")
