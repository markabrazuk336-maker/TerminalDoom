"""Отладка: рендер одного кадра в PNG.

  python tools/shot.py [карта] [файл.png] [ширина] [высота] [dx] [dy] [угол_град]
"""
import os
import sys
import struct
import zlib
import math
import time
from array import array

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm import wad as W
from dm import mapdata as M
from dm import renderer as R

WAD = os.environ.get('DOOMWAD', r'C:\Users\Markazuk\Documents\freedoom-0.12.1\freedoom1.wad')


class Buf:
    def __init__(self, w, h):
        self.pix = array('i', [0]) * (w * h)


def write_png(path, w, h, pix):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        o = y * w
        for x in range(w):
            c = pix[o + x]
            raw.append((c >> 16) & 255)
            raw.append((c >> 8) & 255)
            raw.append(c & 255)

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 6))
    png += chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)


def main():
    mapname = sys.argv[1] if len(sys.argv) > 1 else 'E1M1'
    out = sys.argv[2] if len(sys.argv) > 2 else 'shot.png'
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 320
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    dx = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
    dy = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
    da = float(sys.argv[7]) if len(sys.argv) > 7 else 0.0

    wad = W.Wad(WAD)
    gfx = W.Graphics(wad)
    md = M.MapData(wad, mapname)
    ren = R.Renderer(gfx, w, h, fov=90.0, pixel_aspect=1.2)
    ren.sky_name = 'SKY' + (mapname[1] if mapname.startswith('E') else '1')

    st = md.player_start()
    sec = md.sector_at(st.x, st.y)
    view = R.View(st.x + dx, st.y + dy, sec.floor + 41.0, st.angle + math.radians(da))

    buf = Buf(w, h)
    t = time.time()
    ren.render(buf, md, view)
    el = time.time() - t
    write_png(out, w, h, buf.pix)
    print('%s -> %s  %dx%d  %.3fs  segs=%d  pos=(%.0f,%.0f) ang=%.0f' %
          (mapname, out, w, h, el, ren.visible_segs, view.x, view.y, math.degrees(view.angle)))


if __name__ == '__main__':
    main()
