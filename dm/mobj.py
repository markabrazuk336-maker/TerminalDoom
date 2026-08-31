"""Объекты мира: монстры с ИИ, снаряды, предметы, декорации, эффекты."""
import math
import random

from . import things as TH
from . import sprites as SP

def tgt_radius(t):
    return getattr(t, 'radius', 16.0)


MELEE_RANGE = 64.0
MISSILE_RANGE = 2048.0
GRAVITY = 1100.0


class Mobj:
    __slots__ = ('game', 'x', 'y', 'z', 'angle', 'type', 'kind', 'sprite',
                 'frame', 'bright', 'sector', 'radius', 'height', 'health',
                 'speed', 'info', 'state', 'seq', 'si', 'st', 'target',
                 'solid', 'shootable', 'dead', 'remove', 'momx', 'momy', 'momz',
                 'floating', 'look_t', 'anim', 'letters', 'hangh', 'item',
                 'shadow', 'threshold', 'flash', 'counted', 'move_t')

    def __init__(self, game, x, y, angle=0.0, kind='decor'):
        self.game = game
        self.x = float(x)
        self.y = float(y)
        self.angle = float(angle)
        self.kind = kind
        self.sector = game.md.sector_at(x, y)
        self.z = self.sector.floor
        self.type = 0
        self.sprite = ''
        self.frame = 'A'
        self.bright = False
        self.shadow = False
        self.radius = 0.0
        self.height = 16.0
        self.health = 0
        self.speed = 0.0
        self.info = None
        self.state = 'idle'
        self.seq = None
        self.si = 0
        self.st = 0.0
        self.target = None
        self.solid = False
        self.shootable = False
        self.dead = False
        self.remove = False
        self.momx = self.momy = self.momz = 0.0
        self.floating = False
        self.look_t = random.random() * 0.4
        self.anim = 0
        self.letters = ['A']
        self.hangh = 0.0
        self.item = None
        self.threshold = 0.0
        self.flash = 0.0
        self.counted = False
        self.move_t = 0.0

    # ------------------------------------------------------------ утилиты
    def base_z(self):
        if self.hangh:
            return self.sector.ceil - self.hangh
        if (self.dead or self.kind in ('item', 'decor')) and not self.floating:
            return self.sector.floor
        return self.z

    def frame_at(self, t):
        if self.seq is not None:
            return self.frame
        n = len(self.letters)
        if n <= 1:
            return self.letters[0]
        return self.letters[int(t * 4.0) % n]

    def dist_to(self, o):
        return math.hypot(o.x - self.x, o.y - self.y)

    def sight_to(self, tx, ty):
        z = self.z + self.height * 0.6
        frac, ln = self.game.md.trace(self.x, self.y, tx, ty, z)
        return ln is None

    def set_seq(self, seq, state):
        self.seq = list(seq) if seq else None
        self.si = 0
        self.st = 0.0
        self.state = state
        if self.seq:
            self.frame = self.seq[0][0]

    # ------------------------------------------------------------ движение
    def can_move(self, nx, ny):
        g = self.game
        r = self.radius
        for ln in g.md.lines_near(nx, ny, r + 8.0):
            if g._dist_to_line(nx, ny, ln) < r:
                if ln.back is None or not (ln.flags & 0x0004):
                    return False
                if ln.flags & 0x0002:            # блокирует монстров
                    return False
                f = ln.front.sector
                b = ln.back.sector
                low = max(f.floor, b.floor)
                high = min(f.ceil, b.ceil)
                if high - low < self.height:
                    return False
                if not self.floating and low - self.z > 24.0:
                    return False
                if not self.floating and self.z - low > 128.0:
                    return False
        for o in g.blockers_near(nx, ny):
            if o is self or o.remove:
                continue
            dx = o.x - nx
            dy = o.y - ny
            rr = r + o.radius
            if dx * dx + dy * dy < rr * rr:
                return False
        p = g.player
        dx = p.x - nx
        dy = p.y - ny
        rr = r + 16.0
        if dx * dx + dy * dy < rr * rr:
            return False
        return True

    def step(self, dist):
        t = self.target
        a = math.atan2(t.y - self.y, t.x - self.x) if t is not None else self.angle
        for d in (0.0, 0.5, -0.5, 1.1, -1.1):
            ang = a + d
            nx = self.x + math.cos(ang) * dist
            ny = self.y + math.sin(ang) * dist
            if self.can_move(nx, ny):
                self.x = nx
                self.y = ny
                self.angle = ang
                return True
        return False

    def update_z(self, dt):
        sec = self.game.md.sector_at(self.x, self.y)
        self.sector = sec
        if self.floating:
            t = self.target if self.target is not None else self.game.player
            want = self.aim_z(t) - self.height * 0.5
            lo = sec.floor + 8.0
            hi = sec.ceil - self.height - 8.0
            if want < lo:
                want = lo
            if want > hi:
                want = hi
            self.z += (want - self.z) * min(1.0, dt * 1.5)
            return
        if self.z > sec.floor:
            self.momz -= GRAVITY * dt
            self.z += self.momz * dt
            if self.z <= sec.floor:
                self.z = sec.floor
                self.momz = 0.0
        else:
            self.z = sec.floor
            self.momz = 0.0

    # ------------------------------------------------------------ такт
    def tick(self, dt, t):
        if self.kind == 'missile':
            self.tick_missile(dt)
            return
        if self.kind == 'effect':
            self.advance(dt)
            return
        if self.kind == 'monster':
            self.tick_monster(dt, t)

    def advance(self, dt):
        """Проиграть текущую последовательность кадров."""
        if not self.seq:
            return True
        self.st += dt
        dur = self.seq[self.si][1]
        while dur is not None and self.st >= dur:
            self.st -= dur
            act = self.seq[self.si][2]
            if act:
                self.do_action(act)
            self.si += 1
            if self.si >= len(self.seq):
                self.seq = None
                if self.kind == 'effect':
                    self.remove = True
                return True
            self.frame = self.seq[self.si][0]
            dur = self.seq[self.si][1]
        if dur is None:
            act = self.seq[self.si][2]
            if act:
                self.do_action(act)
                self.seq[self.si] = (self.frame, None, None)
        return False

    # ------------------------------------------------------------ цель
    @staticmethod
    def alive(t):
        return t is not None and t.health > 0 and not getattr(t, 'dead', False)

    @staticmethod
    def aim_z(t):
        """Куда целиться: глаза игрока или середина монстра."""
        vz = getattr(t, 'viewz', None)
        return (vz - 12.0) if vz is not None else (t.z + t.height * 0.5)

    def valid_target(self):
        if self.alive(self.target) and getattr(self.target, 'remove', False) is False:
            return self.target
        self.target = None
        return None

    # ------------------------------------------------------------ ИИ
    def tick_monster(self, dt, t):
        g = self.game
        if self.dead:
            self.advance(dt)
            if self.seq and self.seq[self.si][1] is None:
                self.state = 'corpse'          # труп доиграл, больше не тикает
            return

        if self.state == 'pain':
            if self.advance(dt):
                self.set_seq(self.info['walk'], 'chase')
            return

        if self.state == 'attack':
            if self.advance(dt):
                self.set_seq(self.info['walk'], 'chase')
            return

        if self.state == 'idle':
            p = g.player
            self.look_t -= dt
            if self.look_t <= 0.0:
                self.look_t = 0.25
                d = self.dist_to(p)
                if p.health > 0 and d < 2200.0 and self.sight_to(p.x, p.y):
                    a = math.atan2(p.y - self.y, p.x - self.x)
                    rel = abs(((a - self.angle + math.pi) % math.tau) - math.pi)
                    if rel < 1.6 or d < 300.0:
                        self.wake(p)
            return

        # преследование
        self.advance(dt)
        if self.seq is None:
            self.set_seq(self.info['walk'], 'chase')
        tgt = self.valid_target()
        if tgt is None:
            p = g.player
            if p.health > 0:
                self.target = p                # цель погибла — снова за игроком
                tgt = p
            else:
                self.state = 'idle'
                return
        dist = self.dist_to(tgt)

        if self.info.get('heal') and self.try_resurrect():
            return

        self.threshold -= dt
        melee = self.info.get('melee')
        if melee and dist < MELEE_RANGE + self.radius + tgt_radius(tgt):
            self.set_seq(self.info['atk'], 'attack')
            if self.info.get('attack'):
                g.sound.play(self.info['attack'], 2)
            return
        if self.threshold <= 0.0 and dist < 1600.0:
            has_ranged = self.info.get('missile') or self.info.get('hitscan')
            if has_ranged and self.sight_to(tgt.x, tgt.y):
                chance = 0.55 if dist < 800.0 else 0.3
                if random.random() < chance:
                    self.threshold = 1.3 + random.random() * 1.4
                    self.set_seq(self.info['atk'], 'attack')
                    if self.info.get('attack'):
                        g.sound.play(self.info['attack'], 2)
                    return
                self.threshold = 0.6

        if self.info.get('charge') and dist < 900.0 and self.sight_to(tgt.x, tgt.y):
            self.set_seq(self.info['atk'], 'attack')
            return

        self.move_t += dt
        if self.move_t >= 0.1:
            self.step(self.speed * self.move_t)
            self.update_z(self.move_t)
            self.move_t = 0.0

    def wake(self, target=None):
        self.target = target if target is not None else self.game.player
        self.threshold = 0.5 + random.random() * 0.5     # время реакции
        self.set_seq(self.info['walk'], 'chase')
        s = self.info.get('see')
        if s:
            self.game.sound.play(s, 1)

    def try_resurrect(self):
        """Архвайл поднимает ближайший труп."""
        g = self.game
        for o in g.mobjs:
            if not o.dead or o.kind != 'monster' or o.remove or o is self:
                continue
            if o.info.get('boss') or not o.info.get('die'):
                continue
            if abs(o.x - self.x) > 96.0 or abs(o.y - self.y) > 96.0:
                continue
            o.resurrect()
            self.set_seq(self.info.get('heal'), 'attack')
            g.sound.play('DSSLOP', 2)
            return True
        return False

    def resurrect(self):
        g = self.game
        self.dead = False
        self.health = self.info['hp']
        self.solid = True
        self.shootable = True
        self.floating = bool(self.info.get('float'))
        self.counted = False
        g.kills = max(0, g.kills - 1)
        if self not in g.blockers:
            g.blockers.append(self)
        self.target = g.player
        self.set_seq(self.info['walk'], 'chase')

    def do_action(self, act):
        g = self.game
        if act == 'fall':
            self.solid = False
            if self in g.blockers:
                g.blockers.remove(self)
            return
        tgt = self.valid_target() or g.player
        if not self.alive(tgt):
            return
        self.angle = math.atan2(tgt.y - self.y, tgt.x - self.x)
        if act == 'melee':
            if self.dist_to(tgt) < MELEE_RANGE + self.radius + tgt_radius(tgt) + 16.0:
                a, b = self.info['melee']
                tgt.hurt(a * random.randint(1, b), self)
                g.sound.play(self.info.get('attack'), 2)
        elif act == 'hitscan':
            n, a, b = self.info['hitscan']
            if self.sight_to(tgt.x, tgt.y):
                for _ in range(n):
                    ang = self.angle + (random.random() - 0.5) * 0.09
                    g.hitscan(self, ang, 2048.0, a * random.randint(1, b),
                              aim_z=self.aim_z(tgt))
            g.sound.play(self.info.get('attack'), 3)
        elif act == 'charge':
            if self.dist_to(tgt) < 90.0:
                a, b = self.info['melee']
                tgt.hurt(a * random.randint(1, b), self)
        elif act == 'soul':
            ang = self.angle
            g.spawn_monster_at(3006, self.x + math.cos(ang) * (self.radius + 24.0),
                               self.y + math.sin(ang) * (self.radius + 24.0), ang)
        elif act == 'attack':
            if self.info.get('melee') and \
                    self.dist_to(tgt) < MELEE_RANGE + self.radius + tgt_radius(tgt):
                a, b = self.info['melee']
                tgt.hurt(a * random.randint(1, b), self)
            elif self.info.get('missile'):
                g.spawn_missile(self, self.info['missile'], tgt.x, tgt.y,
                                self.aim_z(tgt))

    # ------------------------------------------------------------ снаряды
    def tick_missile(self, dt):
        if self.seq is not None and self.state == 'boom':
            if self.advance(dt):
                self.remove = True
            return
        g = self.game
        dist = self.speed * dt
        steps = int(dist / 14.0) + 1
        sd = dist / steps
        for _ in range(steps):
            nx = self.x + math.cos(self.angle) * sd
            ny = self.y + math.sin(self.angle) * sd
            nz = self.z + self.momz * dt / steps
            frac, ln = g.md.trace(self.x, self.y, nx, ny, nz)
            if ln is not None:
                self.explode()
                return
            sec = g.md.sector_at(nx, ny)
            if nz < sec.floor or nz + 8.0 > sec.ceil:
                self.explode()
                return
            self.x, self.y, self.z = nx, ny, nz
            hit = self.check_hit()
            if hit is not None:
                self.explode(hit)
                return

    def check_hit(self):
        g = self.game
        owner = self.target
        p = g.player
        if owner is not p:
            if abs(p.x - self.x) < 24 and abs(p.y - self.y) < 24:
                if self.z > p.z - 8 and self.z < p.z + 56:
                    return p
        for o in g.mobjs:
            if o is self or o is owner or not o.shootable or o.dead:
                continue
            dx = o.x - self.x
            dy = o.y - self.y
            r = o.radius + self.radius
            if dx * dx + dy * dy < r * r and o.z - 8 < self.z < o.z + o.height:
                return o
        return None

    def explode(self, hit=None):
        g = self.game
        info = self.info
        owner = self.target
        if hit is not None:
            a, b = info['damage']
            hit.hurt(a * random.randint(1, b), owner)
        if info.get('splash'):
            g.splash(self.x, self.y, self.z, info['splash'],
                     info['damage'][0] * 4, owner)
        g.sound.play(info.get('hit'), 3)
        self.speed = 0.0
        self.state = 'boom'
        self.bright = True
        bs = info.get('boom_sprite')
        if bs and g.sprset.has(bs):
            self.sprite = bs
        boom = info.get('boom')
        if boom:
            self.set_seq([(c, 4.0 / 35.0, None) for c in boom], 'boom')
            self.state = 'boom'
        else:
            self.remove = True

    # ------------------------------------------------------------ урон
    def hurt(self, amount, source=None):
        if self.dead or not self.shootable:
            return
        self.health -= amount
        self.flash = 0.12
        if self.health <= 0:
            self.die(gib=self.health < -self.info['hp'] * 0.7)
            return
        if self.kind != 'monster':          # бочки и прочее не «просыпаются»
            return
        # задел другой монстр — переключаемся на обидчика (кроме своего вида)
        new_target = self.game.player
        if source is not None and source is not self and                 getattr(source, 'kind', None) == 'monster' and                 source.type != self.type and not source.dead:
            new_target = source
        self.target = new_target
        if self.state == 'idle':
            self.wake(new_target)
        if random.randint(0, 255) < self.info.get('painchance', 0):
            self.set_seq(self.info['hurt'], 'pain')
            self.game.sound.play(self.info.get('pain'), 2)

    def die(self, gib=False):
        g = self.game
        self.dead = True
        self.solid = False
        self.shootable = False
        if self in g.blockers:
            g.blockers.remove(self)
        if self.type == TH.BARREL:
            g.spawn_effect('BEXP', 'ABCDE', self.x, self.y, self.z + 16.0, True)
            g.splash(self.x, self.y, self.z, 128.0, 128.0)
            g.sound.play('DSBAREXP', 3)
            self.remove = True
            return
        if not self.counted:
            self.counted = True
            g.kills += 1
        snd = self.info.get('death')
        if gib and self.info.get('gib'):
            g.sound.play('DSSLOP', 2)
            self.set_seq(self.info['gib'], 'dead')
        else:
            if snd:
                g.sound.play(snd, 2)
            self.set_seq(self.info.get('die'), 'dead')
        self.floating = False
        self.state = 'dead'


