"""Мир: игрок, монстры, предметы, двери, лифты, спецлинии, статистика уровня."""
import math
import random

from . import mapdata as MD
from . import things as TH
from . import mobj as MO
from . import specials as SPEC
from .player import Player, WEAPONS
from .renderer import View

RADIUS = 16.0
HEIGHT = 56.0
MAX_STEP = 24.0
USE_RANGE = 74.0

DOOR_MANUAL = {1, 26, 27, 28, 31, 32, 33, 34, 117, 118}
DOOR_OPEN_WAIT = {4, 29, 63, 90, 105, 108, 111, 114}
DOOR_OPEN_STAY = {2, 31, 61, 86, 103, 106, 109, 112, 115, 118, 133, 135, 137}
DOOR_CLOSE = {3, 16, 42, 50, 75, 76, 107, 110, 113, 116}
LIFTS = {10, 21, 62, 88, 120, 121, 122, 123}
FLOOR_RAISE = {5, 24, 64, 91, 101, 18, 69, 119, 128, 129, 130, 131}
FLOOR_LOWER = {19, 23, 36, 37, 38, 45, 60, 70, 82, 83, 84, 102}
EXITS = {11, 51, 52, 124}
TELEPORTS = {39, 97, 125, 126}
KEYED = {26: 'blue', 32: 'blue', 99: 'blue', 133: 'blue',
         27: 'yellow', 34: 'yellow', 136: 'yellow', 137: 'yellow',
         28: 'red', 33: 'red', 134: 'red', 135: 'red'}

ITEM_COUNTED = {'health_bonus', 'armor_bonus', 'soul', 'power_inv', 'berserk',
                'power_invis', 'power_suit', 'power_map', 'power_light'}


class Door:
    def __init__(self, sector, top, speed=110.0, wait=4.0, closing=False):
        self.sector = sector
        self.top = top
        self.bottom = sector.floor
        self.speed = speed
        self.wait = wait
        self.timer = 0.0
        self.dir = -1 if closing else 1
        self.done = False

    def tick(self, dt, game):
        s = self.sector
        if self.dir == 1:
            s.ceil += self.speed * dt
            if s.ceil >= self.top:
                s.ceil = self.top
                if self.wait <= 0.0:
                    self.done = True
                else:
                    self.dir = 0
                    self.timer = self.wait
        elif self.dir == 0:
            self.timer -= dt
            if self.timer <= 0.0:
                self.dir = -1
                game.sound.play('DSDORCLS', 1)
        else:
            p = game.player
            if game.md.sector_at(p.x, p.y) is s and s.ceil < p.z + HEIGHT + 8:
                self.dir = 1                       # не давим игрока
                return
            s.ceil -= self.speed * dt
            if s.ceil <= self.bottom + 4.0:
                s.ceil = self.bottom + 4.0
                self.done = True


class Plat:
    def __init__(self, sector, low, high, speed=80.0, wait=3.0, once=False):
        self.sector = sector
        self.low = low
        self.high = high
        self.speed = speed
        self.wait = wait
        self.timer = 0.0
        self.dir = -1
        self.once = once
        self.done = False

    def tick(self, dt, game):
        s = self.sector
        if self.dir == -1:
            s.floor -= self.speed * dt
            if s.floor <= self.low:
                s.floor = self.low
                if self.once:
                    self.done = True
                else:
                    self.dir = 0
                    self.timer = self.wait
        elif self.dir == 0:
            self.timer -= dt
            if self.timer <= 0.0:
                self.dir = 1
                game.sound.play('DSPSTART', 1)
        else:
            s.floor += self.speed * dt
            if s.floor >= self.high:
                s.floor = self.high
                self.done = True


class FloorMove:
    def __init__(self, sector, target, speed=50.0):
        self.sector = sector
        self.target = target
        self.speed = speed if target > sector.floor else -speed
        self.done = False

    def tick(self, dt, game):
        s = self.sector
        s.floor += self.speed * dt
        if (self.speed > 0 and s.floor >= self.target) or \
           (self.speed < 0 and s.floor <= self.target):
            s.floor = self.target
            self.done = True


