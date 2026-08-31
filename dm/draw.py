"""Отрисовка патчей DOOM с масштабированием + кеш растров (иначе HUD съедает кадр)."""
from array import array


class Raster:
    """Кусок кадра: тот же интерфейс, что нужен draw_patch."""

    __slots__ = ('pix', 'w', 'h')

    def __init__(self, w, h, fill=0):
        self.w = w
        self.h = h
        self.pix = array('i', [fill]) * (w * h)


def draw_patch(frame, patch, x, y, kx, ky, pal, ylo=0, yhi=None):
    """x, y — левый верхний угол в пикселях кадра (смещения патча уже учтены)."""
    if patch is None:
        return
    pix = frame.pix
    w = frame.w
    if yhi is None:
        yhi = frame.h
    cols = patch.cols
    for sx in range(patch.width):
        ix0 = int(x + sx * kx + 0.5)
        ix1 = int(x + (sx + 1) * kx + 0.5)
        if ix1 <= ix0:
            ix1 = ix0 + 1
        if ix1 <= 0 or ix0 >= w:
            continue
        if ix0 < 0:
            ix0 = 0
        if ix1 > w:
            ix1 = w
        for top, data in cols[sx]:
            for i, v in enumerate(data):
                iy0 = int(y + (top + i) * ky + 0.5)
                iy1 = int(y + (top + i + 1) * ky + 0.5)
                if iy1 <= iy0:
                    iy1 = iy0 + 1
                if iy0 < ylo:
                    iy0 = ylo
                if iy1 > yhi:
                    iy1 = yhi
                if iy0 >= iy1:
                    continue
                c = pal[v]
                for yy in range(iy0, iy1):
                    o = yy * w
                    for xx in range(ix0, ix1):
                        pix[o + xx] = c


class ScaledPatch:
    """Патч, заранее растянутый до нужного размера и разложенный на строки-полосы."""

    __slots__ = ('rows', 'w', 'h')

    def __init__(self, patch, kx, ky, pal):
        w = max(1, int(round(patch.width * kx)))
        h = max(1, int(round(patch.height * ky)))
        self.w = w
        self.h = h
        raster = [None] * (w * h)
        for sx in range(patch.width):
            x0 = int(sx * kx + 0.5)
            x1 = int((sx + 1) * kx + 0.5)
            if x1 <= x0:
                x1 = x0 + 1
            if x0 >= w:
                continue
            if x1 > w:
                x1 = w
            for top, data in patch.cols[sx]:
                for i, v in enumerate(data):
                    y0 = int((top + i) * ky + 0.5)
                    y1 = int((top + i + 1) * ky + 0.5)
                    if y1 <= y0:
                        y1 = y0 + 1
                    if y0 >= h:
                        continue
                    if y1 > h:
                        y1 = h
                    c = pal[v]
                    for yy in range(y0, y1):
                        o = yy * w
                        for xx in range(x0, x1):
                            raster[o + xx] = c
        rows = []
        for y in range(h):
            o = y * w
            x = 0
            while x < w:
                if raster[o + x] is None:
                    x += 1
                    continue
                x0 = x
                run = array('i')
                while x < w and raster[o + x] is not None:
                    run.append(raster[o + x])
                    x += 1
                rows.append((y, x0, run))
        self.rows = rows

    def blit(self, frame, ox, oy, ylo=0, yhi=None):
        pix = frame.pix
        fw = frame.w
        if yhi is None:
            yhi = frame.h
        ox = int(ox)
        oy = int(oy)
        for y, x0, run in self.rows:
            dy = oy + y
            if dy < ylo or dy >= yhi:
                continue
            dx = ox + x0
            n = len(run)
            a = 0
            b = n
            if dx < 0:
                a = -dx
                dx = 0
            if dx + (b - a) > fw:
                b = a + fw - dx
            if b <= a:
                continue
            o = dy * fw + dx
            pix[o:o + (b - a)] = run[a:b] if (a or b != n) else run
