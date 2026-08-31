#!/usr/bin/env python3
"""TerminalDoom — движок DOOM, читающий настоящие WAD-файлы, с выводом в терминал.

  python doom.py                     # первая найденная карта
  python doom.py --map E1M3 --skill 4
  python doom.py --wad path/to/doom2.wad --map MAP01
  python doom.py --bench 60          # замер скорости без терминала
"""
import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dm import term as T
from dm import wad as W
from dm import mapdata as MD
from dm import game as G
from dm import renderer as R
from dm import sprites as SP
from dm import sound as SND
from dm import hud as HUD

SEARCH = [
    os.environ.get('DOOMWAD', ''),
    r'C:\Users\%s\Documents\freedoom-0.12.1\freedoom1.wad' % os.environ.get('USERNAME', ''),
    r'C:\Users\%s\Documents\freedoom-0.12.1\freedoom2.wad' % os.environ.get('USERNAME', ''),
    'freedoom1.wad', 'doom.wad', 'doom1.wad', 'doom2.wad', 'DOOM.WAD', 'DOOM1.WAD',
]

WEAPON_KEYS = {'1': (0, 7), '2': (1,), '3': (2, 8), '4': (3,),
               '5': (4,), '6': (5,), '7': (6,)}


def find_wad(explicit=None):
    cands = [explicit] if explicit else SEARCH
    for c in cands:
        if c and os.path.isfile(c):
            return c
    for name in os.listdir('.'):
        if name.lower().endswith('.wad'):
            return name
    raise SystemExit('WAD не найден. Укажи путь: python doom.py --wad <файл.wad>')


def sky_for(mapname):
    if mapname.startswith('E'):
        return 'SKY' + mapname[1]
    try:
        n = int(mapname[3:])
    except ValueError:
        return 'SKY1'
    return 'SKY1' if n < 12 else ('SKY2' if n < 21 else 'SKY3')


def draw_automap(frame, game):
    """Карта уровня: линии стен, повёрнутые по взгляду игрока."""
    md = game.md
    p = game.player
    w, h = frame.w, frame.h
    cx, cy = w * 0.5, h * 0.5
    minx, miny, maxx, maxy = md.bounds
    scale = min(w / max(1.0, maxx - minx), h / max(1.0, maxy - miny)) * 2.6
    ca = math.cos(-p.angle + math.pi / 2)
    sa = math.sin(-p.angle + math.pi / 2)
    pix = frame.pix

    def to_screen(x, y):
        dx = (x - p.x) * scale
        dy = (y - p.y) * scale
        return cx + (dx * ca - dy * sa), cy - (dx * sa + dy * ca)

    def line(x0, y0, x1, y1, c):
        x0 = int(x0); y0 = int(y0); x1 = int(x1); y1 = int(y1)
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        n = 0
        while n < 4000:
            n += 1
            if 0 <= x0 < w and 0 <= y0 < h:
                pix[y0 * w + x0] = c
            if x0 == x1 and y0 == y1:
                break
            e2 = err * 2
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    frame.clear(0x000000)
    for ln in md.lines:
        if ln.flags & MD.ML_DONTDRAW:
            continue
        if ln.back is None or not (ln.flags & MD.ML_TWOSIDED):
            c = 0xC02020
        else:
            f, b = ln.front.sector, ln.back.sector
            if f.floor != b.floor:
                c = 0xB07020
            elif f.ceil != b.ceil:
                c = 0x707060
            else:
                continue
        ax, ay = to_screen(*ln.v1)
        bx, by = to_screen(*ln.v2)
        if max(ax, bx) < -50 or min(ax, bx) > w + 50:
            continue
        if max(ay, by) < -50 or min(ay, by) > h + 50:
            continue
        line(ax, ay, bx, by, c)
    for m in game.mobjs:
        if m.kind == 'monster' and not m.dead:
            x, y = to_screen(m.x, m.y)
            if 0 <= x < w and 0 <= y < h:
                line(x - 1, y, x + 1, y, 0xFF4040)
                line(x, y - 1, x, y + 1, 0xFF4040)
    line(cx, cy - 4, cx, cy + 4, 0xFFFFFF)
    line(cx - 3, cy + 3, cx, cy - 4, 0xFFFFFF)
    line(cx + 3, cy + 3, cx, cy - 4, 0xFFFFFF)


