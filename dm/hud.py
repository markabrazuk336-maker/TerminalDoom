"""Настоящая строка состояния DOOM (STBAR, цифры, лицо) + сообщения и итоги."""
import math

from .draw import draw_patch, Raster, ScaledPatch
from .player import WEAPONS

# координаты в системе 320x200, полоса начинается с y=168
BAR_Y = 168
AMMO_X = 44
HEALTH_X = 90
ARMOR_X = 221
FACE_X = 143
KEY_X = 239
KEY_Y = (172, 182, 192)
SMALL_X = 288
SMALL_MAX_X = 314
SMALL_Y = (173, 179, 185, 191)
ARMS_X = 111
ARMS_Y = 172

AMMO_ORDER = ('bull', 'shell', 'rckt', 'cell')
KEY_ORDER = ('blue', 'yellow', 'red')

CLR_MSG = 0xFFE066
CLR_TXT = 0xE0E0E0


class Hud:
    def __init__(self, gfx):
        self.gfx = gfx
        self.pal = gfx.palette
        self.ok = gfx.wad.has('STBAR')
        self._cache = {}
        self._bar = None          # готовый растр полосы
        self._sig = None
        self._scaled = {}         # кеш растянутых патчей оружия

    def p(self, name):
        got = self._cache.get(name)
        if got is None:
            got = self.gfx.patch(name)
            self._cache[name] = got
        return got

    def bar_height(self, frame):
        if not self.ok:
            return 2
        k = frame.w / 320.0
        bh = int(round(32.0 * k))
        bh -= bh % 2
        return max(2, min(bh, frame.h // 3))

    # ------------------------------------------------------------ цифры
    def num(self, frame, value, right_x, y, k, ytop, prefix='STTNUM', width=13):
        s = str(int(value))
        x = right_x - len(s) * width
        for ch in s:
            pt = self.p(prefix + ch)
            if pt:
                draw_patch(frame, pt, x * k, ytop + (y - BAR_Y) * k, k, k, self.pal)
            x += width

    # ------------------------------------------------------------ лицо
    def face_name(self, p, game):
        if p.health <= 0:
            return 'STFDEAD0'
        pain = int((100 - min(100, p.health)) / 20.0)
        if pain > 4:
            pain = 4
        if p.powers['inv'] > 0.0:
            return 'STFGOD0'
        if p.face_ouch > 0.45:
            return 'STFOUCH%d' % pain
        if p.face_kill > 0.0:
            return 'STFKILL%d' % pain
        return 'STFST%d%d' % (pain, p.face_dir)

    # ------------------------------------------------------------ полоса
    def draw(self, frame, game, fps):
        p = game.player
        if not self.ok:
            return self.draw_text(frame, game, fps)
        bh = self.bar_height(frame)
        ytop = frame.h - bh
        sig = (frame.w, bh, p.health, p.armor, p.weapon,
               tuple(sorted(p.ammo.items())), tuple(sorted(p.maxammo.items())),
               tuple(sorted(p.keys)), tuple(sorted(p.have)), self.face_name(p, game))
        if sig != self._sig:
            self._sig = sig
            self._bar = self.build_bar(frame.w, bh, game)
        w = frame.w
        src = self._bar.pix
        dst = frame.pix
        for y in range(bh):
            o = (ytop + y) * w
            dst[o:o + w] = src[y * w:(y + 1) * w]
        self.overlay(frame, game, fps)

    def build_bar(self, width, bh, game):
        p = game.player
        frame = Raster(width, bh, 0x000000)
        k = width / 320.0
        ytop = 0.0
        draw_patch(frame, self.p('STBAR'), 0, ytop, k, k, self.pal)

        arms = self.p('STARMS')
        if arms:
            draw_patch(frame, arms, 104 * k, ytop, k, k, self.pal, ylo=ytop)
            for i, wid in enumerate((1, 2, 3, 4, 5, 6)):
                col = i % 3
                row = i // 3
                have = wid in p.have
                pt = self.p('STYSNUM%d' % (wid + 1)) if have else self.p('STGNUM%d' % (wid + 1))
                if pt:
                    draw_patch(frame, pt, (ARMS_X + col * 12) * k,
                               ytop + (ARMS_Y + row * 10 - BAR_Y) * k, k, k, self.pal,
                               ylo=ytop)

        w = WEAPONS[p.weapon]
        ammo = p.ammo[w['ammo']] if w['ammo'] else 0
        if w['ammo']:
            self.num(frame, ammo, AMMO_X, 171, k, ytop)
        self.num(frame, p.health, HEALTH_X, 171, k, ytop)
        draw_patch(frame, self.p('STTPRCNT'), HEALTH_X * k, ytop + 3 * k, k, k,
                   self.pal, ylo=ytop)
        self.num(frame, p.armor, ARMOR_X, 171, k, ytop)
        draw_patch(frame, self.p('STTPRCNT'), ARMOR_X * k, ytop + 3 * k, k, k,
                   self.pal, ylo=ytop)

        face = self.p(self.face_name(p, game))
        if face:
            draw_patch(frame, face, (FACE_X + 5) * k, ytop + 1 * k, k, k, self.pal,
                       ylo=ytop)

        for i, key in enumerate(KEY_ORDER):
            if key in p.keys:
                pt = self.p('STKEYS%d' % i)
                if pt:
                    draw_patch(frame, pt, KEY_X * k,
                               ytop + (KEY_Y[i] - BAR_Y) * k, k, k, self.pal, ylo=ytop)

        for i, a in enumerate(AMMO_ORDER):
            self.num(frame, p.ammo[a], SMALL_X, SMALL_Y[i], k, ytop,
                     prefix='STYSNUM', width=4)
            self.num(frame, p.maxammo[a], SMALL_MAX_X, SMALL_Y[i], k, ytop,
                     prefix='STYSNUM', width=4)
        return frame

    # ------------------------------------------------------------ текст
    def draw_text(self, frame, game, fps):
        p = game.player
        rows = frame.rows
        frame.rect(0, (rows - 1) * 2, frame.w, rows * 2, 0x0A0A0C)
        w = WEAPONS[p.weapon]
        ammo = p.ammo[w['ammo']] if w['ammo'] else 0
        left = ' %3d%%  БРОНЯ %3d%%  %s %3d ' % (p.health, p.armor, w['name'], ammo)
        frame.put(rows - 1, 0, left, 0x50D264 if p.health > 40 else 0xFF5A28)
        self.overlay(frame, game, fps)

    def overlay(self, frame, game, fps):
        if game.messages:
            frame.put(0, 1, game.messages[0], CLR_MSG)
        right = '%s  %d/%d  %.0f к/с ' % (game.mapname, game.kills,
                                          game.total_kills, fps)
        frame.put(0, max(0, frame.cols - len(right) - 1), right, 0x9AA0A8)

    # ------------------------------------------------------------ итоги
    def intermission(self, frame, game):
        frame.clear(0x101014)
        p = game.player
        rows = frame.rows
        cx = frame.cols // 2
        t = int(game.time)
        lines = [
            ('УРОВЕНЬ ПРОЙДЕН', 0xFF6A20),
            ('', 0),
            ('%s' % game.mapname, CLR_TXT),
            ('', 0),
            ('УБИТО    %3d / %-3d' % (game.kills, game.total_kills), CLR_TXT),
            ('ПРЕДМЕТЫ %3d / %-3d' % (p.items, game.total_items), CLR_TXT),
            ('ТАЙНИКИ  %3d / %-3d' % (p.secrets, game.total_secrets), CLR_TXT),
            ('ВРЕМЯ    %02d:%02d' % (t // 60, t % 60), CLR_TXT),
            ('', 0),
            ('пробел — дальше', 0x9AA0A8),
        ]
        y0 = max(0, rows // 2 - len(lines) // 2)
        for i, (s, c) in enumerate(lines):
            if s:
                frame.put(y0 + i, cx - len(s) // 2, s, c)


def draw_weapon(frame, gfx, ren, player, view_h, sector_light, cache=None):
    """Оружие в руках: та же формула позиционирования, что в оригинале."""
    from . import player as PL
    w = PL.WEAPONS[player.weapon]
    if player.health <= 0:
        return
    name = w['sprite']
    frame_letter = player.wframe
    lump = name + frame_letter + '0'
    patch = gfx.patch(lump)
    if patch is None:
        patch = gfx.patch(name + 'A0')
        if patch is None:
            return
    kx = frame.w / 320.0
    ky = frame.h / 200.0
    bob = math.sin(player.bob * 0.5) * 8.0 * player.bob_amp
    bobz = abs(math.cos(player.bob * 0.5)) * 6.0 * player.bob_amp
    sx = 1.0 + bob
    sy = 32.0 + bobz + player.woffset
    x = ren.centerx + (sx - 160.0 - patch.xoff) * kx
    y = (sy - patch.yoff) * ky
    li = 0 if player.flash_t > 0.0 else ren.lclamp[(15 - (sector_light >> 4)) * 4 + 64 - 16]
    sp = _scaled(cache, gfx, lump if gfx.patch(lump) else name + 'A0', kx, ky,
                 ren.lut[li], li)
    if sp:
        sp.blit(frame, x, y, yhi=view_h)
    if player.flash_t > 0.0 and w.get('flash'):
        fl = w['flash'] + '0'
        fp = gfx.patch(fl)
        if fp:
            fx = ren.centerx + (sx - 160.0 - fp.xoff) * kx
            fy = (sy - fp.yoff) * ky
            fs = _scaled(cache, gfx, fl, kx, ky, ren.lut[0], 0)
            if fs:
                fs.blit(frame, fx, fy, yhi=view_h)


def _scaled(cache, gfx, lump, kx, ky, lut, li):
    if cache is None:
        cache = _SCALED
    key = (lump, round(kx, 4), round(ky, 4), li)
    got = cache.get(key)
    if got is None:
        patch = gfx.patch(lump)
        if patch is None:
            return None
        got = ScaledPatch(patch, kx, ky, lut)
        cache[key] = got
    return got


_SCALED = {}
