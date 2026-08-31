"""Разбор лампов карты DOOM: вершины, линии, стороны, секторы, сегменты, BSP, вещи."""
import math
import struct

MAP_LUMPS = ('THINGS', 'LINEDEFS', 'SIDEDEFS', 'VERTEXES', 'SEGS',
             'SSECTORS', 'NODES', 'SECTORS', 'REJECT', 'BLOCKMAP')

# флаги линий
ML_BLOCKING = 0x0001
ML_BLOCKMONSTERS = 0x0002
ML_TWOSIDED = 0x0004
ML_DONTPEGTOP = 0x0008
ML_DONTPEGBOTTOM = 0x0010
ML_SECRET = 0x0020
ML_SOUNDBLOCK = 0x0040
ML_DONTDRAW = 0x0080
ML_MAPPED = 0x0100

NO_SIDE = 0xFFFF


class Sector:
    __slots__ = ('floor', 'ceil', 'floorpic', 'ceilpic', 'light', 'special',
                 'tag', 'lines', 'index', 'base_floor', 'base_ceil')

    def __init__(self, i, f, c, fp, cp, l, sp, tag):
        self.index = i
        self.floor = float(f)
        self.ceil = float(c)
        self.base_floor = float(f)
        self.base_ceil = float(c)
        self.floorpic = fp
        self.ceilpic = cp
        self.light = l
        self.special = sp
        self.tag = tag
        self.lines = []


class Side:
    __slots__ = ('xoff', 'yoff', 'upper', 'lower', 'middle', 'sector')

    def __init__(self, xo, yo, up, lo, mid, sec):
        self.xoff = float(xo)
        self.yoff = float(yo)
        self.upper = up
        self.lower = lo
        self.middle = mid
        self.sector = sec


class Line:
    __slots__ = ('v1', 'v2', 'flags', 'special', 'tag', 'right', 'left',
                 'dx', 'dy', 'front', 'back', 'index')

    def __init__(self, i, v1, v2, flags, special, tag, right, left):
        self.index = i
        self.v1 = v1
        self.v2 = v2
        self.flags = flags
        self.special = special
        self.tag = tag
        self.right = right
        self.left = left
        self.dx = v2[0] - v1[0]
        self.dy = v2[1] - v1[1]
        self.front = None
        self.back = None

    @property
    def two_sided(self):
        return self.left != NO_SIDE and self.back is not None


class Seg:
    __slots__ = ('v1', 'v2', 'angle', 'line', 'side', 'offset', 'length')

    def __init__(self, v1, v2, angle, line, side, offset):
        self.v1 = v1
        self.v2 = v2
        self.angle = angle
        self.line = line
        self.side = side
        self.offset = float(offset)
        self.length = math.hypot(v2[0] - v1[0], v2[1] - v1[1])


class SubSector:
    __slots__ = ('first', 'count', 'sector')

    def __init__(self, first, count, sector):
        self.first = first
        self.count = count
        self.sector = sector


class Node:
    __slots__ = ('x', 'y', 'dx', 'dy', 'bbox', 'child')

    def __init__(self, x, y, dx, dy, bbox, child):
        self.x = float(x)
        self.y = float(y)
        self.dx = float(dx)
        self.dy = float(dy)
        self.bbox = bbox            # [ (top,bottom,left,right), ... ] для 0 и 1
        self.child = child          # (right, left), бит 0x8000 = подсектор


class Thing:
    __slots__ = ('x', 'y', 'angle', 'type', 'flags')

    def __init__(self, x, y, a, t, f):
        self.x = float(x)
        self.y = float(y)
        self.angle = math.radians(a)
        self.type = t
        self.flags = f


