"""Small two-layer grid router for the carrier board (A*, 0.25 mm grid, 8 directions).

Routes every net except GND with tracks and vias. GND pads get a short stitch via to the pour
on the other layer. Anything that cannot be routed is reported and left as a ratsnest line for
the user to finish in KiCad.
"""
import heapq
import math

import pcbnew

G = 0.25            # grid, mm
CLR = 0.25          # routing clearance, a little above the 0.2 mm DRC rule
EDGE = 0.4          # keep tracks this far from the board edge
VIA_D, VIA_DRILL = 0.8, 0.4
POWER = {"+3V3", "+5V", "VIN", "VBAT", "COM", "PWR_IN"}
W_SIG, W_PWR = 0.25, 0.4
VIA_COST = 12.0


def to_mm(v):
    return pcbnew.ToMM(v)


class Obstacle:
    """Copper that other nets must keep away from. kind: rect | seg | circle."""

    def __init__(self, kind, geom, net, layers, hw=0.0):
        self.kind, self.geom, self.net, self.layers, self.hw = kind, geom, net, layers, hw


class Grid:
    def __init__(self, w, h):
        self.nx, self.ny = int(w / G) + 1, int(h / G) + 1

    def idx(self, i, j):
        return j * self.nx + i

    def cell(self, x, y):
        return round(x / G), round(y / G)


def pad_rect(pad):
    bb = pad.GetBoundingBox()
    return (to_mm(bb.GetLeft()), to_mm(bb.GetTop()), to_mm(bb.GetRight()), to_mm(bb.GetBottom()))


def pad_layers(pad):
    return (0, 1) if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH) else (0,)