# ------------------------------------------------------------------ фабрики
def spawn_monster(game, thing, sprset):
    info = TH.MONSTERS.get(thing.type)
    if info is None or not sprset.has(info['sprite']):
        return None
    m = Mobj(game, thing.x, thing.y, thing.angle, 'monster')
    m.type = thing.type
    m.info = info
    m.sprite = info['sprite']
    m.radius = float(info['radius'])
    m.height = float(info['height'])
    m.health = info['hp']
    m.speed = float(info['speed'])
    m.solid = True
    m.shootable = True
    m.floating = bool(info.get('float'))
    m.bright = bool(info.get('bright'))
    m.shadow = bool(info.get('shadow'))
    m.letters = ['A']
    m.set_seq(info['walk'], 'idle')
    m.state = 'idle'
    if m.floating:
        m.z = m.sector.floor + 40.0
    return m


def spawn_item(game, thing, sprset):
    got = TH.ITEMS.get(thing.type)
    if got is None:
        return None
    sprite, kind, value, msg, snd = got
    if not sprset.has(sprite):
        return None
    m = Mobj(game, thing.x, thing.y, thing.angle, 'item')
    m.type = thing.type
    m.sprite = sprite
    m.item = (kind, value, msg, snd)
    m.radius = 20.0
    m.bright = kind in ('soul', 'power_inv', 'berserk', 'power_invis',
                        'power_map', 'power_light', 'health_bonus', 'armor_bonus',
                        'armor', 'armor2', 'key')
    letters = sprset.frame_letters(sprite)
    m.letters = letters[:6] if thing.type in TH.BLINKING else [letters[0]]
    return m


