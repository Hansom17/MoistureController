"""Builds carrier.kicad_pcb from design.py. Run with KiCad's bundled python:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 gen_pcb.py

Places the parts, draws the outline, adds GND pours and a keepout under the module, then routes
the signal and power nets with a small grid router (router.py). GND is left to the pours.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/"
                   "Versions/Current/lib/python3.9/site-packages")
import pcbnew  # noqa: E402

import design  # noqa: E402
import gen_sch  # noqa: E402
import router  # noqa: E402

HERE = Path(__file__).parent
KICAD_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

BOARD_W, BOARD_H = 70.0, 58.0
MOD_X, MOD_Y = 35.0, 11.8  # module centre; the USB-C end sits flush with the top edge

# ref -> (x, y, rotation). Connectors: x,y is pin 1.
PLACE = {
    "U1": (MOD_X, MOD_Y, 0),
    # power block, left
    "J7": (3, 5.5, 0), "JP1": (4, 13, 0), "J8": (10, 13, 0), "JP4": (13.5, 19.5, 0),
    "D1": (17, 14, 0), "C9": (17, 2.6, 0), "C10": (17, 6.6, 0),
    "R3": (5, 23, 90), "R4": (9, 23, 90), "C7": (13, 23, 90), "TP1": (20, 9.5, 0),
    # right side: I2C pull-ups, LED, button, UART
    "R1": (51, 5.5, 0), "JP2": (55, 5.5, 0), "R2": (51, 10, 0), "JP3": (55, 10.5, 0),
    "R6": (50.5, 15.5, 0), "D2": (56, 15.5, 0),
    "SW1": (53, 20, 0), "R5": (59, 17.5, 0), "C8": (59, 21, 0),
    "J9": (65, 4.5, 0),
    # ports row
    "J1": (6, 34, 0), "J2": (21, 34, 0), "J3": (36, 34, 0), "J4": (51, 34, 0),
    "C1": (8.5, 29, 0), "C2": (23.5, 29, 0), "C3": (38.5, 29, 0), "C4": (53.5, 29, 0),
    # I2C row
    "J5": (6, 46, 0), "J6": (26, 46, 0),
    # mounting holes
    "H1": (3.5, 54.5, 0), "H2": (66.5, 54.5, 0), "H3": (66.5, 27, 0), "H4": (33, 54.5, 0),
}


def mm(v):
    return pcbnew.FromMM(v)


def vec(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def load_fp(spec):
    lib, name = spec.split(":")
    if lib == "carrier":
        libdir = HERE / "lib" / "carrier.pretty"
    else:
        libdir = KICAD_FP / f"{lib}.pretty"
    fp = pcbnew.FootprintLoad(str(libdir), name)
    if fp is None:
        raise SystemExit(f"footprint not found: {spec}")
    return fp


def main():
    board = pcbnew.BOARD()
    nets = {}

    def net(name):
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    for p in design.PARTS:
        fp = load_fp(p["fp"])
        lib, fpname = p["fp"].split(":")
        fp.SetFPID(pcbnew.LIB_ID(lib, fpname))
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        fp.GetField("Description").SetText(p["desc"])
        x, y, rot = PLACE[p["ref"]]
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(rot)
        fp.SetPath(pcbnew.KIID_PATH(f"/{gen_sch.sym_uuid(p['ref'])}"))
        if p["group"] == "module":
            pin_nets = {str(i + 1): design.MODULE_NETS[n]
                        for i, n in enumerate(design.MODULE_LEFT)}
            pin_nets.update({str(i + 10): design.MODULE_NETS[n]
                             for i, n in enumerate(design.MODULE_RIGHT)})
        else:
            pin_nets = p["pins"]
        for pad in fp.Pads():
            name = pin_nets.get(pad.GetNumber())
            if name:
                pad.SetNet(net(name))
            elif p["group"] == "module":
                # pads left open on purpose: name the net as KiCad does for no-connect pins
                num = int(pad.GetNumber())
                pin = (design.MODULE_LEFT + design.MODULE_RIGHT)[num - 1]
                pad.SetNet(net(f"unconnected-(U1-{pin}-Pad{num})"))
        board.Add(fp)

    # Outline
    for (x1, y1, x2, y2) in [(0, 0, BOARD_W, 0), (BOARD_W, 0, BOARD_W, BOARD_H),
                             (BOARD_W, BOARD_H, 0, BOARD_H), (0, BOARD_H, 0, 0)]:
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(vec(x1, y1))
        seg.SetEnd(vec(x2, y2))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)

    # Keepout under the module body: no copper, so the ceramic antenna and the module's bottom
    # pads stay clear. Pads on the carrier are not affected by a rule area.
    ko = pcbnew.ZONE(board)
    ko.SetIsRuleArea(True)
    ko.SetDoNotAllowZoneFills(True)
    ko.SetDoNotAllowTracks(True)
    ko.SetDoNotAllowVias(True)
    ko.SetDoNotAllowPads(False)
    ko.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    ko.SetLayerSet(ls)
    KO = (MOD_X - 8.6, MOD_Y - 11.75 - 1.0, MOD_X + 8.6, MOD_Y + 11.75)
    ol = ko.Outline()
    ol.NewOutline()
    for (x, y) in [(KO[0], KO[1]), (KO[2], KO[1]), (KO[2], KO[3]), (KO[0], KO[3])]:
        ol.Append(mm(x), mm(y))
    board.Add(ko)

    # Route signals and power, GND stays with the pours.
    router.route_board(board, KO, BOARD_W, BOARD_H)

    # GND pours on both layers
    gnd = net("GND")
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetMinThickness(mm(0.2))
        o = z.Outline()
        o.NewOutline()
        for (x, y) in [(0.3, 0.3), (BOARD_W - 0.3, 0.3), (BOARD_W - 0.3, BOARD_H - 0.3),
                       (0.3, BOARD_H - 0.3)]:
            o.Append(mm(x), mm(y))
        board.Add(z)
    # zones are filled by KiCad on open or by kicad-cli drc --refill-zones

    out = HERE / "carrier.kicad_pcb"
    board.Save(str(out))
    print("wrote", out)


if __name__ == "__main__":
    main()
