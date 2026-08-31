"""Спецэффекты секторов: мигание и свечение света, повреждающий пол, секреты."""
import random

# спец сектора -> урон за «тик» (каждые 0.9 с)
DAMAGE = {4: 20, 5: 10, 7: 5, 11: 20, 16: 20}
SECRET = 9

STROBE_FAST = (5.0 / 35.0, 15.0 / 35.0)
STROBE_SLOW = (5.0 / 35.0, 35.0 / 35.0)


class LightFX:
    __slots__ = ('sec', 'kind', 'hi', 'lo', 'timer', 'on', 'phase')

    def __init__(self, sec, kind, lo):
        self.sec = sec
        self.kind = kind
        self.hi = sec.light
        self.lo = lo
        self.on = True
        self.phase = random.random() * 6.28
        self.timer = random.random() * 0.5

    def tick(self, dt):
        k = self.kind
        s = self.sec
        if k == 'glow':
            self.phase += dt * 1.6
            import math
            f = (math.sin(self.phase) + 1.0) * 0.5
            s.light = int(self.lo + (self.hi - self.lo) * f)
        elif k == 'fire':
            self.timer -= dt
            if self.timer <= 0.0:
                self.timer = 4.0 / 35.0
                amt = random.randint(0, 3) * 16
                s.light = max(self.lo, self.hi - amt)
        else:
            self.timer -= dt
            if self.timer <= 0.0:
                self.on = not self.on
                bright, dark = STROBE_FAST if k == 'fast' else STROBE_SLOW
                if k == 'rand':
                    self.timer = random.random() * 0.5 + 0.05
                else:
                    self.timer = bright if self.on else dark
                s.light = self.hi if self.on else self.lo


def min_neighbour_light(sec):
    lo = sec.light
    for ln in sec.lines:
        for sd in (ln.front, ln.back):
            if sd is not None and sd.sector is not sec:
                if sd.sector.light < lo:
                    lo = sd.sector.light
    return lo


def build_lights(md):
    out = []
    for s in md.sectors:
        sp = s.special
        kind = None
        if sp in (1, 17):
            kind = 'fire'
        elif sp in (2, 13):
            kind = 'fast'
        elif sp in (3, 12):
            kind = 'slow'
        elif sp == 4:
            kind = 'fast'
        elif sp == 8:
            kind = 'glow'
        if kind:
            out.append(LightFX(s, kind, min_neighbour_light(s)))
    return out
