"""Спрайты из WAD: индекс лампов S_START..S_END и таблица типов вещей."""
import math

TAU = math.pi * 2.0


class SpriteSet:
    """frames[база][буква кадра] = (кадр_без_поворотов, [8 поворотов])
    каждый элемент — (имя лампа, отражать_ли)."""

    def __init__(self, wad):
        self.wad = wad
        self.frames = {}
        lumps = wad.range_lumps('S_START', 'S_END')
        if not lumps:
            lumps = wad.range_lumps('SS_START', 'SS_END')
        for l in lumps:
            n = l.name
            if len(n) < 6 or l.size < 8:
                continue
            base = n[:4]
            self._add(base, n[4], n[5], n, False)
            if len(n) >= 8:
                self._add(base, n[6], n[7], n, True)

    def _add(self, base, frame, rot, lump, flip):
        d = self.frames.setdefault(base, {})
        e = d.get(frame)
        if e is None:
            e = [None, [None] * 8]
            d[frame] = e
        if rot == '0':
            e[0] = (lump, flip)
        elif '1' <= rot <= '8':
            e[1][ord(rot) - 49] = (lump, flip)

    def has(self, base):
        return base in self.frames

    def frame_letters(self, base):
        d = self.frames.get(base)
        return sorted(d) if d else []

    def pick(self, base, frame, view_angle_to_thing, thing_angle):
        """-> (имя лампа, отражать) с учётом поворота спрайта."""
        d = self.frames.get(base)
        if not d:
            return None
        e = d.get(frame)
        if e is None:
            k = sorted(d)
            if not k:
                return None
            e = d[k[0]]
        if e[0] is not None and e[1][0] is None:
            return e[0]
        a = (view_angle_to_thing - thing_angle + math.pi / 8.0) % TAU
        rot = int(a / (TAU / 8.0)) & 7
        got = e[1][rot]
        if got is None:
            for r in e[1]:
                if r is not None:
                    got = r
                    break
        return got or e[0]


# ------------------------------------------------------------------ вещи
# тип -> (спрайт, висит_ли_под_потолком, анимировать_ли, полная_яркость)
M = True    # монстр/анимируется
H = True    # висит под потолком