class App:
    def __init__(self, args):
        self.args = args
        self.path = find_wad(args.wad)
        self.wad = W.Wad(self.path)
        self.gfx = W.Graphics(self.wad)
        self.sprset = SP.SpriteSet(self.wad)
        self.sound = SND.Sound(self.wad, enabled=not args.nosound)
        self.music = SND.Music(self.wad, enabled=not args.nomusic)
        self.mouse = None
        if args.mouse and T.IS_WIN:
            try:
                self.mouse = T.Mouse()
                self.mouse.set(True)
            except Exception:
                self.mouse = None
        self.maps = self.wad.maps()
        if not self.maps:
            raise SystemExit('в WAD нет карт')
        name = (args.map or self.maps[0]).upper()
        if name not in self.maps:
            raise SystemExit('карты %s нет. Есть: %s' %
                             (name, ', '.join(self.maps[:12]) + ' ...'))
        self.hud = HUD.Hud(self.gfx)
        self.frame = None
        self.ren = None
        self.load(name)

    def load(self, name):
        self.md = MD.MapData(self.wad, name)
        self.game = G.Game(self.gfx, self.md, name, self.sprset, self.sound,
                           self.args.skill)
        if self.ren is not None:
            self.ren.sky_name = sky_for(name)
        self.music.play_map(name)
        self.state = 'play'

    def next_map(self):
        i = (self.maps.index(self.game.mapname) + 1) % len(self.maps)
        self.load(self.maps[i])

    def resize(self, cols, rows):
        self.frame = T.Frame(cols, rows)
        self.bar_h = self.hud.bar_height(self.frame)
        self.view_h = self.frame.h - self.bar_h
        if self.ren is None:
            self.ren = R.Renderer(self.gfx, self.frame.w, self.view_h,
                                  self.args.fov, self.args.aspect)
        else:
            self.ren.setup(self.frame.w, self.view_h)
        self.ren.sky_name = sky_for(self.game.mapname)

    # ------------------------------------------------------------ кадр
    def draw(self, fps):
        frame = self.frame
        game = self.game
        if self.state == 'intermission':
            self.hud.intermission(frame, game)
            return
        if game.automap:
            draw_automap(frame, game)
        else:
            p = game.player
            lim = self.view_h * 0.45
            pitch = p.pitch * self.ren.projy
            game.view.pitch = lim if pitch > lim else (-lim if pitch < -lim else pitch)
            self.ren.set_palette(p.palette())
            frame.clear(0x000000)
            self.ren.render(frame, self.md, game.view)
            self.ren.render_things(game.mobjs, self.sprset, game.time)
            sec = self.md.sector_at(p.x, p.y)
            HUD.draw_weapon(frame, self.gfx, self.ren, p, self.view_h, sec.light)
        self.hud.draw(frame, game, fps)

    # ------------------------------------------------------------ ввод
    def input(self, inp):
        game = self.game
        p = game.player
        if self.state == 'intermission':
            if inp.hit('space') or inp.hit('enter'):
                self.next_map()
            return True
        if inp.hit('tab') or inp.hit('m'):
            game.automap = not game.automap
        if inp.hit('space') or inp.hit('mouse2'):
            if not game.use():
                self.sound.play('DSNOWAY', 1)
        if inp.hit('k') and self.mouse is not None:
            self.mouse.set(not self.mouse.enabled)
            game.say('мышь: ' + ('вкл' if self.mouse.enabled else 'выкл'))
        if self.mouse is not None and self.mouse.enabled:
            dx, dy = self.mouse.poll()
            p.mouse_dx += dx
            p.mouse_dy += dy
        if inp.hit('r'):
            self.load(game.mapname)
            return True
        if inp.hit('n'):
            self.next_map()
            return True
        for k, ids in WEAPON_KEYS.items():
            if inp.hit(k):
                for i in ids:
                    if p.weapon_ok(i) and i != p.weapon:
                        p.switch_to(i)
                        break
        if inp.hit('x'):
            p.next_weapon(1)
        if inp.hit('z'):
            p.next_weapon(-1)
        if inp.hit('g'):
            game.noclip = not game.noclip
            game.say('режим сквозь стены: ' + ('вкл' if game.noclip else 'выкл'))
        return True

    def tick(self, dt, inp):
        self.music.update(dt)
        if self.state == 'intermission':
            return
        self.game.tick(dt, inp.down)
        if self.game.exit_level:
            self.game.exit_level = False
            self.state = 'intermission'
            self.sound.play('DSPSTOP', 3)


