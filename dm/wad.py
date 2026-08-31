"""Чтение WAD: каталог лампов, палитра, колормап, патчи, составные текстуры, флэты."""
import struct
from array import array


class Lump:
    __slots__ = ('name', 'pos', 'size', 'index')

    def __init__(self, name, pos, size, index):
        self.name = name
        self.pos = pos
        self.size = size
        self.index = index

    def __repr__(self):
        return '<Lump %s #%d %db>' % (self.name, self.index, self.size)


class Wad:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self.data = f.read()
        sig, count, dirofs = struct.unpack_from('<4sii', self.data, 0)
        if sig not in (b'IWAD', b'PWAD'):
            raise ValueError('не WAD-файл: %s' % path)
        self.type = sig.decode('ascii')
        self.lumps = []
        self.by_name = {}
        for i in range(count):
            pos, size, raw = struct.unpack_from('<ii8s', self.data, dirofs + i * 16)
            name = raw.rstrip(b'\x00').decode('ascii', 'replace').upper()
            lump = Lump(name, pos, size, i)
            self.lumps.append(lump)
            self.by_name.setdefault(name, lump)   # первый по имени

    # ------------------------------------------------------------- доступ
    def has(self, name):
        return name.upper() in self.by_name

    def find(self, name, start=0):
        name = name.upper()
        for i in range(start, len(self.lumps)):
            if self.lumps[i].name == name:
                return i
        return -1

    def read(self, lump):
        if isinstance(lump, str):
            l = self.by_name.get(lump.upper())
            if l is None:
                return None
            lump = l
        elif isinstance(lump, int):
            lump = self.lumps[lump]
        return self.data[lump.pos:lump.pos + lump.size]

    def maps(self):
        import re
        pat = re.compile(r'^(E\dM\d|MAP\d\d)$')
        return [l.name for l in self.lumps if pat.match(l.name)]

    def range_lumps(self, start, end):
        """Лампы строго между маркерами start и end."""
        i = self.find(start)
        if i < 0:
            return []
        out = []
        for l in self.lumps[i + 1:]:
            if l.name == end:
                break
            out.append(l)
        return out


# ------------------------------------------------------------------ графика
def parse_playpal(data):
    """Первая палитра -> 256 упакованных RGB."""
    pal = array('i', [0]) * 256
    for i in range(256):
        r = data[i * 3]
        g = data[i * 3 + 1]
        b = data[i * 3 + 2]
        pal[i] = (r << 16) | (g << 8) | b
    return pal


def build_light_lut(playpal, colormap):
    """rgb_lut[light][index] -> упакованный цвет. light 0 = ярко, 31 = темно."""
    pal = parse_playpal(playpal)
    n = len(colormap) // 256
    lut = []
    for l in range(n):
        base = l * 256
        lut.append(array('i', [pal[colormap[base + i]] for i in range(256)]))
    return pal, lut


class Patch:
    """Формат картинки DOOM: колонки из постов."""
    __slots__ = ('width', 'height', 'xoff', 'yoff', 'cols')

    def __init__(self, data):
        w, h, xo, yo = struct.unpack_from('<hhhh', data, 0)
        self.width = w
        self.height = h
        self.xoff = xo
        self.yoff = yo
        offs = struct.unpack_from('<%di' % w, data, 8)
        self.cols = []
        for x in range(w):
            posts = []
            p = offs[x]
            if p <= 0 or p >= len(data):
                self.cols.append(posts)
                continue
            prev_top = -1
            while p < len(data):
                top = data[p]
                if top == 0xFF:
                    break
                length = data[p + 1]
                if top <= prev_top:                 # "tall patch" — смещение
                    top += prev_top
                prev_top = top
                pix = data[p + 3:p + 3 + length]    # p+2 — фиктивный байт
                posts.append((top, pix))
                p += length + 4
            self.cols.append(posts)