class Game:
    def __init__(self, gfx, md, mapname, sprset, sound, skill=3):
        self.gfx = gfx
        self.md = md
        self.mapname = mapname
        self.sprset = sprset
        self.sound = sound
        self.skill = skill
        self.time = 0.0
        self.exit_level = False
        self.finished = False
        self.automap = False
        self.noclip = False
        self.messages = []
        self.msg_time = 0.0
        self.thinkers = []
        self.busy = {}
        self.kills = 0
        self.total_kills = 0
        self.total_items = 0
        self.total_secrets = sum(1 for s in md.sectors if s.special == SPEC.SECRET)
        self.lights = SPEC.build_lights(md)
        self.hurt_t = 0.0

        st = md.player_start(1)
        sec = md.sector_at(st.x, st.y)
        self.player = Player(self, st.x, st.y, st.angle, sec)
        self.view = View(st.x, st.y, sec.floor + 41.0, st.angle)

        self.mobjs = []
        self.blockers = []
        self.bgrid = {}
        self.spawn_things()
        self.rebuild_bgrid()

    # ------------------------------------------------------------ создание
    def spawn_things(self):
        skill_bit = {1: 1, 2: 1, 3: 2, 4: 4, 5: 4}.get(self.skill, 2)
        for t in self.md.things:
            if t.flags & 16:
                continue
            if (t.flags & 7) and not (t.flags & skill_bit):
                continue
            m = None
            if t.type in TH.MONSTERS:
                m = MO.spawn_monster(self, t, self.sprset)
                if m is not None:
                    self.total_kills += 1
            elif t.type in TH.ITEMS:
                m = MO.spawn_item(self, t, self.sprset)
                if m is not None and m.item[0] in ITEM_COUNTED:
                    self.total_items += 1
            else:
                m = MO.spawn_decor(self, t, self.sprset, self.gfx)
            if m is not None:
                self.mobjs.append(m)
                if m.solid:
                    self.blockers.append(m)

    def rebuild_bgrid(self):
        """Сетка твёрдых объектов 128x128 — чтобы не перебирать всю карту."""
        grid = {}
        for o in self.blockers:
            if o.remove or not o.solid:
                continue
            key = (int(o.x) >> 7, int(o.y) >> 7)
            lst = grid.get(key)
            if lst is None:
                grid[key] = [o]
            else:
                lst.append(o)
        self.bgrid = grid

    def blockers_near(self, x, y):
        cx = int(x) >> 7
        cy = int(y) >> 7
        out = []
        g = self.bgrid
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                lst = g.get((cx + i, cy + j))
                if lst:
                    out.extend(lst)
        return out

    # ------------------------------------------------------------ сообщения
    def say(self, text):
        self.messages = [text]
        self.msg_time = 3.5

    # ------------------------------------------------------------ геометрия
    @staticmethod
    def _dist_to_line(px, py, line):
        x1, y1 = line.v1
        dx, dy = line.dx, line.dy
        L2 = dx * dx + dy * dy
        if L2 == 0.0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / L2
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        return math.hypot(px - (x1 + dx * t), py - (y1 + dy * t))

    def _line_block(self, line, z):
        if not (line.flags & MD.ML_TWOSIDED) or line.back is None or line.front is None:
            return True
        if line.flags & MD.ML_BLOCKING:
            return True
        f = line.front.sector
        b = line.back.sector
        low = max(f.floor, b.floor)
        high = min(f.ceil, b.ceil)
        if high - low < HEIGHT:
            return True
        if low - z > MAX_STEP:
            return True
        return False

    def can_stand(self, x, y, z):
        for ln in self.md.lines_near(x, y, RADIUS + 8.0):
            if self._dist_to_line(x, y, ln) < RADIUS and self._line_block(ln, z):
                return False
        for o in self.blockers_near(x, y):
            if o.remove or not o.solid:
                continue
            dx = o.x - x
            dy = o.y - y
            r = RADIUS + o.radius
            if dx * dx + dy * dy < r * r:
                return False
        return True

    def move_player(self, dx, dy):
        p = self.player
        ox, oy = p.x, p.y
        if self.noclip:
            p.x += dx
            p.y += dy
        else:
            nx = p.x + dx
            ny = p.y + dy
            if self.can_stand(nx, ny, p.z):
                p.x, p.y = nx, ny
            elif dx and self.can_stand(p.x + dx, p.y, p.z):
                p.x += dx
            elif dy and self.can_stand(p.x, p.y + dy, p.z):
                p.y += dy
            else:
                return
        self.cross_lines(ox, oy, p.x, p.y)

    def cross_lines(self, x0, y0, x1, y1):
        dx = x1 - x0
        dy = y1 - y0
        if dx == 0.0 and dy == 0.0:
            return
        for ln in self.md.lines_near((x0 + x1) * 0.5, (y0 + y1) * 0.5,
                                     math.hypot(dx, dy) + RADIUS + 8.0):
            if ln.special == 0:
                continue
            ldx, ldy = ln.dx, ln.dy
            den = dx * ldy - dy * ldx
            if den == 0.0:
                continue
            ex = ln.v1[0] - x0
            ey = ln.v1[1] - y0
            t = (ex * ldy - ey * ldx) / den
            u = (ex * dy - ey * dx) / den
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                self.activate(ln, use=False)

    # ------------------------------------------------------------ действия
    def use(self):
        p = self.player
        ca = math.cos(p.angle)
        sa = math.sin(p.angle)
        best = None
        bestd = USE_RANGE
        for ln in self.md.lines_near(p.x + ca * 40, p.y + sa * 40, USE_RANGE):
            if ln.special == 0:
                continue
            mx = (ln.v1[0] + ln.v2[0]) * 0.5
            my = (ln.v1[1] + ln.v2[1]) * 0.5
            if (mx - p.x) * ca + (my - p.y) * sa <= 0.0:
                continue
            d = self._dist_to_line(p.x, p.y, ln)
            if d < bestd:
                bestd = d
                best = ln
        if best is None:
            return False
        return self.activate(best, use=True)

    def activate(self, line, use=False):
        sp = line.special
        if sp == 0:
            return False
        need = KEYED.get(sp)
        if need and need not in self.player.keys:
            if use:
                self.say('нужен %s ключ' % {'blue': 'синий', 'red': 'красный',
                                            'yellow': 'жёлтый'}[need])
                self.sound.play('DSNOWAY', 2)
            return False
        if sp in EXITS:
            if sp in (11, 51) and not use:
                return False
            self.exit_level = True
            self.sound.play('DSSWTCHX', 3)
            return True
        if sp in TELEPORTS:
            return self.teleport(line)
        if sp in DOOR_MANUAL:
            sec = line.back.sector if line.back else None
            if sec is None:
                return False
            return self.open_door(sec, wait=4.0)
        if sp in LIFTS:
            return self.tagged(line.tag, self.make_plat)
        if sp in DOOR_CLOSE:
            return self.tagged(line.tag, lambda s: self.open_door(s, closing=True))
        if sp in DOOR_OPEN_STAY:
            return self.tagged(line.tag, lambda s: self.open_door(s, wait=0.0))
        if sp in DOOR_OPEN_WAIT:
            return self.tagged(line.tag, lambda s: self.open_door(s, wait=4.0))
        if sp in FLOOR_RAISE:
            return self.tagged(line.tag, self.raise_floor)
        if sp in FLOOR_LOWER:
            return self.tagged(line.tag, self.lower_floor)
        if use:
            self.sound.play('DSSWTCHN', 2)
        return False

    def tagged(self, tag, fn):
        if tag == 0:
            return False
        hit = False
        for s in self.md.sectors:
            if s.tag == tag and id(s) not in self.busy:
                if fn(s):
                    hit = True
        return hit

    def add(self, th):
        self.thinkers.append(th)
        self.busy[id(th.sector)] = th
        return True

    def open_door(self, sec, wait=4.0, closing=False):
        if id(sec) in self.busy:
            return False
        if closing:
            self.sound.play('DSDORCLS', 2)
            return self.add(Door(sec, sec.ceil, closing=True))
        top = self.lowest_neighbour_ceiling(sec) - 4.0
        if top <= sec.floor:
            return False
        self.sound.play('DSDOROPN', 2)
        return self.add(Door(sec, top, wait=wait))

    def make_plat(self, sec):
        low = self.lowest_neighbour_floor(sec)
        if low >= sec.floor:
            return False
        self.sound.play('DSPSTART', 2)
        return self.add(Plat(sec, low, sec.floor))

    def raise_floor(self, sec):
        target = min((sd.sector.ceil for ln in sec.lines
                      for sd in (ln.front, ln.back)
                      if sd is not None and sd.sector is not sec), default=sec.ceil)
        if target <= sec.floor:
            return False
        self.sound.play('DSSTNMOV', 1)
        return self.add(FloorMove(sec, target - 8.0))

    def lower_floor(self, sec):
        target = self.lowest_neighbour_floor(sec)
        if target >= sec.floor:
            return False
        self.sound.play('DSSTNMOV', 1)
        return self.add(FloorMove(sec, target))

    def teleport(self, line):
        if line.back is None:
            return False
        tag = line.tag
        for t in self.md.things:
            if t.type != 14:
                continue
            sec = self.md.sector_at(t.x, t.y)
            if sec.tag == tag or tag == 0:
                p = self.player
                self.spawn_effect('TFOG', 'ABABCDEFGHIJ', p.x, p.y, p.z, True)
                p.x, p.y = t.x, t.y
                p.z = sec.floor
                p.angle = t.angle
                p.viewz = p.z + 41.0
                self.spawn_effect('TFOG', 'ABABCDEFGHIJ', t.x, t.y, sec.floor, True)
                self.sound.play('DSTELEPT', 3)
                return True
        return False

    @staticmethod
    def lowest_neighbour_ceiling(sec):
        best = None
        for ln in sec.lines:
            for sd in (ln.front, ln.back):
                if sd is None or sd.sector is sec:
                    continue
                c = sd.sector.ceil
                if best is None or c < best:
                    best = c
        return best if best is not None else sec.ceil + 72.0

    @staticmethod
    def lowest_neighbour_floor(sec):
        best = sec.floor
        for ln in sec.lines:
            for sd in (ln.front, ln.back):
                if sd is None or sd.sector is sec:
                    continue
                f = sd.sector.floor
                if f < best:
                    best = f
        return best

    # ------------------------------------------------------------ бой
    def hitscan(self, shooter, angle, rng, damage, melee=False):
        p = self.player
        x0, y0 = shooter.x, shooter.y
        z = p.viewz if shooter is p else shooter.z + shooter.height * 0.6
        ca = math.cos(angle)
        sa = math.sin(angle)
        frac, ln = self.md.trace(x0, y0, x0 + ca * rng, y0 + sa * rng, z)
        bestd = frac * rng
        best = None
        for o in self.mobjs:
            if o is shooter or o.remove or not o.shootable or o.dead:
                continue
            dx = o.x - x0
            dy = o.y - y0
            t = dx * ca + dy * sa
            if t <= 0.0 or t >= bestd:
                continue
            if abs(-dx * sa + dy * ca) > o.radius:
                continue
            slope = 40.0 + t * 0.25          # чем дальше, тем шире конус
            if o.z - slope > z or o.z + o.height + slope < z:
                continue
            bestd = t
            best = o
        hx = x0 + ca * bestd
        hy = y0 + sa * bestd
        if best is not None:
            best.hurt(damage, shooter)
            self.spawn_effect('BLUD', 'CBA', hx, hy, z - 8.0, False)
            return True
        if not melee:
            self.spawn_effect('PUFF', 'ABCD', hx - ca * 4, hy - sa * 4, z, True)
        return False

    def spawn_missile(self, source, kind, tx, ty, tz):
        info = TH.MISSILES.get(kind)
        if info is None or not self.sprset.has(info['sprite']):
            return None
        m = MO.Mobj(self, source.x, source.y, 0.0, 'missile')
        p = self.player
        sz = (p.viewz - 6.0) if source is p else (source.z + source.height * 0.6)
        m.angle = math.atan2(ty - source.y, tx - source.x)
        m.x += math.cos(m.angle) * (source.radius + 12.0 if source is not p else 24.0)
        m.y += math.sin(m.angle) * (source.radius + 12.0 if source is not p else 24.0)
        m.z = sz
        d = max(1.0, math.hypot(tx - source.x, ty - source.y))
        m.momz = (tz - sz) / d * info['speed']
        m.info = info
        m.sprite = info['sprite']
        m.speed = float(info['speed'])
        m.radius = float(info['radius'])
        m.height = float(info['height'])
        m.bright = True
        m.target = source
        m.set_seq([(c, 4.0 / 35.0, None) for c in info['fly']], 'fly')
        m.seq = None
        m.letters = list(info['fly'])
        m.frame = info['fly'][0]
        m.state = 'fly'
        self.mobjs.append(m)
        self.sound.play(info.get('sound'), 3)
        return m

    def spawn_monster_at(self, type_, x, y, angle):
        """Породить монстра на лету (элементаль боли выпускает души)."""
        t = MD.Thing(int(x), int(y), int(math.degrees(angle)), type_, 7)
        m = MO.spawn_monster(self, t, self.sprset)
        if m is None:
            return None
        m.wake()
        self.mobjs.append(m)
        if m.solid:
            self.blockers.append(m)
        return m

    def splash(self, x, y, z, radius, damage):
        p = self.player
        for o in list(self.mobjs):
            if not o.shootable or o.dead or o.remove:
                continue
            d = math.hypot(o.x - x, o.y - y)
            if d < radius:
                o.hurt(int(damage * (1.0 - d / radius)), None)
        d = math.hypot(p.x - x, p.y - y)
        if d < radius:
            p.hurt(int(damage * 0.6 * (1.0 - d / radius)))

    def spawn_effect(self, sprite, frames, x, y, z, bright):
        if not self.sprset.has(sprite):
            return None
        m = MO.Mobj(self, x, y, 0.0, 'effect')
        m.sprite = sprite
        m.z = z
        m.bright = bright
        m.set_seq([(c, 4.0 / 35.0, None) for c in frames], 'anim')
        self.mobjs.append(m)
        return m

    # ------------------------------------------------------------ предметы
    def pickup(self, m):
        p = self.player
        kind, value, msg, snd = m.item
        took = False
        if kind == 'health':
            if p.health < 100:
                p.health = min(100, p.health + value)
                took = True
        elif kind == 'health_bonus':
            if p.health < 200:
                p.health += 1
                took = True
        elif kind == 'armor_bonus':
            if p.armor < 200:
                p.armor += 1
                p.armor_type = max(1, p.armor_type)
                took = True
        elif kind == 'armor':
            if p.armor < 100:
                p.armor = 100
                p.armor_type = 1
                took = True
        elif kind == 'armor2':
            p.armor = 200
            p.armor_type = 2
            took = True
        elif kind == 'soul':
            p.health = min(200, p.health + 100)
            took = True
        elif kind.startswith('ammo_'):
            took = p.give_ammo(kind[5:], value)
        elif kind == 'backpack':
            for k in p.maxammo:
                p.maxammo[k] *= 2
            for k, v in (('bull', 10), ('shell', 4), ('rckt', 1), ('cell', 20)):
                p.give_ammo(k, v)
            took = True
        elif kind == 'weapon':
            if value < len(WEAPONS):
                new = value not in p.have
                p.have.add(value)
                give = {2: ('shell', 8), 3: ('bull', 20), 4: ('rckt', 2),
                        5: ('cell', 40), 6: ('cell', 40), 8: ('shell', 8)}.get(value)
                if give:
                    p.give_ammo(*give)
                if new:
                    p.switch_to(value)
                took = new or give is not None
        elif kind == 'key':
            if value not in p.keys:
                p.keys.add(value)
                took = True
        elif kind == 'berserk':
            p.berserk = True
            p.health = max(p.health, 100)
            p.switch_to(0)
            took = True
        elif kind.startswith('power_'):
            k = {'power_inv': 'inv', 'power_invis': 'invis',
                 'power_suit': 'suit', 'power_light': 'light'}.get(kind)
            if k:
                p.powers[k] = float(value)
            took = True
        if took:
            m.remove = True
            p.bonus_count = min(1.0, p.bonus_count + 0.5)
            if kind in ITEM_COUNTED:
                p.items += 1
            self.sound.play(snd, 2)
            self.say(msg)
        return took

    # ------------------------------------------------------------ такт
    def tick(self, dt, keys):
        self.time += dt
        p = self.player
        p.tick(dt, keys, self)

        px, py = p.x, p.y
        self.rebuild_bgrid()
        alive = []
        for m in self.mobjs:
            if m.remove:
                if m in self.blockers:
                    self.blockers.remove(m)
                continue
            alive.append(m)
            if m.kind == 'missile' or m.kind == 'effect':
                m.tick(dt, self.time)
                continue
            if m.kind == 'monster':
                if m.state == 'corpse':
                    continue
                d = abs(m.x - px) + abs(m.y - py)
                if m.dead or d < 3000.0 or m.state == 'chase':
                    m.tick(dt, self.time)
                continue
            if m.kind == 'item':
                dx = m.x - px
                dy = m.y - py
                if dx * dx + dy * dy < 36.0 * 36.0 and abs(m.z - p.z) < 60.0:
                    self.pickup(m)
        self.mobjs = alive

        for t in list(self.thinkers):
            t.tick(dt, self)
            if t.done:
                self.thinkers.remove(t)
                self.busy.pop(id(t.sector), None)
        for l in self.lights:
            l.tick(dt)

        sec = self.md.sector_at(p.x, p.y)
        if sec.special == SPEC.SECRET:
            sec.special = 0
            p.secrets += 1
            self.say('НАЙДЕН ТАЙНИК!')
        dmg = SPEC.DAMAGE.get(sec.special)
        if dmg and p.onground and p.health > 0:
            self.hurt_t += dt
            if self.hurt_t > 0.9:
                self.hurt_t = 0.0
                if sec.special == 11 or p.powers['suit'] <= 0.0:
                    p.hurt(dmg // 2 + random.randint(0, dmg // 2))
        else:
            self.hurt_t = 0.0

        self.view.x = p.x
        self.view.y = p.y
        self.view.z = p.viewz + p.view_bob()
        self.view.angle = p.angle

        if self.msg_time > 0.0:
            self.msg_time -= dt
            if self.msg_time <= 0.0:
                self.messages = []
