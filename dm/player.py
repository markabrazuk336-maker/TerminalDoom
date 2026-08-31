"""Игрок: движение, оружие, боеприпасы, урон, эффекты палитры."""
import math
import random

T = 1.0 / 35.0

RADIUS = 16.0
HEIGHT = 56.0
VIEW_HEIGHT = 41.0
MAX_STEP = 24.0
GRAVITY = 1100.0
WALK = 300.0
RUN = 560.0
TURN = math.radians(140.0)
TURN_RUN = math.radians(215.0)

AMMO_MAX = {'bull': 200, 'shell': 50, 'rckt': 50, 'cell': 300}

# оружие: кадры (буква, тики, действие)
WEAPONS = [
    dict(name='КУЛАК', sprite='PUNG', ammo=None, use=0, flash=None,
         fire=[('A', 4, None), ('B', 4, None), ('C', 4, 'punch'),
               ('D', 4, None), ('C', 4, None)], auto=True, sound=None),
    dict(name='ПИСТОЛЕТ', sprite='PISG', ammo='bull', use=1, flash='PISFA',
         fire=[('A', 4, None), ('B', 6, 'bullet'), ('C', 4, None), ('B', 5, None)],
         auto=False, sound='DSPISTOL', pellets=1, spread=0.02, dmg=(5, 3)),
    dict(name='ДРОБОВИК', sprite='SHTG', ammo='shell', use=1, flash='SHTFA',
         fire=[('A', 3, None), ('A', 7, 'bullet'), ('B', 5, None), ('C', 5, None),
               ('D', 4, None), ('C', 5, None), ('B', 5, None), ('A', 3, None)],
         auto=False, sound='DSSHOTGN', pellets=7, spread=0.08, dmg=(5, 3)),
    dict(name='ПУЛЕМЁТ', sprite='CHGG', ammo='bull', use=1, flash='CHGFA',
         fire=[('A', 4, 'bullet'), ('B', 4, 'bullet')],
         auto=True, sound='DSPISTOL', pellets=1, spread=0.04, dmg=(5, 3)),
    dict(name='РАКЕТНИЦА', sprite='MISG', ammo='rckt', use=1, flash='MISFA',
         fire=[('A', 8, 'rocket'), ('B', 12, None)],
         auto=False, sound=None, missile='MISL'),
    dict(name='ПЛАЗМОМЁТ', sprite='PLSG', ammo='cell', use=1, flash='PLSFA',
         fire=[('A', 3, 'plasma'), ('B', 20, None)],
         auto=True, sound=None, missile='PLSS'),
    dict(name='BFG9000', sprite='BFGG', ammo='cell', use=40, flash='BFGFA',
         fire=[('A', 20, None), ('A', 10, None), ('B', 10, 'bfg'), ('B', 20, None)],
         auto=False, sound=None, missile='BFS1'),
    dict(name='БЕНЗОПИЛА', sprite='SAWG', ammo=None, use=0, flash=None,
         fire=[('A', 4, 'saw'), ('B', 4, 'saw')], auto=True, sound='DSSAWFUL'),
    dict(name='ДВУСТВОЛКА', sprite='SHT2', ammo='shell', use=2, flash='SHT2I',
         fire=[('A', 3, None), ('A', 7, 'bullet'), ('B', 7, None), ('C', 7, None),
               ('D', 7, None), ('E', 7, None), ('F', 7, None), ('G', 6, None),
               ('H', 6, None), ('A', 5, None)],
         auto=False, sound='DSDSHTGN', pellets=20, spread=0.16, dmg=(5, 3)),
]



