"""Проверка спецлиний: лестницы, прессы, «пончик», телепорт, воскрешение."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm import wad as W, mapdata as MD, game as G, sprites as SP, sound as SND
from dm import things as TH

WAD1 = os.environ.get('DOOMWAD', r'C:\Users\Markazuk\Documents\freedoom-0.12.1\freedoom1.wad')
WAD2 = os.environ.get('DOOMWAD2', WAD1.replace('freedoom1', 'freedoom2'))
NOKEYS = lambda k: False


class Loader:
    def __init__(self, path):
        self.wad = W.Wad(path)
        self.gfx = W.Graphics(self.wad)
        self.spr = SP.SpriteSet(self.wad)
        self.snd = SND.Sound(self.wad, enabled=False)

    def game(self, mapname, skill=3):
        md = MD.MapData(self.wad, mapname)
        return G.Game(self.gfx, md, mapname, self.spr, self.snd, skill)


def run(g, seconds, dt=1.0 / 35.0):
    for _ in range(int(seconds / dt)):
        g.tick(dt, NOKEYS)


def find(loader, specials, limit=40):
    """-> (карта, линия) первой попавшейся линии с нужным спецом."""
    for name in loader.wad.maps()[:limit]:
        md = MD.MapData(loader.wad, name)
        for ln in md.lines:
            if ln.special in specials and ln.tag:
                return name, ln.special, ln.tag
    return None, None, None


def check(loader, title, specials, probe):
    name, sp, tag = find(loader, specials)
    if name is None:
        print('%-12s спецлиний не нашлось' % title)
        return
    g = loader.game(name)
    before = [(s.floor, s.ceil) for s in g.md.sectors if s.tag == tag]
    line = next(l for l in g.md.lines if l.special == sp and l.tag == tag)
    ok = g.activate(line, use=True)
    run(g, 4.0)
    after = [(s.floor, s.ceil) for s in g.md.sectors if s.tag == tag]
    moved = sum(1 for a, b in zip(before, after) if a != b)
    print('%-12s %s спец %d тег %d: сработало %s, изменилось секторов %d/%d %s'
          % (title, name, sp, tag, ok, moved, len(before), probe(g)))


def main():
    l1 = Loader(WAD1)
    print('=== %s ===' % os.path.basename(WAD1))
    check(l1, 'лестница', G.STAIRS8 | G.STAIRS16, lambda g: '')
    check(l1, 'пресс', G.CRUSHERS, lambda g: '(прессов %d)' % sum(
        1 for t in g.thinkers if getattr(t, 'crush', False)))
    check(l1, 'потолок вниз', G.CEIL_LOWER, lambda g: '')
    check(l1, 'пончик', G.DONUT, lambda g: '')

    # телепорт
    name, sp, tag = find(l1, G.TELEPORTS)
    if name:
        g = l1.game(name)
        line = next(l for l in g.md.lines if l.special == sp and l.tag == tag)
        p = g.player
        pos = (p.x, p.y)
        ok = g.activate(line, use=False)
        print('%-12s %s спец %d: сработало %s, игрок %s -> (%.0f, %.0f)'
              % ('телепорт', name, sp, ok, tuple(round(v) for v in pos), p.x, p.y))

    # воскрешение архвайлом (DOOM 2)
    if os.path.exists(WAD2):
        print('=== %s ===' % os.path.basename(WAD2))
        l2 = Loader(WAD2)
        for mapname in l2.wad.maps():
            md = MD.MapData(l2.wad, mapname)
            if not any(t.type == 64 for t in md.things):
                continue
            g = l2.game(mapname, skill=4)
            vile = next((m for m in g.mobjs if m.kind == 'monster' and m.type == 64),
                        None)
            if vile is not None:
                imp = next((m for m in g.mobjs
                            if m.kind == 'monster' and m.type != 64), None)
                if imp is None:
                    break
                imp.x, imp.y = vile.x + 60.0, vile.y
                imp.sector = g.md.sector_at(imp.x, imp.y)
                imp.hurt(10000, None)
                run(g, 1.0)
                was_dead = imp.dead
                vile.wake()
                run(g, 3.0)
                print('%-12s %s: труп %s -> воскрешён %s, здоровье %d, состояние %s'
                      % ('архвайл', mapname, was_dead, not imp.dead, imp.health,
                         imp.state))
                break


if __name__ == '__main__':
    main()
