"""Программный рендерер в духе оригинального DOOM.

Обход BSP спереди назад, отрисовка сегментов по колонкам с перспективно
корректной текстурой, полы/потолки заполняются прямо в колонке
(в одном секторе высота пола постоянна, поэтому visplane'ы не нужны),
верх/низ отсекаются массивами top_clip/bot_clip.
"""
import math
from array import array

from .mapdata import ML_DONTPEGBOTTOM, ML_DONTPEGTOP

SKY_FLAT = 'F_SKY1'
NEAR = 1.0


class View:
    __slots__ = ('x', 'y', 'z', 'angle', 'pitch')

    def __init__(self, x=0.0, y=0.0, z=41.0, angle=0.0, pitch=0.0):
        self.x = x
        self.y = y
        self.z = z
        self.angle = angle
        self.pitch = pitch


class Renderer:
    def __init__(self, gfx, w, h, fov=90.0, pixel_aspect=1.0):
        self.gfx = gfx
        self.fov = fov
        self.pixel_aspect = pixel_aspect
        self.sky_name = 'SKY1'
        self.lut = gfx.lut
        self.setup(w, h)
        # освещение как в оригинале: базовая темнота сектора минус
        # «подсветка вблизи», всё это зажимается в диапазон колормапов
        n = len(gfx.lut)
        self.maxlight = min(31, n - 1)
        self.lclamp = [0] * 224
        for i in range(224):
            v = i - 64
            self.lclamp[i] = 0 if v < 0 else (self.maxlight if v > self.maxlight else v)
        self.near_light = 1400.0
        self.dlt = [0] * 1200            # индекс = int(z) >> 3
        for i in range(1200):
            z = max(1.0, i * 8.0)
            # ограничение сверху: индекс освещения не должен уйти ниже нуля
            self.dlt[i] = min(56, int(self.near_light / z))
        self.dlt_max = len(self.dlt) - 1

    def set_palette(self, idx):
        self.lut = self.gfx.lut_for(idx)

    def setup(self, w, h):
        self.w = w
        self.h = h
        self.projx = (w * 0.5) / math.tan(math.radians(self.fov) * 0.5)
        self.projy = self.projx * self.pixel_aspect
        self.centerx = w * 0.5
        self.top = array('i', [0]) * w
        self.bot = array('i', [0]) * w
        self.zbuf = array('f', [0.0]) * w
        # окна отсечения по колонке: (глубина_сужения, верх, низ) — для спрайтов
        self.clips = [[] for _ in range(w)]
        self.yslope = array('f', [0.0]) * h
        # боковые множители колонки: A = cos+sin*lx, B = sin-cos*lx (заполняются в кадре)
        self.colA = array('f', [0.0]) * w
        self.colB = array('f', [0.0]) * w
        self.lx = array('f', [0.0]) * w

    # ------------------------------------------------------------- кадр
    def render(self, frame, md, view):
        w, h = self.w, self.h
        self.md = md
        self.pix = frame.pix
        self.vx = view.x
        self.vy = view.y
        self.vz = view.z
        self.cy = h * 0.5 + view.pitch
        cy = self.cy
        self.sina = math.sin(view.angle)
        self.cosa = math.cos(view.angle)
        self.angle = view.angle

        ys = self.yslope
        py = self.projy
        for y in range(h):
            d = (y + 0.5) - cy
            ys[y] = py / d if d != 0.0 else 1e9

        lx = self.lx
        A = self.colA
        B = self.colB
        sa, ca = self.sina, self.cosa
        px = self.projx
        cx = self.centerx
        for x in range(w):
            t = (x + 0.5 - cx) / px
            lx[x] = t
            A[x] = ca + sa * t
            B[x] = sa - ca * t

        top = self.top
        bot = self.bot
        zbuf = self.zbuf
        clips = self.clips
        for x in range(w):
            top[x] = 0
            bot[x] = h - 1
            zbuf[x] = 1e9
            if clips[x]:
                clips[x] = []
        self.open_cols = w
        self.masked = []
        self.sky = self.gfx.texture(self.sky_name)

        self.visible_segs = 0
        self._traverse(md.root)

    # ------------------------------------------------------------- BSP
    def _traverse(self, node_idx):
        md = self.md
        stack = [node_idx]
        pop = stack.pop
        push = stack.append
        while stack:
            if self.open_cols <= 0:
                return
            idx = pop()
            if idx & 0x8000:
                self._subsector(md.subsectors[idx & 0x7FFF])
                continue
            node = md.nodes[idx]
            side = 0 if node.dy * (self.vx - node.x) - node.dx * (self.vy - node.y) > 0 else 1
            push(node.child[side ^ 1])   # дальняя половина — потом
            push(node.child[side])       # ближняя — сразу

    def _subsector(self, ss):
        md = self.md
        segs = md.segs
        for i in range(ss.first, ss.first + ss.count):
            self._seg(segs[i], ss.sector)
            if self.open_cols <= 0:
                return

    # ------------------------------------------------------------- сегмент
    def _seg(self, seg, sector):
        v1 = seg.v1
        v2 = seg.v2
        vx, vy = self.vx, self.vy
        # отсечение задних граней
        if (v2[0] - v1[0]) * (vy - v1[1]) - (v2[1] - v1[1]) * (vx - v1[0]) >= 0.0:
            return

        sa, ca = self.sina, self.cosa
        dx1 = v1[0] - vx
        dy1 = v1[1] - vy
        dx2 = v2[0] - vx
        dy2 = v2[1] - vy
        d1 = dx1 * ca + dy1 * sa          # глубина
        l1 = dx1 * sa - dy1 * ca          # смещение вправо
        d2 = dx2 * ca + dy2 * sa
        l2 = dx2 * sa - dy2 * ca
        s1 = 0.0
        s2 = 1.0

        # ближняя плоскость
        if d1 < NEAR and d2 < NEAR:
            return
        if d1 < NEAR:
            t = (NEAR - d1) / (d2 - d1)
            l1 += (l2 - l1) * t
            d1 = NEAR
            s1 += (s2 - s1) * t
        elif d2 < NEAR:
            t = (NEAR - d2) / (d1 - d2)
            l2 += (l1 - l2) * t
            d2 = NEAR
            s2 += (s1 - s2) * t

        px = self.projx
        cx = self.centerx
        w = self.w
        # боковые плоскости пирамиды видимости
        # левая: l*px + d*cx >= 0 ; правая: d*(w-cx) - l*px >= 0
        f1 = l1 * px + d1 * cx
        f2 = l2 * px + d2 * cx
        if f1 < 0.0 and f2 < 0.0:
            return
        if f1 < 0.0:
            t = f1 / (f1 - f2)
            l1 += (l2 - l1) * t
            d1 += (d2 - d1) * t
            s1 += (s2 - s1) * t
        elif f2 < 0.0:
            t = f2 / (f2 - f1)
            l2 += (l1 - l2) * t
            d2 += (d1 - d2) * t
            s2 += (s1 - s2) * t

        rw = w - cx
        g1 = d1 * rw - l1 * px
        g2 = d2 * rw - l2 * px
        if g1 < 0.0 and g2 < 0.0:
            return
        if g1 < 0.0:
            t = g1 / (g1 - g2)
            l1 += (l2 - l1) * t
            d1 += (d2 - d1) * t
            s1 += (s2 - s1) * t
        elif g2 < 0.0:
            t = g2 / (g2 - g1)
            l2 += (l1 - l2) * t
            d2 += (d1 - d2) * t
            s2 += (s1 - s2) * t

        if d1 < NEAR or d2 < NEAR:
            return

        sx1 = cx + l1 / d1 * px
        sx2 = cx + l2 / d2 * px
        if sx2 - sx1 < 0.01:
            return
        x1 = int(math.ceil(sx1 - 0.5))
        x2 = int(math.ceil(sx2 - 0.5)) - 1
        if x1 < 0:
            x1 = 0
        if x2 > w - 1:
            x2 = w - 1
        if x1 > x2:
            return

        line = seg.line
        side = line.back if seg.side else line.front
        if side is None:
            return
        back = line.front if seg.side else line.back
        back_sector = back.sector if (back is not None and (line.flags & 0x0004)) else None

        # интерполяция 1/z и s/z по экрану
        iz1 = 1.0 / d1
        iz2 = 1.0 / d2
        span = sx2 - sx1
        diz = (iz2 - iz1) / span
        sz1 = s1 * iz1
        dsz = (s2 * iz2 - sz1) / span

        self.visible_segs += 1
        self._render_wall(seg, sector, back_sector, side, line,
                          x1, x2, sx1, iz1, diz, sz1, dsz)

    # ------------------------------------------------------------- стена
    def _render_wall(self, seg, front, back, side, line,
                     x1, x2, sx1, iz1, diz, sz1, dsz):
        gfx = self.gfx
        pix = self.pix
        w = self.w
        h = self.h
        cy = self.cy
        projy = self.projy
        top = self.top
        bot = self.bot
        zbuf = self.zbuf
        clips = self.clips
        lut = self.lut
        lclamp = self.lclamp
        dlt = self.dlt
        dlt_max = self.dlt_max
        vz = self.vz
        vx = self.vx
        vy = self.vy
        ys = self.yslope
        colA = self.colA
        colB = self.colB

        fc = front.ceil
        ff = front.floor
        fc_rel = (fc - vz) * projy
        ff_rel = (ff - vz) * projy

        sky_ceil = front.ceilpic == SKY_FLAT
        ceil_flat = None if sky_ceil else gfx.flat(front.ceilpic)
        floor_flat = gfx.flat(front.floorpic)

        # освещение сектора (+64 — смещение таблицы lclamp)
        sbase = (15 - (front.light >> 4)) * 4 + 64
        base = sbase                      # для стен: подсветка по ориентации
        if line.v1[1] == line.v2[1]:
            base += 4
        elif line.v1[0] == line.v2[0]:
            base -= 4

        seg_len = seg.length
        u_base = seg.offset + side.xoff

        solid = back is None
        if not solid:
            bc = back.ceil
            bf = back.floor
            bc_rel = (bc - vz) * projy
            bf_rel = (bf - vz) * projy
            sky_back = back.ceilpic == SKY_FLAT
            closed = (bf >= bc) or (bf >= fc) or (bc <= ff)
            up_tex = gfx.texture(side.upper) if (bc < fc and not (sky_ceil and sky_back)) else None
            lo_tex = gfx.texture(side.lower) if bf > ff else None
            if closed:
                solid = True
                mid_tex = gfx.texture(side.middle) or up_tex or lo_tex
            else:
                mid_tex = None
                # решётки и перила: средняя текстура двусторонней линии
                mt = gfx.texture(side.middle)
                if mt is not None:
                    if line.flags & ML_DONTPEGBOTTOM:
                        tmid = max(ff, bf) + mt.height - vz + side.yoff
                    else:
                        tmid = min(fc, bc) - vz + side.yoff
                    xm = (x1 + x2) * 0.5 + 0.5 - sx1
                    izm = iz1 + diz * xm
                    self.masked.append((
                        1.0 / izm if izm > 0.0 else 1e9, mt, x1, x2, sx1,
                        iz1, diz, sz1, dsz, seg.offset + side.xoff, seg.length,
                        tmid, sbase, max(ff, bf) - vz, min(fc, bc) - vz))
        else:
            mid_tex = gfx.texture(side.middle)
            up_tex = lo_tex = None

        # вертикальные привязки текстур
        pegbot = line.flags & ML_DONTPEGBOTTOM
        pegtop = line.flags & ML_DONTPEGTOP
        if mid_tex is not None:
            if pegbot:
                mid_mid = ff + mid_tex.height - vz + side.yoff
            else:
                mid_mid = fc - vz + side.yoff
        if up_tex is not None:
            if pegtop:
                up_mid = fc - vz + side.yoff
            else:
                up_mid = back.ceil + up_tex.height - vz + side.yoff
        if lo_tex is not None:
            if pegbot:
                lo_mid = fc - vz + side.yoff
            else:
                lo_mid = back.floor - vz + side.yoff

        sky = self.sky
        sky_w = sky.width if sky else 1
        sky_h = sky.height if sky else 1
        sky_cols = sky.cols if sky else None
        sky_lut = lut[0]
        ang = self.angle
        px = self.projx
        cx = self.centerx
        TWO_PI = math.pi * 2.0

        for x in range(x1, x2 + 1):
            ty = top[x]
            by = bot[x]
            if ty > by:
                continue
            dxs = x + 0.5 - sx1
            iz = iz1 + diz * dxs
            if iz <= 0.0:
                continue
            z = 1.0 / iz

            yt = cy - fc_rel * iz
            yb = cy - ff_rel * iz
            yl = int(math.ceil(yt - 0.5))
            yh = int(math.ceil(yb - 0.5)) - 1

            # ---------- потолок
            ce = yl - 1
            if ce > by:
                ce = by
            if ce >= ty:
                if sky_ceil:
                    self._sky_col(x, ty, ce, ang, px, cx, sky_cols, sky_w, sky_h, sky_lut)
                elif ceil_flat is not None:
                    hh = fc - vz
                    if hh > 0.0:
                        a = colA[x]
                        b = colB[x]
                        o = ty * w + x
                        for y in range(ty, ce + 1):
                            zz = hh * ys[y]
                            if zz < 0.0:
                                zz = -zz
                            tx = int(vx + zz * a) & 63
                            tyy = int(-(vy + zz * b)) & 63
                            zi = int(zz) >> 3
                            pix[o] = lut[lclamp[sbase - dlt[zi if zi < dlt_max else dlt_max]]][
                                ceil_flat[(tyy << 6) | tx]]
                            o += w

            # ---------- пол
            fs = yh + 1
            if fs < ty:
                fs = ty
            if fs <= by and floor_flat is not None:
                hh = vz - ff
                if hh > 0.0:
                    a = colA[x]
                    b = colB[x]
                    o = fs * w + x
                    for y in range(fs, by + 1):
                        zz = hh * ys[y]
                        if zz < 0.0:
                            zz = -zz
                        tx = int(vx + zz * a) & 63
                        tyy = int(-(vy + zz * b)) & 63
                        zi = int(zz) >> 3
                        pix[o] = lut[lclamp[sbase - dlt[zi if zi < dlt_max else dlt_max]]][
                            floor_flat[(tyy << 6) | tx]]
                        o += w

            # ---------- текстурные координаты
            zi = int(z) >> 3
            cl = lut[lclamp[base - dlt[zi if zi < dlt_max else dlt_max]]]
            s = (sz1 + dsz * dxs) * z
            u = u_base + s * seg_len
            iscale = z / projy

            if solid:
                a0 = yl if yl > ty else ty
                b0 = yh if yh < by else by
                if mid_tex is not None and a0 <= b0:
                    col = mid_tex.cols[int(u) % mid_tex.width]
                    th = mid_tex.height
                    v = mid_mid + (a0 + 0.5 - cy) * iscale
                    o = a0 * w + x
                    for y in range(a0, b0 + 1):
                        pix[o] = cl[col[int(v) % th]]
                        v += iscale
                        o += w
                elif a0 <= b0:
                    o = a0 * w + x
                    c = cl[0]
                    for y in range(a0, b0 + 1):
                        pix[o] = c
                        o += w
                top[x] = 1
                bot[x] = 0
                zbuf[x] = z
                self.open_cols -= 1
                continue

            # ---------- портал: верх и низ
            new_top = yl if yl > ty else ty
            new_bot = yh if yh < by else by

            if bc < fc:
                ybt = cy - bc_rel * iz
                ylb = int(math.ceil(ybt - 0.5))
                a0 = yl if yl > ty else ty
                b0 = ylb - 1
                if b0 > by:
                    b0 = by
                if up_tex is not None and a0 <= b0:
                    col = up_tex.cols[int(u) % up_tex.width]
                    th = up_tex.height
                    v = up_mid + (a0 + 0.5 - cy) * iscale
                    o = a0 * w + x
                    for y in range(a0, b0 + 1):
                        pix[o] = cl[col[int(v) % th]]
                        v += iscale
                        o += w
                elif sky_ceil and a0 <= b0:
                    self._sky_col(x, a0, b0, ang, px, cx, sky_cols, sky_w, sky_h, sky_lut)
                if ylb > new_top:
                    new_top = ylb
            if bf > ff:
                ybf = cy - bf_rel * iz
                yhb = int(math.ceil(ybf - 0.5)) - 1
                a0 = yhb + 1
                if a0 < ty:
                    a0 = ty
                b0 = yh if yh < by else by
                if lo_tex is not None and a0 <= b0:
                    col = lo_tex.cols[int(u) % lo_tex.width]
                    th = lo_tex.height
                    v = lo_mid + (a0 + 0.5 - cy) * iscale
                    o = a0 * w + x
                    for y in range(a0, b0 + 1):
                        pix[o] = cl[col[int(v) % th]]
                        v += iscale
                        o += w
                if yhb < new_bot:
                    new_bot = yhb

            changed = False
            if new_top > top[x]:
                top[x] = new_top
                changed = True
            if new_bot < bot[x]:
                bot[x] = new_bot
                changed = True
            if top[x] > bot[x]:
                zbuf[x] = z
                self.open_cols -= 1
            elif changed:
                clips[x].append((z, top[x], bot[x]))

    # ------------------------------------------------------------- спрайты
    def render_things(self, actors, sprset, time):
        """Билборды поверх мира: сортировка от дальних к ближним, тест глубины."""
        if not actors and not self.masked:
            return
        vx, vy, vz = self.vx, self.vy, self.vz
        sa, ca = self.sina, self.cosa
        px, py = self.projx, self.projy
        cx, cy = self.centerx, self.cy
        w = self.w
        vis = []
        for a in actors:
            dx = a.x - vx
            dy = a.y - vy
            depth = dx * ca + dy * sa
            if depth < 8.0 or depth > 4000.0:
                continue
            lat = dx * sa - dy * ca
            if abs(lat) > depth * (w / px):        # с запасом на ширину спрайта
                continue
            vis.append((depth, lat, a, math.atan2(dy, dx)))
        for rec in self.masked:
            vis.append((rec[0], None, rec, None))
        vis.sort(key=lambda t: -t[0])
        for depth, lat, a, ang_to in vis:
            if lat is None:
                self._draw_masked(a)
            else:
                self._draw_sprite(a, depth, lat, ang_to, sprset, time, px, py, cx, cy, w)

    def _draw_sprite(self, a, depth, lat, ang_to, sprset, time, px, py, cx, cy, w):
        gfx = self.gfx
        frame = a.frame_at(time)
        got = sprset.pick(a.sprite, frame, ang_to, a.angle)
        if not got:
            return
        patch = gfx.patch(got[0])
        if patch is None or patch.width <= 0:
            return
        flip = got[1]
        xscale = px / depth
        yscale = py / depth
        pw = patch.width
        ph = patch.height
        xoff = patch.xoff if not flip else (pw - patch.xoff)
        x1f = cx + (lat - xoff) * xscale
        x2f = x1f + pw * xscale
        x1 = int(math.ceil(x1f - 0.5))
        x2 = int(math.ceil(x2f - 0.5)) - 1
        if x2 < 0 or x1 > w - 1:
            return
        base_z = a.base_z()
        top_z = base_z + patch.yoff
        ytop = cy - (top_z - self.vz) * yscale
        if ytop > self.h or ytop + ph * yscale < 0:
            return

        if a.shadow:
            cl = self.lut[min(self.maxlight, 26)]
        elif a.bright:
            cl = self.lut[0]
        else:
            sec = a.sector
            sbase = (15 - (sec.light >> 4)) * 4 + 64
            zi = int(depth) >> 3
            d = self.dlt[zi if zi < self.dlt_max else self.dlt_max]
            cl = self.lut[self.lclamp[sbase - d]]

        pix = self.pix
        zbuf = self.zbuf
        clips = self.clips
        cols = patch.cols
        inv_w = pw / (x2f - x1f)
        h = self.h
        if x1 < 0:
            x1 = 0
        if x2 > w - 1:
            x2 = w - 1
        for x in range(x1, x2 + 1):
            if depth >= zbuf[x]:
                continue
            u = int((x + 0.5 - x1f) * inv_w)
            if u < 0:
                u = 0
            elif u >= pw:
                u = pw - 1
            if flip:
                u = pw - 1 - u
            wtop = 0
            wbot = h - 1
            for cz, ct, cb in clips[x]:
                if cz >= depth:
                    break
                wtop = ct
                wbot = cb
            if wtop > wbot:
                continue
            for ptop, data in cols[u]:
                y0f = ytop + ptop * yscale
                y1f = y0f + len(data) * yscale
                y0 = int(math.ceil(y0f - 0.5))
                y1 = int(math.ceil(y1f - 0.5)) - 1
                if y0 < wtop:
                    y0 = wtop
                if y1 > wbot:
                    y1 = wbot
                if y0 > y1:
                    continue
                inv_y = 1.0 / yscale
                o = y0 * w + x
                n = len(data) - 1
                for y in range(y0, y1 + 1):
                    v = int((y + 0.5 - y0f) * inv_y)
                    if v < 0:
                        v = 0
                    elif v > n:
                        v = n
                    pix[o] = cl[data[v]]
                    o += w

    # --------------------------------------------- средние текстуры (решётки)
    def _draw_masked(self, rec):
        (_z, tex, x1, x2, sx1, iz1, diz, sz1, dsz, u_base, seg_len,
         tmid, sbase, open_lo, open_hi) = rec
        pix = self.pix
        w = self.w
        h = self.h
        cy = self.cy
        projy = self.projy
        zbuf = self.zbuf
        clips = self.clips
        lut = self.lut
        lclamp = self.lclamp
        dlt = self.dlt
        dlt_max = self.dlt_max
        cols = tex.cols
        mask = tex.mask
        tw = tex.width
        th = tex.height
        for x in range(x1, x2 + 1):
            dxs = x + 0.5 - sx1
            iz = iz1 + diz * dxs
            if iz <= 0.0:
                continue
            z = 1.0 / iz
            if z >= zbuf[x]:
                continue
            wtop = 0
            wbot = h - 1
            for cz, ct, cb in clips[x]:
                if cz >= z:
                    break
                wtop = ct
                wbot = cb
            if wtop > wbot:
                continue
            # окно портала тоже режет текстуру
            pz = projy * iz
            ytop = cy - tmid * pz
            a0 = int(ytop + 0.5)
            b0 = int(ytop + th * pz + 0.5) - 1
            lo = int(cy - open_hi * pz + 0.5)
            hi = int(cy - open_lo * pz + 0.5) - 1
            if lo > a0:
                a0 = lo
            if wtop > a0:
                a0 = wtop
            if hi < b0:
                b0 = hi
            if wbot < b0:
                b0 = wbot
            if a0 > b0:
                continue
            s = (sz1 + dsz * dxs) * z
            ui = int(u_base + s * seg_len) % tw
            col = cols[ui]
            msk = mask[ui]
            zi = int(z) >> 3
            cl = lut[lclamp[sbase - dlt[zi if zi < dlt_max else dlt_max]]]
            iscale = z / projy
            v = (a0 + 0.5 - ytop) * iscale
            o = a0 * w + x
            for y in range(a0, b0 + 1):
                iv = int(v)
                if 0 <= iv < th and msk[iv]:
                    pix[o] = cl[col[iv]]
                v += iscale
                o += w

    # ------------------------------------------------------------- небо
    def _sky_col(self, x, y0, y1, ang, px, cx, cols, sw, sh, lut):
        if cols is None:
            return
        pix = self.pix
        w = self.w
        a = ang + math.atan((cx - (x + 0.5)) / px)
        u = int(a * (2.0 * sw) / math.pi) % sw
        col = cols[u]
        # небо рисуется в фиксированном масштабе, без перспективы
        k = 100.0 / (self.h * 0.5)
        base = 40.0
        o = y0 * w + x
        for y in range(y0, y1 + 1):
            v = int(base + (y - self.cy) * k)
            if v < 0:
                v = 0
            elif v >= sh:
                v = sh - 1
            pix[o] = lut[col[v]]
            o += w