class Player:
    def __init__(self, game, x, y, angle, sector):
        self.game = game
        self.x = float(x)
        self.y = float(y)
        self.angle = float(angle)
        self.z = sector.floor
        self.momz = 0.0
        self.floorz = sector.floor
        self.viewz = self.z + VIEW_HEIGHT
        self.bob = 0.0
        self.bob_amp = 0.0
        self.onground = True
        self.pitch = 0.0            # наклон взгляда, тангенс угла
        self.mouse_dx = 0.0
        self.mouse_dy = 0.0

        self.health = 100
        self.armor = 0
        self.armor_type = 0
        self.ammo = {'bull': 50, 'shell': 0, 'rckt': 0, 'cell': 0}
        self.maxammo = dict(AMMO_MAX)
        self.have = {0, 1}
        self.weapon = 1
        self.pending = -1
        self.wstate = 'ready'
        self.wseq = None
        self.wi = 0
        self.wt = 0.0
        self.wframe = 'A'
        self.woffset = 0.0
        self.flash_t = 0.0
        self.flash_frame = 'A'
        self.attack_held = False
        self.keys = set()
        self.dead_t = 0.0

        self.damage_count = 0.0
        self.bonus_count = 0.0
        self.powers = {'inv': 0.0, 'invis': 0.0, 'suit': 0.0, 'light': 0.0}
        self.berserk = False
        self.face_t = 0.0
        self.face_dir = 0
        self.face_ouch = 0.0
        self.face_kill = 0.0
        self.secrets = 0
        self.items = 0

    # ------------------------------------------------------------ оружие
    def weapon_ok(self, i):
        if i not in self.have:
            return False
        w = WEAPONS[i]
        if w['ammo'] is None:
            return True
        return self.ammo[w['ammo']] >= w['use']

    def switch_to(self, i):
        if i == self.weapon or not self.weapon_ok(i):
            return
        self.pending = i
        if self.wstate in ('ready', 'fire'):
            self.wstate = 'lower'

    def next_weapon(self, step=1):
        order = [i for i in range(len(WEAPONS)) if self.weapon_ok(i)]
        if not order:
            return
        if self.weapon in order:
            i = order[(order.index(self.weapon) + step) % len(order)]
        else:
            i = order[0]
        self.switch_to(i)

    def start_fire(self):
        w = WEAPONS[self.weapon]
        if w['ammo'] is not None and self.ammo[w['ammo']] < w['use']:
            # нет патронов — переключаемся на что-нибудь стреляющее
            for i in (8, 2, 3, 1, 5, 4, 6, 0):
                if self.weapon_ok(i):
                    self.switch_to(i)
                    break
            return
        if w['ammo'] is not None:
            self.ammo[w['ammo']] -= w['use']
        self.wseq = list(w['fire'])
        self.wi = 0
        self.wt = 0.0
        self.wframe = self.wseq[0][0]
        self.wstate = 'fire'
        self.face_kill = 0.6
        if w.get('sound'):
            self.game.sound.play(w['sound'], 3)

    def tick_weapon(self, dt, firing):
        if self.wstate == 'lower':
            self.woffset += dt * 900.0
            if self.woffset > 90.0:
                self.woffset = 90.0
                if self.pending >= 0:
                    self.weapon = self.pending
                    self.pending = -1
                self.wstate = 'raise'
            return
        if self.wstate == 'raise':
            self.woffset -= dt * 900.0
            if self.woffset <= 0.0:
                self.woffset = 0.0
                self.wstate = 'ready'
                self.wframe = 'A'
            return
        if self.wstate == 'fire' and self.wseq:
            self.wt += dt
            dur = self.wseq[self.wi][1] * T
            while self.wt >= dur:
                self.wt -= dur
                act = self.wseq[self.wi][2]
                if act:
                    self.do_fire(act)
                self.wi += 1
                if self.wi >= len(self.wseq):
                    self.wseq = None
                    self.wstate = 'ready'
                    self.wframe = 'A'
                    w = WEAPONS[self.weapon]
                    if firing and w['auto'] and self.health > 0:
                        self.start_fire()
                    return
                self.wframe = self.wseq[self.wi][0]
                dur = self.wseq[self.wi][1] * T
            return
        if self.wstate == 'ready':
            self.wframe = 'A'
            if firing and self.health > 0:
                self.start_fire()

    def do_fire(self, act):
        g = self.game
        w = WEAPONS[self.weapon]
        self.flash_t = 0.12
        self.flash_frame = 'A'
        if act == 'punch':
            dmg = random.randint(1, 10) * 2
            if self.berserk:
                dmg *= 10
            hit = g.hitscan(self, self.angle + (random.random() - 0.5) * 0.1,
                            80.0, dmg, melee=True, slope=self.pitch)
            g.sound.play('DSPUNCH' if hit else 'DSPUNCH', 2)
        elif act == 'saw':
            dmg = random.randint(1, 10) * 2
            g.hitscan(self, self.angle + (random.random() - 0.5) * 0.15,
                      90.0, dmg, melee=True, slope=self.pitch)
        elif act == 'bullet':
            n = w.get('pellets', 1)
            a, b = w.get('dmg', (5, 3))
            for _ in range(n):
                ang = self.angle + (random.random() - 0.5) * w.get('spread', 0.03)
                sl = self.pitch + (random.random() - 0.5) * w.get('spread', 0.03)
                g.hitscan(self, ang, 2048.0, a * random.randint(1, b), slope=sl)
        elif act in ('rocket', 'plasma', 'bfg'):
            tx = self.x + math.cos(self.angle) * 2048.0
            ty = self.y + math.sin(self.angle) * 2048.0
            tz = self.viewz - 8.0 + self.pitch * 2048.0
            g.spawn_missile(self, w['missile'], tx, ty, tz)

    # ------------------------------------------------------------ урон
    def hurt(self, amount, source=None):
        if self.health <= 0:
            return
        if self.powers['inv'] > 0.0:
            return
        if self.armor > 0:
            take = amount * (0.5 if self.armor_type == 2 else 1.0 / 3.0)
            take = int(take)
            if take > self.armor:
                take = self.armor
            self.armor -= take
            amount -= take
        self.health -= amount
        self.damage_count = min(1.0, self.damage_count + amount / 60.0 + 0.15)
        self.face_ouch = 0.7
        if self.health <= 0:
            self.health = 0
            self.dead_t = 0.0
            self.game.sound.play('DSPLDETH', 3)
            self.game.say('ТЫ ПОГИБ.  R — начать уровень заново')
        else:
            self.game.sound.play('DSPLPAIN', 2)

    def give_ammo(self, kind, amount):
        m = self.maxammo[kind]
        if self.ammo[kind] >= m:
            return False
        self.ammo[kind] = min(m, self.ammo[kind] + amount)
        return True

    # ------------------------------------------------------------ такт
    def tick(self, dt, keys, game):
        if self.health <= 0:
            self.dead_t += dt
            self.viewz += (self.z + 8.0 - self.viewz) * min(1.0, dt * 5.0)
            self.damage_count = max(0.0, self.damage_count - dt * 0.25)
            self.woffset = min(90.0, self.woffset + dt * 200.0)
            return

        speed = RUN if keys('shift') else WALK
        turn = TURN_RUN if keys('shift') else TURN
        fwd = side = 0.0
        if keys('w') or keys('up'):
            fwd += 1.0
        if keys('s') or keys('down'):
            fwd -= 1.0
        if keys('comma'):
            side -= 1.0
        if keys('period'):
            side += 1.0
        if keys('a') or keys('left'):
            self.angle += turn * dt
        if keys('d') or keys('right'):
            self.angle -= turn * dt
        if self.mouse_dx:
            self.angle -= self.mouse_dx * 0.0032
            self.mouse_dx = 0.0
        self.angle %= math.tau

        # взгляд вверх-вниз
        if keys('pgup'):
            self.pitch += 1.6 * dt
        if keys('pgdn'):
            self.pitch -= 1.6 * dt
        if keys('home'):
            self.pitch = 0.0
        if self.mouse_dy:
            self.pitch -= self.mouse_dy * 0.006
            self.mouse_dy = 0.0
        if self.pitch > 1.0:
            self.pitch = 1.0
        elif self.pitch < -1.0:
            self.pitch = -1.0

        if fwd or side:
            n = math.hypot(fwd, side)
            ca = math.cos(self.angle)
            sa = math.sin(self.angle)
            dx = (ca * fwd + sa * side) / n * speed * dt
            dy = (sa * fwd - ca * side) / n * speed * dt
            game.move_player(dx, dy)
            self.bob += dt * (13.0 if speed > WALK else 9.0)
            self.bob_amp += (1.0 if speed > WALK else 0.6 - self.bob_amp) * dt * 4.0
            self.bob_amp = min(self.bob_amp, 1.0 if speed > WALK else 0.65)
        else:
            self.bob += dt * 3.0
            self.bob_amp += (0.0 - self.bob_amp) * min(1.0, dt * 6.0)

        sec = game.md.sector_at(self.x, self.y)
        self.floorz = sec.floor
        if self.z < self.floorz:
            self.z = min(self.floorz, self.z + 260.0 * dt + 1.0)
            self.momz = 0.0
            self.onground = True
        elif self.z > self.floorz:
            self.momz -= GRAVITY * dt
            self.z += self.momz * dt
            if self.z <= self.floorz:
                self.z = self.floorz
                self.momz = 0.0
                self.onground = True
            else:
                self.onground = False
        if self.z + HEIGHT > sec.ceil:
            self.z = max(self.floorz, sec.ceil - HEIGHT)

        target = self.z + VIEW_HEIGHT
        self.viewz += (target - self.viewz) * min(1.0, dt * 14.0)

        firing = keys('e') or keys('ctrl') or keys('f') or keys('mouse1')
        self.tick_weapon(dt, firing)

        for k in self.powers:
            if self.powers[k] > 0.0:
                self.powers[k] = max(0.0, self.powers[k] - dt)
        self.damage_count = max(0.0, self.damage_count - dt * 0.9)
        self.bonus_count = max(0.0, self.bonus_count - dt * 1.6)
        self.flash_t = max(0.0, self.flash_t - dt)
        self.face_ouch = max(0.0, self.face_ouch - dt)
        self.face_kill = max(0.0, self.face_kill - dt)
        self.face_t += dt
        if self.face_t > 0.5:
            self.face_t = 0.0
            self.face_dir = random.randint(0, 2)

    # ------------------------------------------------------------ вид
    def view_bob(self):
        return math.sin(self.bob) * 2.6 * self.bob_amp

    def palette(self):
        """Номер палитры PLAYPAL: 1-8 — красный, 9-12 — жёлтый, 13 — костюм."""
        if self.damage_count > 0.0:
            return min(8, 1 + int(self.damage_count * 7.0))
        if self.bonus_count > 0.0:
            return min(12, 9 + int(self.bonus_count * 3.0))
        if self.powers['suit'] > 0.0:
            return 13
        return 0
