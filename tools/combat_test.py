"""Проверка боевой части без терминала: пробуждение, стрельба, урон, предметы."""
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm import wad as W, mapdata as MD, game as G, sprites as SP, sound as SND
from dm import things as TH

WAD = os.environ.get('DOOMWAD', r'C:\Users\Markazuk\Documents\freedoom-0.12.1\freedoom1.wad')
NOKEYS = lambda k: False


def build(mapname='E1M1'):
    wad = W.Wad(WAD)
    gfx = W.Graphics(wad)
    spr = SP.SpriteSet(wad)
    snd = SND.Sound(wad, enabled=False)
    md = MD.MapData(wad, mapname)
    return G.Game(gfx, md, mapname, spr, snd, 3)


def run(g, seconds, keys=NOKEYS, dt=1.0 / 35.0):
    for _ in range(int(seconds / dt)):
        g.tick(dt, keys)


def main():
    g = build()
    p = g.player
    mons = [m for m in g.mobjs if m.kind == 'monster']
    print('монстров: %d, предметов: %d, всего объектов: %d'
          % (len(mons), sum(1 for m in g.mobjs if m.kind == 'item'), len(g.mobjs)))

    # 1. поставить игрока перед монстром и посмотреть, проснётся ли он
    m = mons[0]
    p.x = m.x - math.cos(m.angle) * 200.0
    p.y = m.y - math.sin(m.angle) * 200.0
    p.z = g.md.sector_at(p.x, p.y).floor
    p.angle = m.angle
    m.angle = math.atan2(p.y - m.y, p.x - m.x)
    run(g, 1.0)
    print('1) %s: состояние %s, дистанция %.0f' % (m.sprite, m.state, m.dist_to(p)))

    # 2. расстрелять его из дробовика
    p.have.add(2)
    p.ammo['shell'] = 50
    p.weapon = 2
    p.wstate = 'ready'
    shots = 0
    for _ in range(400):
        g.tick(1.0 / 35.0, lambda k: k == 'ctrl')
        if p.wstate == 'fire' and p.wi == 1:
            shots += 1
        if m.dead:
            break
    print('2) убит: %s, здоровье монстра %d, кадр %s, убито в счётчике %d'
          % (m.dead, m.health, m.frame, g.kills))

    # 3. урон игроку от монстра ближнего боя
    g2 = build()
    p2 = g2.player
    sarg = next((x for x in g2.mobjs if x.kind == 'monster' and x.sprite == 'SARG'), None)
    if sarg:
        p2.x, p2.y = sarg.x + 50.0, sarg.y
        p2.z = g2.md.sector_at(p2.x, p2.y).floor
        sarg.wake()
        run(g2, 4.0)
        print('3) демон: состояние %s, здоровье игрока %d, палитра %d'
              % (sarg.state, p2.health, p2.palette()))

    # 4. снаряд импа
    g3 = build()
    p3 = g3.player
    troo = next((x for x in g3.mobjs if x.kind == 'monster' and x.sprite == 'TROO'), None)
    if troo:
        p3.x, p3.y = troo.x + 400.0, troo.y
        p3.z = g3.md.sector_at(p3.x, p3.y).floor
        troo.wake()
        troo.threshold = 0.0
        run(g3, 6.0)
        miss = [x for x in g3.mobjs if x.kind == 'missile']
        print('4) имп: состояние %s, снарядов в воздухе %d, здоровье игрока %d'
              % (troo.state, len(miss), p3.health))

    # 5. подбор предметов
    g4 = build()
    p4 = g4.player
    p4.health = 50
    taken = 0
    for it in [x for x in g4.mobjs if x.kind == 'item'][:12]:
        p4.x, p4.y, p4.z = it.x, it.y, it.sector.floor
        g4.tick(0.03, NOKEYS)
        if it.remove:
            taken += 1
    print('5) подобрано %d/12, здоровье %d, броня %d, патроны %s, оружие %s'
          % (taken, p4.health, p4.armor, p4.ammo, sorted(p4.have)))

    # 6. двери и переключатели
    g5 = build()
    opened = 0
    for ln in g5.md.lines:
        if ln.special in G.DOOR_MANUAL and ln.back is not None:
            if g5.open_door(ln.back.sector):
                opened += 1
    run(g5, 2.0)
    print('6) открыто дверей: %d, активных обработчиков %d' % (opened, len(g5.thinkers)))

    # 7. ракета и урон по площади
    g6 = build()
    p6 = g6.player
    p6.have.add(4)
    p6.ammo['rckt'] = 5
    p6.weapon = 4
    p6.wstate = 'ready'
    run(g6, 1.5, lambda k: k == 'ctrl')
    print('7) ракет выпущено: осталось %d, объектов-снарядов %d'
          % (p6.ammo['rckt'], sum(1 for x in g6.mobjs if x.kind == 'missile')))

    # 8. бочка
    g7 = build()
    bar = next((x for x in g7.mobjs if x.type == TH.BARREL), None)
    if bar:
        bar.hurt(50, None)
        run(g7, 1.0)
        print('8) бочка: мертва %s, кадр %s' % (bar.dead, bar.frame))


    # 9. драка монстров между собой
    g8 = build()
    mons8 = [x for x in g8.mobjs if x.kind == 'monster']
    imp = next(x for x in mons8 if x.sprite == 'TROO')
    dem = next(x for x in mons8 if x.sprite == 'SARG')
    dem.x, dem.y = imp.x + 220.0, imp.y
    dem.sector = g8.md.sector_at(dem.x, dem.y)
    dem.z = dem.sector.floor
    hp0 = dem.health
    imp.wake()
    imp.target = dem
    imp.threshold = 0.0
    imp.set_seq(imp.info['atk'], 'attack')
    run(g8, 3.0)
    print('9) имп -> демон: цель демона %s, здоровье демона %d -> %d, '
          'здоровье импа %d'
          % ('имп' if dem.target is imp else str(dem.target), hp0, dem.health,
             imp.health))


if __name__ == '__main__':
    main()