def bench(app, args):
    cols, rows = (120, 40)
    if args.size:
        cols, rows = (int(v) for v in args.size.lower().split('x'))
    app.resize(cols, rows)
    frame = app.frame
    t0 = time.time()
    for i in range(args.bench):
        app.game.view.angle = i * 0.05
        frame.clear(0)
        app.ren.render(frame, app.md, app.game.view)
        app.ren.render_things(app.game.mobjs, app.sprset, i * 0.03)
    dt = time.time() - t0
    print('%s %dx%d (%dx%d пикс): %d кадров за %.2fс = %.1f к/с (мир + спрайты)'
          % (app.game.mapname, cols, rows, frame.w, frame.h, args.bench,
             dt, args.bench / dt))
    import io
    n = max(1, args.bench // 2)
    real = sys.stdout
    sys.stdout = io.StringIO()
    t0 = time.time()
    for i in range(n):
        frame.flush()
    el = time.time() - t0
    size = len(sys.stdout.getvalue()) // n
    sys.stdout = real
    print('сборка кадра для терминала: %.1f к/с, %d Кб на кадр' % (n / el, size // 1024))


class ScriptInput:
    """Бот для самотеста: идёт, крутится, стреляет, жмёт «использовать»."""

    def __init__(self):
        self.n = 0

    def poll(self):
        self.n += 1

    def down(self, k):
        if k in ('w', 'shift'):
            return True
        if k == 'ctrl':
            return (self.n // 7) % 3 == 0
        if k == 'left':
            return (self.n // 25) % 2 == 0
        if k == 'right':
            return (self.n // 25) % 2 == 1
        return False

    def hit(self, k):
        if k == 'space':
            return self.n % 13 == 0
        if k == '3':
            return self.n == 30
        return False

    def restore(self):
        pass


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--wad', default=None)
    ap.add_argument('--map', default=None)
    ap.add_argument('--skill', type=int, default=3, help='1..5, по умолчанию 3')
    ap.add_argument('--fov', type=float, default=90.0)
    ap.add_argument('--aspect', type=float, default=1.0)
    ap.add_argument('--nosound', action='store_true')
    ap.add_argument('--nomusic', action='store_true')
    ap.add_argument('--mouse', action='store_true', help='управление мышью')
    ap.add_argument('--bench', type=int, default=0)
    ap.add_argument('--selftest', type=int, default=0)
    ap.add_argument('--size', default=None, help='например 120x40')
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    if args.bench or args.selftest:          # в тестовых режимах не шумим
        args.nosound = True
        args.nomusic = True

    app = App(args)
    if args.bench:
        bench(app, args)
        return

    con = T.Console()
    limit = args.selftest or -1
    if args.selftest:
        import io
        inp = ScriptInput()
        app.sound.enabled = False
        real_stdout = sys.stdout
        sys.stdout = io.StringIO()
    else:
        inp = T.make_input()
    con.setup()
    try:
        cols, rows = con.size()
        if args.size:
            cols, rows = (int(v) for v in args.size.lower().split('x'))
        app.resize(cols, rows)
        app.game.say('%s — %s' % (app.game.mapname, os.path.basename(app.path)))

        last = time.time()
        fps = 0.0
        acc = 0.0
        frames = 0
        check = 0
        while limit != 0:
            limit -= 1
            now = time.time()
            dt = now - last
            last = now
            if dt > 0.1:
                dt = 0.1
            acc += dt
            frames += 1
            if acc >= 0.5:
                fps = frames / acc
                acc = 0.0
                frames = 0

            inp.poll()
            if inp.down('esc'):
                break
            app.input(inp)
            app.tick(dt, inp)

            check += 1
            if check % 30 == 0 and not args.size:
                c, r = con.size()
                if (c, r) != (app.frame.cols, app.frame.rows):
                    app.resize(c, r)

            app.draw(fps)
            app.frame.flush()

            if args.selftest:
                continue
            slack = 1.0 / 35.0 - (time.time() - now)
            if slack > 0.002:
                time.sleep(slack)
    finally:
        try:
            inp.restore()
        except Exception:
            pass
        app.sound.stop()
        app.music.close()
        if app.mouse is not None:
            app.mouse.set(False)
        con.restore()
        if args.selftest:
            sys.stdout = real_stdout
            g = app.game
            p = g.player
            print('самотест: %d кадров, %s, позиция (%.0f, %.0f), здоровье %d, '
                  'убито %d/%d, объектов %d, обработчиков %d — сбоев нет'
                  % (args.selftest, g.mapname, p.x, p.y, p.health, g.kills,
                     g.total_kills, len(g.mobjs), len(g.thinkers)))


if __name__ == '__main__':
    main()