def spawn_decor(game, thing, sprset, gfx):
    got = SP.THINGS.get(thing.type)
    if got is None:
        return None
    base, hang, anim, bright = got
    if not sprset.has(base):
        return None
    m = Mobj(game, thing.x, thing.y, thing.angle, 'decor')
    m.type = thing.type
    m.sprite = base
    m.bright = bool(bright)
    avail = sprset.frame_letters(base)
    if thing.type in SP.CORPSE_FRAME:
        f = SP.CORPSE_FRAME[thing.type]
        m.letters = [f if f in avail else avail[-1]]
    elif thing.type == TH.BARREL:
        m.letters = [c for c in ('A', 'B') if c in avail] or [avail[0]]
        m.health = 20
        m.shootable = True
        m.solid = True
        m.radius = 10.0
        m.height = 42.0
        m.info = dict(hp=20, painchance=0)
    elif anim:
        m.letters = avail[:8]
    else:
        m.letters = [avail[0]]
    m.radius = float(SP.RADIUS.get(thing.type, 0))
    m.solid = m.radius > 0.0
    if hang:
        m.hangh = 64.0
        got2 = sprset.pick(base, m.letters[0], 0.0, 0.0)
        if got2:
            p = gfx.patch(got2[0])
            if p:
                m.hangh = float(p.height)
        m.z = m.sector.ceil - m.hangh
        m.solid = False
    return m