class Router:
    def __init__(self, board, keepout, w, h):
        self.board, self.w, self.h, self.keepout = board, w, h, keepout
        self.grid = Grid(w, h)
        self.obs = []
        self.nets = {}      # name -> list of (pad, rect, layers)
        self.tracks = []    # (layer, x1, y1, x2, y2, width, netname)
        self.vias = []      # (x, y, netname)
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                name = pad.GetNetname()
                rect = pad_rect(pad)
                layers = pad_layers(pad)
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    self.obs.append(Obstacle("rect", rect, None, layers))
                elif name:
                    self.obs.append(Obstacle("rect", rect, name, layers))
                    self.nets.setdefault(name, []).append((pad, rect, layers))
                else:
                    self.obs.append(Obstacle("rect", rect, "", layers))  # unconnected pad
            # mounting holes: footprints with no pads
            if not list(fp.Pads()):
                c = fp.GetPosition()
                self.obs.append(Obstacle("circle", (to_mm(c.x), to_mm(c.y), 3.2), None, (0, 1)))

    # --- occupancy -------------------------------------------------------------------------

    def build_blocked(self, net, hw):
        """Per layer bytearray: 1 = this net's track centre may not be here."""
        g = self.grid
        blocked = [bytearray(g.nx * g.ny) for _ in range(2)]
        margin = CLR + hw

        def mark_rect(layer, x1, y1, x2, y2):
            i1, i2 = max(0, int(x1 / G)), min(g.nx - 1, int(x2 / G) + 1)
            j1, j2 = max(0, int(y1 / G)), min(g.ny - 1, int(y2 / G) + 1)
            arr = blocked[layer]
            for j in range(j1, j2 + 1):
                cy = j * G
                if cy < y1 or cy > y2:
                    continue
                for i in range(i1, i2 + 1):
                    cx = i * G
                    if x1 <= cx <= x2:
                        arr[j * g.nx + i] = 1

        # board edge
        for layer in (0, 1):
            arr = blocked[layer]
            for j in range(g.ny):
                for i in range(g.nx):
                    x, y = i * G, j * G
                    if x < EDGE + hw or x > self.w - EDGE - hw or y < EDGE + hw \
                            or y > self.h - EDGE - hw:
                        arr[j * g.nx + i] = 1
        kx1, ky1, kx2, ky2 = self.keepout
        for layer in (0, 1):
            mark_rect(layer, kx1 - hw, ky1 - hw, kx2 + hw, ky2 + hw)

        for o in self.obs:
            if o.net == net and net:
                continue
            for layer in o.layers:
                if o.kind == "rect":
                    x1, y1, x2, y2 = o.geom
                    mark_rect(layer, x1 - margin, y1 - margin, x2 + margin, y2 + margin)
                elif o.kind == "circle":
                    cx, cy, r = o.geom
                    mark_rect(layer, cx - r - margin, cy - r - margin, cx + r + margin,
                              cy + r + margin)
                elif o.kind == "seg" and o.layers == (layer,):
                    x1, y1, x2, y2 = o.geom
                    r = o.hw + margin
                    self._mark_seg(blocked[layer], x1, y1, x2, y2, r)
        return blocked

    def _mark_seg(self, arr, x1, y1, x2, y2, r):
        g = self.grid
        i1, i2 = max(0, int((min(x1, x2) - r) / G)), min(g.nx - 1, int((max(x1, x2) + r) / G) + 1)
        j1, j2 = max(0, int((min(y1, y2) - r) / G)), min(g.ny - 1, int((max(y1, y2) + r) / G) + 1)
        dx, dy = x2 - x1, y2 - y1
        ll = dx * dx + dy * dy
        for j in range(j1, j2 + 1):
            for i in range(i1, i2 + 1):
                px, py = i * G, j * G
                t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / ll))
                if math.hypot(px - (x1 + t * dx), py - (y1 + t * dy)) < r:
                    arr[j * g.nx + i] = 1

    # --- search ----------------------------------------------------------------------------

    def astar(self, blocked, sources, targets, via_ok):
        g = self.grid
        nx = g.nx
        tset = set(targets)
        tl = list(targets)

        def h(n):
            layer, i, j = n
            best = 1e9
            for (_, ti, tj) in tl:
                dx, dy = abs(i - ti), abs(j - tj)
                best = min(best, (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy))
            return best

        openq, came, cost = [], {}, {}
        for s in sources:
            cost[s] = 0.0
            heapq.heappush(openq, (h(s), 0.0, s))
        dirs = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
        while openq:
            _, c, n = heapq.heappop(openq)
            if c > cost.get(n, 1e18):
                continue
            if n in tset:
                path = [n]
                while n in came:
                    n = came[n]
                    path.append(n)
                return path[::-1]
            layer, i, j = n
            for dx, dy, dc in dirs:
                ni, nj = i + dx, j + dy
                if not (0 <= ni < nx and 0 <= nj < g.ny) or blocked[layer][nj * nx + ni]:
                    continue
                if dx and dy and (blocked[layer][j * nx + ni] or blocked[layer][nj * nx + i]):
                    continue
                m = (layer, ni, nj)
                nc = c + dc
                if nc < cost.get(m, 1e18):
                    cost[m], came[m] = nc, n
                    heapq.heappush(openq, (nc + h(m), nc, m))
            o = 1 - layer
            if not blocked[o][j * nx + i] and via_ok(blocked, i, j):
                m = (o, i, j)
                nc = c + VIA_COST
                if nc < cost.get(m, 1e18):
                    cost[m], came[m] = nc, n
                    heapq.heappush(openq, (nc + h(m), nc, m))
        return None

    def via_ok(self, blocked, i, j):
        nx = self.grid.nx
        for layer in (0, 1):
            for di, dj in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                ii, jj = i + di, j + dj
                if not (0 <= ii < nx and 0 <= jj < self.grid.ny) or blocked[layer][jj * nx + ii]:
                    return False
        return True

    # --- routing ---------------------------------------------------------------------------

    def pad_cells(self, blocked, rect, layers):
        x1, y1, x2, y2 = rect
        sh = min(0.3, 0.2 * min(x2 - x1, y2 - y1))
        x1, y1, x2, y2 = x1 + sh, y1 + sh, x2 - sh, y2 - sh
        g = self.grid
        out = []
        for layer in layers:
            for j in range(int(y1 / G), int(y2 / G) + 2):
                for i in range(int(x1 / G), int(x2 / G) + 2):
                    if x1 <= i * G <= x2 and y1 <= j * G <= y2 and 0 <= i < g.nx and 0 <= j < g.ny \
                            and not blocked[layer][j * g.nx + i]:
                        out.append((layer, i, j))
        return out

    def commit(self, net, hw, path):
        """Turn a cell path into tracks/vias and register them as obstacles."""
        segs = []
        for a, b in zip(path, path[1:]):
            if a[0] != b[0]:
                x, y = a[1] * G, a[2] * G
                self.vias.append((x, y, net))
                self.obs.append(Obstacle("circle", (x, y, VIA_D / 2), net, (0, 1)))
            else:
                segs.append((a[0], a[1], a[2], b[1], b[2]))
        # merge collinear steps
        merged = []
        for s in segs:
            if merged and merged[-1][0] == s[0]:
                l, x1, y1, x2, y2 = merged[-1]
                if (x2 - x1) * (s[4] - y2) == (y2 - y1) * (s[3] - x2) and (x2, y2) == (s[1], s[2]) \
                        and ((x2 - x1) * (s[3] - s[1]) + (y2 - y1) * (s[4] - s[2])) > 0:
                    merged[-1] = (l, x1, y1, s[3], s[4])
                    continue
            merged.append(s)
        for (layer, i1, j1, i2, j2) in merged:
            self.tracks.append((layer, i1 * G, j1 * G, i2 * G, j2 * G, hw * 2, net))
            self.obs.append(Obstacle("seg", (i1 * G, j1 * G, i2 * G, j2 * G), net, (layer,), hw))
        for node in (path[0], path[-1]):
            self._to_pad_centre(net, hw, node)

    def _to_pad_centre(self, net, hw, node):
        layer, i, j = node
        x, y = i * G, j * G
        for pad, rect, layers in self.nets.get(net, []):
            if layer in layers and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                c = pad.GetPosition()
                cx, cy = to_mm(c.x), to_mm(c.y)
                if math.hypot(cx - x, cy - y) > 0.01:
                    self.tracks.append((layer, x, y, cx, cy, hw * 2, net))
                    self.obs.append(Obstacle("seg", (x, y, cx, cy), net, (layer,), hw))
                return

    def route_net(self, name):
        hw = (W_PWR if name in POWER else W_SIG) / 2
        pads = self.nets[name]
        blocked = self.build_blocked(name, hw)
        terms = []
        for pad, rect, layers in pads:
            cells = self.pad_cells(blocked, rect, layers)
            terms.append((rect, cells))
        terms = [t for t in terms if t[1]]
        if len(terms) < 2:
            return len(pads) - 1 if len(pads) > 1 else 0
        centre = lambda r: ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)  # noqa: E731
        connected = [terms[0]]
        rest = terms[1:]
        sources = set(terms[0][1])
        failed = 0
        while rest:
            def dist(t):
                cx, cy = centre(t[0])
                return min(math.hypot(cx - centre(c[0])[0], cy - centre(c[0])[1]) for c in connected)
            rest.sort(key=dist)
            t = rest.pop(0)
            path = self.astar(blocked, sources, t[1], self.via_ok)
            if path is None:
                failed += 1
                continue
            self.commit(name, hw, path)
            sources |= set(path)
            sources |= set(t[1])
            connected.append(t)
            blocked = self.build_blocked(name, hw)
        return failed

    def stitch_gnd(self):
        """Give every SMD GND pad a via to the pour on the back layer."""
        hw = W_SIG / 2
        count = failed = 0
        for pad, rect, layers in self.nets.get("GND", []):
            if len(layers) == 2:
                continue
            blocked = self.build_blocked("GND", hw)
            src = self.pad_cells(blocked, rect, layers)
            if not src:
                failed += 1
                continue
            g = self.grid
            targets = [(1, i, j) for j in range(g.ny) for i in range(g.nx)
                       if not blocked[1][j * g.nx + i] and self.via_ok(blocked, i, j)]
            # keep the target set local: only cells near the pad
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            targets = [t for t in targets if math.hypot(t[1] * G - cx, t[2] * G - cy) < 4.0]
            path = self.astar(blocked, set(src), targets, self.via_ok) if targets else None
            if path is None:
                failed += 1
                continue
            self.commit("GND", hw, path)
            count += 1
        return count, failed

    def emit(self):
        layer_id = (pcbnew.F_Cu, pcbnew.B_Cu)
        nets = {n.GetNetname(): n for n in self.board.GetNetInfo().NetsByNetcode().values()}
        for (layer, x1, y1, x2, y2, w, net) in self.tracks:
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
            t.SetWidth(pcbnew.FromMM(w))
            t.SetLayer(layer_id[layer])
            t.SetNet(nets[net])
            self.board.Add(t)
        for (x, y, net) in self.vias:
            v = pcbnew.PCB_VIA(self.board)
            v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetWidth(pcbnew.FromMM(VIA_D))
            v.SetDrill(pcbnew.FromMM(VIA_DRILL))
            v.SetNet(nets[net])
            self.board.Add(v)


def route_board(board, keepout, w, h):
    r = Router(board, keepout, w, h)
    names = [n for n in r.nets if n != "GND"]
    # power first, then the rest by pad count (small, local nets first within each class)
    names.sort(key=lambda n: (n not in POWER, len(r.nets[n])))
    unrouted = {}
    for n in names:
        f = r.route_net(n)
        if f:
            unrouted[n] = f
    stitched, gfail = r.stitch_gnd()
    r.emit()
    print(f"routed: {len(r.tracks)} track segments, {len(r.vias)} vias, "
          f"GND stitch vias {stitched}")
    if unrouted or gfail:
        print("UNROUTED connections:", unrouted, "GND stitch failures:", gfail)