class MapData:
    def __init__(self, wad, name):
        i = wad.find(name)
        if i < 0:
            raise KeyError('нет карты %s' % name)
        self.name = name
        lumps = {}
        for l in wad.lumps[i + 1:i + 12]:
            if l.name in MAP_LUMPS:
                lumps[l.name] = l
            elif l.name not in MAP_LUMPS:
                break
        self._parse(wad, lumps)

    def _parse(self, wad, L):
        # вершины
        d = wad.read(L['VERTEXES'])
        self.vertexes = [(float(x), float(y)) for x, y in struct.iter_unpack('<hh', d)]

        # секторы
        d = wad.read(L['SECTORS'])
        self.sectors = []
        for i, (fh, ch, fp, cp, lt, sp, tg) in enumerate(struct.iter_unpack('<hh8s8shHH', d)):
            self.sectors.append(Sector(
                i, fh, ch,
                fp.rstrip(b'\x00').decode('ascii', 'replace').upper(),
                cp.rstrip(b'\x00').decode('ascii', 'replace').upper(),
                lt, sp, tg))

        # стороны
        d = wad.read(L['SIDEDEFS'])
        self.sides = []
        for xo, yo, up, lo, mid, sec in struct.iter_unpack('<hh8s8s8sH', d):
            self.sides.append(Side(
                xo, yo,
                up.rstrip(b'\x00').decode('ascii', 'replace').upper(),
                lo.rstrip(b'\x00').decode('ascii', 'replace').upper(),
                mid.rstrip(b'\x00').decode('ascii', 'replace').upper(),
                self.sectors[sec] if sec < len(self.sectors) else self.sectors[0]))

        # линии
        d = wad.read(L['LINEDEFS'])
        self.lines = []
        V = self.vertexes
        for i, (a, b, fl, sp, tg, r, l) in enumerate(struct.iter_unpack('<HHHHHHH', d)):
            ln = Line(i, V[a], V[b], fl, sp, tg, r, l)
            ln.front = self.sides[r] if r != NO_SIDE and r < len(self.sides) else None
            ln.back = self.sides[l] if l != NO_SIDE and l < len(self.sides) else None
            self.lines.append(ln)
            for s in (ln.front, ln.back):
                if s is not None:
                    s.sector.lines.append(ln)

        # сегменты
        d = wad.read(L['SEGS'])
        self.segs = []
        for a, b, ang, ld, side, off in struct.iter_unpack('<HHhHhh', d):
            line = self.lines[ld] if ld < len(self.lines) else self.lines[0]
            self.segs.append(Seg(V[a], V[b], ang * math.pi / 32768.0, line, side, off))

        # подсекторы
        d = wad.read(L['SSECTORS'])
        self.subsectors = []
        for cnt, first in struct.iter_unpack('<HH', d):
            sg = self.segs[first]
            side = sg.line.back if sg.side else sg.line.front
            if side is None:
                side = sg.line.front or sg.line.back
            self.subsectors.append(SubSector(first, cnt, side.sector))

        # узлы BSP
        d = wad.read(L['NODES'])
        self.nodes = []
        for rec in struct.iter_unpack('<hhhh8hHH', d):
            x, y, dx, dy = rec[0:4]
            bb0 = rec[4:8]
            bb1 = rec[8:12]
            self.nodes.append(Node(x, y, dx, dy, (bb0, bb1), (rec[12], rec[13])))

        # вещи
        d = wad.read(L['THINGS'])
        self.things = [Thing(x, y, a, t, f) for x, y, a, t, f in struct.iter_unpack('<hhhHH', d)]

        # габариты карты
        xs = [v[0] for v in V]
        ys = [v[1] for v in V]
        self.bounds = (min(xs), min(ys), max(xs), max(ys))
        self.root = len(self.nodes) - 1

        self._build_blockmap()

    # ------------------------------------------------------------ поиск
    @staticmethod
    def point_side(node, x, y):
        """0 — передняя (правая) сторона узла, 1 — задняя."""
        return 0 if node.dy * (x - node.x) - node.dx * (y - node.y) > 0 else 1

    def subsector_at(self, x, y):
        if not self.nodes:
            return self.subsectors[0]
        node_idx = self.root
        while True:
            node = self.nodes[node_idx]
            side = self.point_side(node, x, y)
            c = node.child[side]
            if c & 0x8000:
                return self.subsectors[c & 0x7FFF]
            node_idx = c

    def sector_at(self, x, y):
        return self.subsector_at(x, y).sector

    # ------------------------------------------------------------ блокмап
    def _build_blockmap(self, cell=128):
        minx, miny, maxx, maxy = self.bounds
        self.bm_x = minx - 8
        self.bm_y = miny - 8
        self.bm_cell = cell
        self.bm_w = int((maxx - minx) / cell) + 2
        self.bm_h = int((maxy - miny) / cell) + 2
        self.blockmap = [[] for _ in range(self.bm_w * self.bm_h)]
        for ln in self.lines:
            x0 = min(ln.v1[0], ln.v2[0])
            x1 = max(ln.v1[0], ln.v2[0])
            y0 = min(ln.v1[1], ln.v2[1])
            y1 = max(ln.v1[1], ln.v2[1])
            cx0 = max(0, int((x0 - self.bm_x) / cell))
            cx1 = min(self.bm_w - 1, int((x1 - self.bm_x) / cell))
            cy0 = max(0, int((y0 - self.bm_y) / cell))
            cy1 = min(self.bm_h - 1, int((y1 - self.bm_y) / cell))
            for cy in range(cy0, cy1 + 1):
                row = cy * self.bm_w
                for cx in range(cx0, cx1 + 1):
                    self.blockmap[row + cx].append(ln)

    def lines_near(self, x, y, radius):
        cell = self.bm_cell
        cx0 = max(0, int((x - radius - self.bm_x) / cell))
        cx1 = min(self.bm_w - 1, int((x + radius - self.bm_x) / cell))
        cy0 = max(0, int((y - radius - self.bm_y) / cell))
        cy1 = min(self.bm_h - 1, int((y + radius - self.bm_y) / cell))
        out = []
        seen = set()
        for cy in range(cy0, cy1 + 1):
            row = cy * self.bm_w
            for cx in range(cx0, cx1 + 1):
                for ln in self.blockmap[row + cx]:
                    if ln.index not in seen:
                        seen.add(ln.index)
                        out.append(ln)
        return out

    def blocks_at(self, line, z):
        """Перекрывает ли линия луч на высоте z."""
        if line.back is None or line.front is None or not (line.flags & ML_TWOSIDED):
            return True
        f = line.front.sector
        b = line.back.sector
        low = f.floor if f.floor > b.floor else b.floor
        high = f.ceil if f.ceil < b.ceil else b.ceil
        return high <= low or z <= low or z >= high

    def trace(self, x1, y1, x2, y2, z):
        """Первое препятствие на отрезке -> (доля пути 0..1, линия) либо (1.0, None)."""
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return 1.0, None
        cell = self.bm_cell
        steps = int(length / (cell * 0.5)) + 2
        seen_cells = set()
        seen_lines = set()
        best = 1.0
        bestline = None
        bmx, bmy, bw, bh = self.bm_x, self.bm_y, self.bm_w, self.bm_h
        for i in range(steps + 1):
            t = i / steps
            cx = int((x1 + dx * t - bmx) / cell)
            cy = int((y1 + dy * t - bmy) / cell)
            if cx < 0 or cy < 0 or cx >= bw or cy >= bh:
                continue
            key = cy * bw + cx
            if key in seen_cells:
                continue
            seen_cells.add(key)
            for ln in self.blockmap[key]:
                if ln.index in seen_lines:
                    continue
                seen_lines.add(ln.index)
                ldx = ln.dx
                ldy = ln.dy
                den = dx * ldy - dy * ldx
                if den == 0.0:
                    continue
                ex = ln.v1[0] - x1
                ey = ln.v1[1] - y1
                tt = (ex * ldy - ey * ldx) / den
                if tt < 0.0 or tt > best:
                    continue
                uu = (ex * dy - ey * dx) / den
                if uu < 0.0 or uu > 1.0:
                    continue
                if self.blocks_at(ln, z):
                    best = tt
                    bestline = ln
        return best, bestline

    def player_start(self, num=1):
        for t in self.things:
            if t.type == num:
                return t
        return self.things[0] if self.things else Thing(0, 0, 0, 1, 7)
