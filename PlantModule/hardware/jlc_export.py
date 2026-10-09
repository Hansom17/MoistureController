"""Exports the JLCPCB order files from the current KiCad project into jlcpcb/.

  python3 jlc_export.py

Gerbers + drill (zipped), BOM with LCSC part numbers, and the component placement list (CPL)
for the SMD parts. Reads carrier.kicad_pcb / carrier.kicad_sch as they are on disk, so it
includes any edits made in KiCad. Close KiCad (or save) first.
"""
import csv
import re
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "jlcpcb"
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

# Schematic value -> LCSC part number (checked on lcsc.com / jlcpcb.com, 2026-10-02).
LCSC = {
    "100nF": ("C14663", "Yageo CC0603KRX7R9BB104, 0603 X7R 50V (JLCPCB Basic)"),
    "10uF": ("C15850", "Samsung CL21A106KAYNNNE, 0805 X5R 25V"),
    "B5819W": ("C82544", "Diodes 1N5819HW-7-F, SOD-123 Schottky 40V 1A"),
    "1N5819HW": ("C82544", "Diodes 1N5819HW-7-F, SOD-123 Schottky 40V 1A"),
    "STATUS": ("C2286", "Hubei KENTO KT-0603R, red 0603"),
    "LED_red": ("C2286", "Hubei KENTO KT-0603R, red 0603"),
    "4.7k": ("C23162", "UNI-ROYAL 0603WAF4701T5E"),
    "330k": ("C23137", "UNI-ROYAL 0603WAF3303T5E"),
    "10k": ("C25804", "UNI-ROYAL 0603WAF1002T5E"),
    "1k": ("C21190", "UNI-ROYAL 0603WAF1001T5E"),
    "USER": ("C221675", "C&K KMR211GLFS, SMD tactile switch"),
}
# Through-hole parts: not part of the SMT run, listed separately.
THT = {
    "JST_XH_B3B-XH-A": ("C144394", "JST B3B-XH-A(LF)(SN), 3-pin 2.5 mm"),
    "JST_XH_B4B-XH-A": ("C144395", "JST B4B-XH-A(LF)(SN), 4-pin 2.5 mm"),
}
SKIP_PLACE = ("U1", "H", "TP", "JP", "J")  # module (hand), holes, test point, jumpers, headers


def expand(refs):
    """'C1-C4,C7' -> ['C1','C2','C3','C4','C7'] (JLCPCB does not read ranges)."""
    out = []
    for part in refs.split(","):
        m = re.match(r"([A-Za-z]+)(\d+)-([A-Za-z]+)(\d+)$", part)
        if m:
            out += [f"{m[1]}{i}" for i in range(int(m[2]), int(m[4]) + 1)]
        else:
            out.append(part)
    return out


def run(*args):
    subprocess.run([CLI, *args], check=True, capture_output=True)


def main():
    OUT.mkdir(exist_ok=True)
    gdir = OUT / "gerber"
    gdir.mkdir(exist_ok=True)
    pcb = str(HERE / "carrier.kicad_pcb")

    run("pcb", "export", "gerbers", "--output", str(gdir), "--layers",
        "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts",
        "--subtract-soldermask", pcb)
    run("pcb", "export", "drill", "--output", str(gdir) + "/", "--format", "excellon",
        "--excellon-units", "mm", "--generate-map", "--map-format", "gerberx2", pcb)
    with zipfile.ZipFile(OUT / "carrier_gerber.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gdir.iterdir()):
            z.write(f, f.name)

    # BOM from the schematic, grouped by value + footprint
    tmp = OUT / "_bom.csv"
    run("sch", "export", "bom", "--fields", "Reference,Value,Footprint", "--labels",
        "Refs,Value,Footprint", "--group-by", "Value,Footprint", "--exclude-dnp",
        "--output", str(tmp), str(HERE / "carrier.kicad_sch"))
    rows = list(csv.DictReader(open(tmp)))
    tmp.unlink()
    smt, tht, hand = [], [], []
    for r in rows:
        refs = ",".join(expand(r["Refs"].replace(" ", "")))
        value, fp = r["Value"], r["Footprint"].split(":")[-1]
        first = refs.split(",")[0].split("-")[0]
        if value in LCSC and not first.startswith(("J", "U", "H")):
            smt.append((value, refs, fp, *LCSC[value]))
            continue
        key = next((k for k in THT if fp.startswith(k)), None)
        if key:
            tht.append((value, refs, fp, *THT[key]))
        else:
            hand.append((value, refs, fp))

    with open(OUT / "bom_jlcpcb.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "JLCPCB Part #"])
        for value, refs, fp, lcsc, _ in smt:
            w.writerow([value, refs, fp, lcsc])
    with open(OUT / "parts_overview.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Where", "Value", "Designators", "Footprint", "LCSC", "Part"])
        for value, refs, fp, lcsc, name in smt:
            w.writerow(["JLCPCB SMT", value, refs, fp, lcsc, name])
        for value, refs, fp, lcsc, name in tht:
            w.writerow(["through-hole (check JLCPCB quote, else order at LCSC)", value, refs, fp,
                        lcsc, name])
        for value, refs, fp in hand:
            w.writerow(["hand / other shop", value, refs, fp, "", ""])

    # Placement list for the SMT parts
    smt_refs = set()
    for _, refs, *_ in smt:
        smt_refs |= set(refs.split(","))
    pos = OUT / "_pos.csv"
    run("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "front",
        "--smd-only", "--output", str(pos), pcb)
    with open(pos) as src, open(OUT / "cpl_jlcpcb.csv", "w", newline="") as dst:
        w = csv.writer(dst)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in csv.DictReader(src):
            if r["Ref"] in smt_refs:
                w.writerow([r["Ref"], f'{float(r["PosX"]):.4f}mm', f'{float(r["PosY"]):.4f}mm',
                            "Top", f'{float(r["Rot"]):.0f}'])
    pos.unlink()
    print(f"SMT lines: {len(smt)}, placed parts: {len(smt_refs)}, THT lines: {len(tht)}, "
          f"other: {len(hand)}")
    print("files in", OUT)


if __name__ == "__main__":
    main()
