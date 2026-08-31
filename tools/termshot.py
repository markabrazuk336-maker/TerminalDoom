"""Отладка: кадр игры в терминальном разрешении -> PNG (с увеличением).

  python tools/termshot.py [карта] [колонки] [строки] [шагов] [map|fire]
"""
import os
import sys
import argparse
from array import array

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import doom as D
from tools.shot import write_png


def main():
    mapname = sys.argv[1] if len(sys.argv) > 1 else 'E1M1'
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    steps = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    mode = sys.argv[5] if len(sys.argv) > 5 else ''

    args = argparse.Namespace(wad=None, map=mapname, skill=3, fov=90.0,
                              aspect=1.0, nosound=True, bench=0, selftest=0,
                              size=None)
    app = D.App(args)
    app.resize(cols, rows)
    game = app.game
    p = game.player

    keys = lambda k: k in ('w',)
    for _ in range(steps):
        game.tick(1.0 / 35.0, keys)
    if mode == 'fire':
        p.have.add(2)
        p.ammo['shell'] = 20
        p.weapon = 2
        p.wstate = 'ready'
        for _ in range(8):
            game.tick(1.0 / 35.0, lambda k: k == 'ctrl')
    game.tick(0.01, lambda k: False)
    game.automap = (mode == 'map')
    game.say('ТЕРМИНАЛЬНЫЙ DOOM')
    app.draw(30.0)

    frame = app.frame
    k = 5
    big = array('i', [0]) * (frame.w * k * frame.h * k)
    for y in range(frame.h):
        for x in range(frame.w):
            c = frame.pix[y * frame.w + x]
            for j in range(k):
                o = (y * k + j) * frame.w * k + x * k
                for i in range(k):
                    big[o + i] = c
    out = 'term_%s.png' % mapname.lower()
    write_png(out, frame.w * k, frame.h * k, big)
    print('%s %dx%d -> %s | полоса %d пикс, вид %d пикс | здоровье %d, оружие %s'
          % (mapname, cols, rows, out, app.bar_h, app.view_h, p.health,
             p.weapon))


if __name__ == '__main__':
    main()