THINGS = {
    # игроки и монстры
    3004: ('POSS', 0, M, 0), 9: ('SPOS', 0, M, 0), 65: ('CPOS', 0, M, 0),
    3001: ('TROO', 0, M, 0), 3002: ('SARG', 0, M, 0), 58: ('SARG', 0, M, 0),
    3005: ('HEAD', 0, M, 0), 3006: ('SKUL', 0, M, 1), 69: ('BOS2', 0, M, 0),
    3003: ('BOSS', 0, M, 0), 68: ('BSPI', 0, M, 0), 71: ('PAIN', 0, M, 0),
    66: ('SKEL', 0, M, 0), 67: ('FATT', 0, M, 0), 64: ('VILE', 0, M, 0),
    72: ('KEEN', H, 0, 0), 7: ('SPID', 0, M, 0), 16: ('CYBR', 0, M, 0),
    84: ('SSWV', 0, M, 0), 88: ('BBRN', 0, M, 0),
    # оружие и патроны
    2005: ('CSAW', 0, 0, 0), 2001: ('SHOT', 0, 0, 0), 82: ('SGN2', 0, 0, 0),
    2002: ('MGUN', 0, 0, 0), 2003: ('LAUN', 0, 0, 0), 2004: ('PLAS', 0, 0, 0),
    2006: ('BFUG', 0, 0, 0), 2007: ('CLIP', 0, 0, 0), 2048: ('AMMO', 0, 0, 0),
    2010: ('ROCK', 0, 0, 0), 2046: ('BROK', 0, 0, 0), 2047: ('CELL', 0, 0, 0),
    17: ('CELP', 0, 0, 0), 2008: ('SHEL', 0, 0, 0), 2049: ('SBOX', 0, 0, 0),
    8: ('BPAK', 0, 0, 0),
    # здоровье, броня, артефакты
    2011: ('STIM', 0, 0, 0), 2012: ('MEDI', 0, 0, 0), 2014: ('BON1', 0, M, 1),
    2015: ('BON2', 0, M, 1), 2018: ('ARM1', 0, M, 1), 2019: ('ARM2', 0, M, 1),
    2013: ('SOUL', 0, M, 1), 2022: ('PINV', 0, M, 1), 2023: ('PSTR', 0, M, 1),
    2024: ('PINS', 0, M, 1), 2025: ('SUIT', 0, 0, 1), 2026: ('PMAP', 0, M, 1),
    2045: ('PVIS', 0, M, 1),
    # ключи
    5: ('BKEY', 0, M, 1), 6: ('YKEY', 0, M, 1), 13: ('RKEY', 0, M, 1),
    40: ('BSKU', 0, M, 1), 39: ('YSKU', 0, M, 1), 38: ('RSKU', 0, M, 1),
    # декорации
    2035: ('BAR1', 0, M, 0), 48: ('ELEC', 0, 0, 0), 30: ('COL1', 0, 0, 0),
    31: ('COL2', 0, 0, 0), 32: ('COL3', 0, 0, 0), 33: ('COL4', 0, 0, 0),
    37: ('COL6', 0, 0, 0), 36: ('COL5', 0, M, 0), 41: ('CEYE', 0, M, 0),
    42: ('FSKU', 0, M, 1), 43: ('TRE1', 0, 0, 0), 54: ('TRE2', 0, 0, 0),
    47: ('SMIT', 0, 0, 0), 2028: ('COLU', 0, 0, 1), 85: ('TLMP', 0, M, 1),
    86: ('TLP2', 0, M, 1), 34: ('CAND', 0, 0, 1), 35: ('CBRA', 0, 0, 1),
    44: ('TBLU', 0, M, 1), 45: ('TGRN', 0, M, 1), 46: ('TRED', 0, M, 1),
    55: ('SMBT', 0, M, 1), 56: ('SMGT', 0, M, 1), 57: ('SMRT', 0, M, 1),
    70: ('FCAN', 0, M, 1),
    49: ('GOR1', H, M, 0), 50: ('GOR2', H, 0, 0), 51: ('GOR3', H, 0, 0),
    52: ('GOR4', H, 0, 0), 53: ('GOR5', H, 0, 0), 59: ('GOR2', H, 0, 0),
    60: ('GOR4', H, 0, 0), 61: ('GOR3', H, 0, 0), 62: ('GOR5', H, 0, 0),
    63: ('GOR1', H, M, 0),
    25: ('POL1', 0, 0, 0), 26: ('POL6', 0, M, 0), 27: ('POL4', 0, 0, 0),
    28: ('POL2', 0, 0, 0), 29: ('POL3', 0, M, 0), 24: ('POL5', 0, 0, 0),
    10: ('PLAY', 0, 0, 0), 12: ('PLAY', 0, 0, 0), 15: ('PLAY', 0, 0, 0),
    18: ('POSS', 0, 0, 0), 19: ('SPOS', 0, 0, 0), 20: ('TROO', 0, 0, 0),
    21: ('SARG', 0, 0, 0), 22: ('HEAD', 0, 0, 0), 23: ('SKUL', 0, 0, 0),
    79: ('POB1', 0, 0, 0), 80: ('POB2', 0, 0, 0), 81: ('BRS1', 0, 0, 0),
    73: ('HDB1', H, 0, 0), 74: ('HDB2', H, 0, 0), 75: ('HDB3', H, 0, 0),
    76: ('HDB4', H, 0, 0), 77: ('HDB5', H, 0, 0), 78: ('HDB6', H, 0, 0),
}

# у трупов из таблицы выше кадр не 'A', а последний кадр смерти
CORPSE_FRAME = {10: 'M', 12: 'M', 15: 'N', 18: 'L', 19: 'M', 20: 'M',
                21: 'N', 22: 'L', 23: 'K', 24: 'A'}

MONSTER_TYPES = {3004, 9, 65, 3001, 3002, 58, 3005, 3006, 69, 3003, 68, 71,
                 66, 67, 64, 7, 16, 84, 88}

# радиусы (для столкновений с декором и монстрами)
RADIUS = {3004: 20, 9: 20, 65: 20, 3001: 20, 3002: 30, 58: 30, 3005: 31,
          3006: 16, 69: 24, 3003: 24, 68: 64, 71: 31, 66: 20, 67: 48,
          64: 20, 7: 128, 16: 40, 84: 20, 2035: 10, 30: 16, 31: 16, 32: 16,
          33: 16, 36: 16, 37: 16, 43: 16, 54: 32, 47: 16, 2028: 16, 48: 16,
          85: 16, 86: 16, 35: 16, 34: 16, 41: 16, 28: 16, 29: 16, 25: 16,
          26: 16, 27: 16}
