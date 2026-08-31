"""Прогон всех карт WAD: загрузка, несколько тактов игры и кадров рендера.

  python tools/mapsweep.py [путь.wad] [тактов]
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm import term as T
from dm import wad as W
from dm import mapdata as MD
from dm import game as G
from dm import renderer as R
from dm import sprites as SP
from dm import sound as SND
from dm import hud as HUD
import doom as D

WAD = os.environ.get('DOOMWAD', r'C:\Users\Markazuk\Documents\freedoom-0.12.1\freedoom1.wad')


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else WAD
    ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    wad = W.Wad(path)
    gfx = W.Graphics(wad)
    spr = SP.SpriteSet(wad)
    snd = SND.Sound(wad, enabled=False)
    hud = HUD.Hud(gfx)
    frame = T.Frame(100, 34)
    bar = hud.bar_height(frame)
    ren = R.Renderer(gfx, frame.w, frame.h - bar, 90.0, 1.0)

    bad = 0
    t0 = time.time()
    print('%-8s %5s %5s %5s %5s %6s %6s  %s'
          % ('карта', 'сект', 'линий', 'вещей', 'монст', 'предм', 'тайн', 'статус'))
    for name in wad.maps():
        try:
            md = MD.MapData(wad, name)
            game = G.Game(gfx, md, name, spr, snd, 3)
            ren.sky_name = D.sky_for(name)
            keys = lambda k: k in ('w', 'ctrl')
            for i in range(ticks):
                game.tick(1.0 / 35.0, keys)
                if i % 8 == 0:
                    frame.clear(0)
                    ren.set_palette(game.player.palette())
                    ren.render(frame, md, game.view)
                    ren.render_things(game.mobjs, spr, game.time)
                    sec = md.sector_at(game.player.x, game.player.y)
                    HUD.draw_weapon(frame, gfx, ren, game.player, frame.h - bar,
                                    sec.light)
                    hud.draw(frame, game, 30.0)
            D.draw_automap(frame, game)
            mons = sum(1 for m in game.mobjs if m.kind == 'monster')
            status = 'ок'
        except Exception:
            bad += 1
            status = 'СБОЙ: ' + traceback.format_exc().strip().splitlines()[-1][:70]
            mons = -1
            md = None
        print('%-8s %5s %5s %5s %5s %6s %6s  %s'
              % (name,
                 len(md.sectors) if md else '-', len(md.lines) if md else '-',
                 len(md.things) if md else '-', mons if mons >= 0 else '-',
                 game.total_items if md else '-',
                 game.total_secrets if md else '-', status))
    print('\n%d карт за %.1fс, сбоев: %d' % (len(wad.maps()), time.time() - t0, bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