class Texture:
    """Составная текстура: колонки индексов палитры + маска непрозрачности."""
    __slots__ = ('name', 'width', 'height', 'cols', 'mask', 'masked')

    def __init__(self, name, width, height):
        self.name = name
        self.width = max(1, width)
        self.height = max(1, height)
        self.cols = [bytearray(self.height) for _ in range(self.width)]
        self.mask = [bytearray(self.height) for _ in range(self.width)]
        self.masked = False

    def stamp(self, patch, ox, oy):
        for px in range(patch.width):
            tx = ox + px
            if tx < 0 or tx >= self.width:
                continue
            col = self.cols[tx]
            msk = self.mask[tx]
            for top, pix in patch.cols[px]:
                y = oy + top
                for i, v in enumerate(pix):
                    yy = y + i
                    if 0 <= yy < self.height:
                        col[yy] = v
                        msk[yy] = 1

    def finish(self):
        self.masked = any(0 in m for m in self.mask)


class Graphics:
    """Палитра, освещение, текстуры стен, флэты, патчи-спрайты."""

    def __init__(self, wad):
        self.wad = wad
        self._cm = wad.read('COLORMAP')
        self._pp = wad.read('PLAYPAL')
        self.npal = len(self._pp) // 768
        self.palette, self.lut = build_light_lut(self._pp, self._cm)
        self.nlights = len(self.lut)
        self._luts = {0: self.lut}
        self._patch_cache = {}
        self._load_pnames()
        self.textures = {}
        self.texdefs = {}
        for lname in ('TEXTURE1', 'TEXTURE2'):
            if wad.has(lname):
                self._load_texture_lump(wad.read(lname))
        self._load_flats()

    def lut_for(self, pal_index):
        """Таблицы освещения для одной из палитр PLAYPAL (вспышки урона и бонусов)."""
        if pal_index <= 0 or pal_index >= self.npal:
            return self.lut
        got = self._luts.get(pal_index)
        if got is None:
            got = build_light_lut(self._pp[pal_index * 768:(pal_index + 1) * 768],
                                  self._cm)[1]
            self._luts[pal_index] = got
        return got

    # ---------------------------------------------------------- патчи
    def _load_pnames(self):
        data = self.wad.read('PNAMES')
        n = struct.unpack_from('<i', data, 0)[0]
        self.pnames = []
        for i in range(n):
            raw = data[4 + i * 8:12 + i * 8]
            self.pnames.append(raw.rstrip(b'\x00').decode('ascii', 'replace').upper())

    def patch(self, name):
        name = name.upper()
        p = self._patch_cache.get(name)
        if p is None:
            data = self.wad.read(name)
            if data is None or len(data) < 8:
                return None
            try:
                p = Patch(data)
            except Exception:
                return None
            self._patch_cache[name] = p
        return p

    # ---------------------------------------------------------- текстуры
    def _load_texture_lump(self, data):
        """Только объявления — сама текстура собирается при первом обращении."""
        count = struct.unpack_from('<i', data, 0)[0]
        offs = struct.unpack_from('<%di' % count, data, 4)
        for o in offs:
            name = data[o:o + 8].rstrip(b'\x00').decode('ascii', 'replace').upper()
            w, h = struct.unpack_from('<hh', data, o + 12)
            npatch = struct.unpack_from('<h', data, o + 20)[0]
            parts = []
            p = o + 22
            for _ in range(npatch):
                ox, oy, pidx = struct.unpack_from('<hhh', data, p)
                p += 10
                parts.append((ox, oy, pidx))
            self.texdefs[name] = (w, h, parts)

    def texture(self, name):
        if not name or name[0] == '-':
            return None
        name = name.upper()
        tex = self.textures.get(name)
        if tex is not None:
            return tex
        d = self.texdefs.get(name)
        if d is None:
            self.textures[name] = None
            return None
        w, h, parts = d
        tex = Texture(name, w, h)
        for ox, oy, pidx in parts:
            if 0 <= pidx < len(self.pnames):
                pat = self.patch(self.pnames[pidx])
                if pat:
                    tex.stamp(pat, ox, oy)
        tex.finish()
        self.textures[name] = tex
        return tex

    def has_texture(self, name):
        return bool(name) and name[0] != '-' and name.upper() in self.texdefs

    # ---------------------------------------------------------- флэты
    def _load_flats(self):
        self.flats = {}
        lumps = self.wad.range_lumps('F_START', 'F_END')
        if not lumps:
            lumps = self.wad.range_lumps('FF_START', 'FF_END')
        for l in lumps:
            if l.size == 4096:
                self.flats[l.name] = self.wad.read(l)

    def flat(self, name):
        return self.flats.get(name.upper()) if name else None
