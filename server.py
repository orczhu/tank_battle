#!/usr/bin/env python3
"""Tank Battle - a Battle City style game for two players on the same WiFi.

Run:   python3 server.py
Then on each kid's computer open  http://<this-computer-ip>:8080
(the address is printed when the server starts).
"""
import asyncio
import json
import math
import pathlib
import random
import socket

from aiohttp import web

PORT = 8080
FPS = 60
TILE = 8            # map cell size in pixels
N = 26              # map is N x N cells
SIZE = TILE * N     # 208 px playfield
TANK = 16

UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
DX = (0, 1, 0, -1)
DY = (-1, 0, 1, 0)

EMPTY, BRICK, STEEL, WATER, TREES = '.', '#', '@', '~', '%'
TANK_BLOCKERS = {BRICK, STEEL, WATER}

BASE_RECT = (96, 192, 16, 16)
BASE_WALL = [(11, 23), (12, 23), (13, 23), (14, 23), (11, 24), (14, 24), (11, 25), (14, 25)]
PLAYER_SPAWNS = [(64, 192), (128, 192)]
ENEMY_SPAWNS = [(0, 0), (96, 0), (192, 0)]

ENEMY_TYPES = {
    'basic': dict(speed=0.5, bullet=2.0, hp=1, score=100),
    'fast': dict(speed=1.25, bullet=2.5, hp=1, score=200),
    'power': dict(speed=0.75, bullet=4.0, hp=1, score=300),
    'armor': dict(speed=0.5, bullet=2.5, hp=4, score=400),
}
POWERUPS = ['star', 'grenade', 'helmet', 'shovel', 'timer', 'tank']

# Each map is 13x13 blocks; every block becomes 2x2 cells.
# . empty  # brick  @ steel  ~ water  % trees
# Base area (bottom middle) and spawn points are filled in by code - keep them empty.
STAGES = [
    [
        ".............",
        ".#.#.#.#.#.#.",
        ".#.#.#.#.#.#.",
        ".#.#.#@#.#.#.",
        ".#.#.....#.#.",
        ".....#.#.....",
        "@.##.....##.@",
        ".....#.#.....",
        ".#.#.###.#.#.",
        ".#.#.#.#.#.#.",
        ".#.#.....#.#.",
        ".#.#.....#.#.",
        ".............",
    ],
    [
        ".............",
        ".%%%.....%%%.",
        ".%#%.@.@.%#%.",
        ".%%%.....%%%.",
        "....#####....",
        "~~..#...#..~~",
        "....#.%.#....",
        "~~..#...#..~~",
        "....##.##....",
        ".@.........@.",
        ".##.#.#.#.##.",
        ".##.......##.",
        ".............",
    ],
    [
        ".............",
        "..@@.....@@..",
        "..#.......#..",
        "..#.~~~~~.#..",
        "..#.~%%%~.#..",
        "....~%@%~....",
        "##..~%%%~..##",
        "....~~.~~....",
        ".#.........#.",
        ".#.##...##.#.",
        ".#..#.#.#..#.",
        "....#...#....",
        ".............",
    ],
]


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def enemy_queue(stage):
    mixes = [(14, 4, 2, 0), (8, 6, 4, 2), (4, 6, 6, 4)]
    basic, fast, power, armor = mixes[min(stage - 1, 2)] if stage <= 3 else (2, 6, 6, 6)
    q = ['basic'] * basic + ['fast'] * fast + ['power'] * power + ['armor'] * armor
    random.shuffle(q)
    return q


class Tank:
    def __init__(self, kind, x, y, direction, slot=None):
        self.kind, self.x, self.y, self.dir, self.slot = kind, x, y, direction, slot
        self.spawn = 60       # ticks of spawn sparkle before it becomes active
        self.shield = 0
        self.frozen = 0
        self.cooldown = 0
        self.bonus = False
        self.level = 0
        self.ai_timer = 0
        if slot is None:
            t = ENEMY_TYPES[kind]
            self.speed, self.hp = t['speed'], t['hp']
        else:
            self.speed, self.hp = 0.75, 1

    @property
    def player(self):
        return self.slot is not None

    @property
    def rect(self):
        return (self.x, self.y, TANK, TANK)

    @property
    def bullet_speed(self):
        if self.player:
            return 4.0 if self.level >= 1 else 2.5
        return ENEMY_TYPES[self.kind]['bullet']

    @property
    def max_bullets(self):
        return 2 if self.player and self.level >= 2 else 1


class Bullet:
    def __init__(self, x, y, direction, speed, owner, power):
        self.x, self.y, self.dir, self.speed, self.owner, self.power = x, y, direction, speed, owner, power
        self.alive = True

    @property
    def rect(self):
        return (self.x - 2, self.y - 2, 4, 4)


class Game:
    def __init__(self):
        self.clients = {}   # websocket -> slot (0, 1, or None for spectators)
        self.inputs = [{'dir': -1, 'fire': False}, {'dir': -1, 'fire': False}]
        self.pinfo = [None, None]
        self.state = 'lobby'
        self.stage = 1
        self.tick = 0
        self.events = []
        self.load_stage()
        self.state = 'lobby'

    # ---------- connections ----------
    def join(self, ws):
        taken = set(self.clients.values())
        slot = next((s for s in (0, 1) if s not in taken), None)
        self.clients[ws] = slot
        if slot is not None and self.state == 'playing' and self.pinfo[slot] is None:
            self.pinfo[slot] = {'lives': 3, 'level': 0, 'score': 0}   # jump straight into a running game
            self.spawn_player(slot)
        return slot

    def leave(self, ws):
        slot = self.clients.pop(ws, None)
        if slot is not None:
            self.inputs[slot] = {'dir': -1, 'fire': False}
        if not self.connected(0) and not self.connected(1):
            self.state = 'lobby'   # everyone left - don't keep a game running with nobody playing

    def connected(self, slot):
        return slot in self.clients.values()

    def handle(self, ws, msg):
        slot = self.clients.get(ws)
        if msg.get('t') == 'input' and slot is not None:
            self.inputs[slot] = {'dir': int(msg.get('dir', -1)), 'fire': bool(msg.get('fire'))}
        elif msg.get('t') == 'start' and self.state in ('lobby', 'gameover'):
            self.start_game()

    # ---------- stage setup ----------
    def start_game(self):
        self.pinfo = [{'lives': 3, 'level': 0, 'score': 0} if self.connected(s) else None for s in (0, 1)]
        if not any(self.pinfo):
            return
        self.stage = 1
        self.load_stage()

    def load_stage(self):
        rows = STAGES[(self.stage - 1) % len(STAGES)]
        self.map = [[EMPTY] * N for _ in range(N)]
        for br, row in enumerate(rows):
            for bc, ch in enumerate(row):
                for r in (2 * br, 2 * br + 1):
                    for c in (2 * bc, 2 * bc + 1):
                        self.map[r][c] = ch
        for c, r in BASE_WALL:
            self.map[r][c] = BRICK
        self.base_alive = True
        self.tanks, self.bullets, self.explosions = [], [], []
        self.powerup = None
        self.queue = enemy_queue(self.stage)
        self.enemies_spawned = 0
        self.spawn_index = 0
        self.spawn_timer = 60
        self.freeze_timer = 0
        self.shovel_timer = 0
        self.state = 'playing'
        self.state_timer = 0
        for slot in (0, 1):
            # Late joiners get in, and a knocked-out sibling comes back with 1 life.
            if self.connected(slot):
                if self.pinfo[slot] is None:
                    self.pinfo[slot] = {'lives': 3, 'level': 0, 'score': 0}
                elif self.pinfo[slot]['lives'] <= 0:
                    self.pinfo[slot]['lives'] = 1
            if self.pinfo[slot] and self.pinfo[slot]['lives'] > 0:
                self.spawn_player(slot)

    def spawn_player(self, slot):
        x, y = PLAYER_SPAWNS[slot]
        t = Tank('p%d' % (slot + 1), x, y, UP, slot)
        t.level = self.pinfo[slot]['level']
        self.tanks.append(t)

    # ---------- main update ----------
    def update(self):
        self.tick += 1
        for e in self.explosions:
            e[3] += 1
        self.explosions = [e for e in self.explosions if e[3] < (30 if e[2] else 15)]

        if self.state == 'playing':
            self.update_play()
        elif self.state == 'stage_clear':
            self.state_timer -= 1
            if self.state_timer <= 0:
                self.stage += 1
                self.load_stage()

    def update_play(self):
        if self.freeze_timer:
            self.freeze_timer -= 1
        if self.shovel_timer:
            self.shovel_timer -= 1
            if self.shovel_timer == 0:
                self.set_base_wall(BRICK)

        self.spawn_enemies()

        for t in list(self.tanks):
            if t not in self.tanks:
                continue
            if t.spawn > 0:
                t.spawn -= 1
                if t.spawn == 0 and t.player:
                    t.shield = 180
                continue
            if t.shield:
                t.shield -= 1
            if t.cooldown:
                t.cooldown -= 1
            if t.player:
                self.control_player(t)
            else:
                self.control_enemy(t)

        self.update_bullets()
        self.update_powerup()

        if self.state != 'playing':
            return
        if not any(t.player for t in self.tanks) and all(p is None or p['lives'] <= 0 for p in self.pinfo):
            self.game_over()
        elif not self.queue and not any(not t.player for t in self.tanks):
            self.state = 'stage_clear'
            self.state_timer = 180
            self.events.append('clear')

    def game_over(self):
        self.state = 'gameover'
        self.events.append('gameover')

    def spawn_enemies(self):
        enemies = sum(1 for t in self.tanks if not t.player)
        if not self.queue or enemies >= 4:
            return
        self.spawn_timer -= 1
        if self.spawn_timer > 0:
            return
        x, y = ENEMY_SPAWNS[self.spawn_index % 3]
        if any(overlap(t.rect, (x, y, TANK, TANK)) for t in self.tanks):
            return
        t = Tank(self.queue.pop(0), x, y, DOWN)
        t.bonus = self.enemies_spawned in (3, 10, 17)
        self.enemies_spawned += 1
        self.spawn_index += 1
        self.tanks.append(t)
        self.spawn_timer = max(60, 190 - self.stage * 10)

    # ---------- tanks ----------
    def control_player(self, t):
        if t.frozen:
            t.frozen -= 1
            return
        inp = self.inputs[t.slot]
        if inp['dir'] >= 0:
            self.turn(t, inp['dir'])
            self.move(t)
        if inp['fire']:
            self.fire(t)

    def control_enemy(self, t):
        if self.freeze_timer:
            return
        t.ai_timer -= 1
        moved = self.move(t)
        if t.ai_timer <= 0 or (not moved and random.random() < 0.3):
            t.ai_timer = random.randint(60, 240)
            r = random.random()
            if r < 0.4:
                d = DOWN
            elif r < 0.65:
                d = LEFT if t.x > 96 else RIGHT
            else:
                d = random.randint(0, 3)
            self.turn(t, d)
        if random.random() < (0.1 if not moved else 0.02):
            self.fire(t)

    def turn(self, t, d):
        if d == t.dir:
            return
        if d % 2 != t.dir % 2:
            # Snap to the half-block grid when turning, like the original, so tanks fit through gaps.
            if t.dir % 2 == 0:
                t.y = round(t.y / TILE) * TILE
            else:
                t.x = round(t.x / TILE) * TILE
        t.dir = d

    def move(self, t):
        remaining = t.speed
        while remaining > 0:
            s = min(1.0, remaining)
            nx, ny = t.x + DX[t.dir] * s, t.y + DY[t.dir] * s
            if self.blocked(t, nx, ny):
                return False
            t.x, t.y = nx, ny
            remaining -= s
        return True

    def blocked(self, t, nx, ny):
        r = (nx, ny, TANK, TANK)
        if self.rect_tiles(r, TANK_BLOCKERS) or overlap(r, BASE_RECT):
            return True
        for o in self.tanks:
            # Tanks that already overlap (e.g. after a spawn) may drive apart.
            if o is not t and overlap(r, o.rect) and not overlap(t.rect, o.rect):
                return True
        return False

    def rect_tiles(self, r, kinds):
        """Return the cells of the given kinds under rect r (out of bounds counts as a hit)."""
        x, y, w, h = r
        if x < 0 or y < 0 or x + w > SIZE or y + h > SIZE:
            return [None]
        hits = []
        for row in range(int(y // TILE), int((y + h - 0.001) // TILE) + 1):
            for col in range(int(x // TILE), int((x + w - 0.001) // TILE) + 1):
                if self.map[row][col] in kinds:
                    hits.append((col, row))
        return hits

    def fire(self, t):
        if t.cooldown or sum(1 for b in self.bullets if b.owner is t) >= t.max_bullets:
            return
        cx, cy = t.x + 8 + DX[t.dir] * 8, t.y + 8 + DY[t.dir] * 8
        self.bullets.append(Bullet(cx, cy, t.dir, t.bullet_speed, t, t.player and t.level >= 3))
        t.cooldown = 12 if t.player else 30
        if t.player:
            self.events.append('fire')

    # ---------- bullets ----------
    def update_bullets(self):
        for b in self.bullets:
            steps = math.ceil(b.speed)
            for _ in range(steps):
                b.x += DX[b.dir] * b.speed / steps
                b.y += DY[b.dir] * b.speed / steps
                if self.bullet_collide(b):
                    break
        # Player and enemy bullets cancel each other out.
        for i, a in enumerate(self.bullets):
            for b in self.bullets[i + 1:]:
                if a.alive and b.alive and a.owner.player != b.owner.player and overlap(a.rect, b.rect):
                    a.alive = b.alive = False
        self.bullets = [b for b in self.bullets if b.alive]

    def bullet_collide(self, b):
        r = b.rect
        if b.x < 2 or b.y < 2 or b.x > SIZE - 2 or b.y > SIZE - 2:
            self.kill_bullet(b, 'steel')
            return True
        if overlap(r, BASE_RECT):
            self.kill_bullet(b, None)
            if self.base_alive and not b.owner.player:   # kids can't blow up their own eagle
                self.base_alive = False
                self.explosions.append([104, 200, True, 0])
                self.events.append('explode')
                self.game_over()
            return True
        hits = self.rect_tiles(r, {BRICK, STEEL})
        if hits:
            self.destroy_tiles(b, hits[0])
            return True
        for t in self.tanks:
            if t is b.owner or t.spawn or not overlap(r, t.rect):
                continue
            if b.owner.player == t.player:
                if not t.player:
                    continue        # enemy bullets pass through enemies
                if not t.shield:
                    t.frozen = 120  # friendly fire just freezes your sibling for a moment
                b.alive = False
                return True
            b.alive = False
            self.hit_tank(t, b.owner)
            return True
        return False

    def kill_bullet(self, b, sound):
        b.alive = False
        self.explosions.append([b.x, b.y, False, 0])
        if sound and b.owner.player:
            self.events.append(sound)

    def destroy_tiles(self, b, hit):
        col, row = hit
        # Knock out a strip of bricks as wide as a tank, perpendicular to the bullet.
        if b.dir in (UP, DOWN):
            cells = [(c, row) for c in range(int((b.x - 6) // TILE), int((b.x + 5.999) // TILE) + 1)]
        else:
            cells = [(col, r) for r in range(int((b.y - 6) // TILE), int((b.y + 5.999) // TILE) + 1)]
        broke = False
        for c, r in cells:
            if 0 <= c < N and 0 <= r < N:
                tile = self.map[r][c]
                if tile == BRICK or (tile == STEEL and b.power):
                    self.map[r][c] = EMPTY
                    broke = True
        self.kill_bullet(b, 'brick' if broke else 'steel')

    def hit_tank(self, t, shooter):
        if t.player:
            if not t.shield:
                self.kill_player(t)
            return
        if t.bonus:
            t.bonus = False
            self.spawn_powerup()
        t.hp -= 1
        if t.hp > 0:
            self.events.append('armor')
            return
        self.tanks.remove(t)
        self.explosions.append([t.x + 8, t.y + 8, True, 0])
        self.events.append('explode')
        if shooter.player:
            self.pinfo[shooter.slot]['score'] += ENEMY_TYPES[t.kind]['score']

    def kill_player(self, t):
        self.tanks.remove(t)
        self.explosions.append([t.x + 8, t.y + 8, True, 0])
        self.events.append('explode')
        info = self.pinfo[t.slot]
        info['lives'] -= 1
        info['level'] = 0
        if info['lives'] > 0:
            self.spawn_player(t.slot)

    # ---------- power-ups ----------
    def spawn_powerup(self):
        self.powerup = {'kind': random.choice(POWERUPS), 'x': random.randint(0, 12) * 16,
                        'y': random.randint(0, 11) * 16, 'timer': 1200}
        self.events.append('bonus')

    def update_powerup(self):
        p = self.powerup
        if not p:
            return
        p['timer'] -= 1
        if p['timer'] <= 0:
            self.powerup = None
            return
        for t in self.tanks:
            if t.player and not t.spawn and overlap(t.rect, (p['x'], p['y'], 16, 16)):
                self.apply_powerup(p['kind'], t)
                self.powerup = None
                return

    def apply_powerup(self, kind, t):
        info = self.pinfo[t.slot]
        info['score'] += 500
        if kind == 'star':
            t.level = info['level'] = min(3, t.level + 1)
        elif kind == 'grenade':
            for e in [e for e in self.tanks if not e.player]:
                self.tanks.remove(e)
                self.explosions.append([e.x + 8, e.y + 8, True, 0])
            self.events.append('explode')
        elif kind == 'helmet':
            t.shield = 600
        elif kind == 'shovel':
            self.shovel_timer = 1200
            self.set_base_wall(STEEL)
        elif kind == 'timer':
            self.freeze_timer = 600
        elif kind == 'tank':
            info['lives'] += 1
        self.events.append('powerup')

    def set_base_wall(self, tile):
        for c, r in BASE_WALL:
            if not any(overlap((c * TILE, r * TILE, TILE, TILE), t.rect) for t in self.tanks):
                self.map[r][c] = tile

    # ---------- network snapshot ----------
    def snapshot(self):
        tanks = []
        for t in self.tanks:
            flags = (1 if t.shield else 0) | (2 if t.frozen else 0) | (4 if t.bonus else 0) | (8 if t.spawn else 0)
            tanks.append([round(t.x, 2), round(t.y, 2), t.dir, t.kind, t.hp, t.level, flags])
        p = self.powerup
        snap = {
            't': 'state', 'tick': self.tick, 'state': self.state, 'stage': self.stage,
            'map': ''.join(''.join(row) for row in self.map),
            'base': self.base_alive,
            'tanks': tanks,
            'bullets': [[round(b.x, 1), round(b.y, 1)] for b in self.bullets],
            'powerup': [p['x'], p['y'], p['kind'], p['timer']] if p else None,
            'boom': [[round(e[0]), round(e[1]), e[2], e[3]] for e in self.explosions],
            'players': self.pinfo,
            'conn': [self.connected(0), self.connected(1)],
            'left': len(self.queue),
            'events': self.events,
        }
        self.events = []
        return snap


game = Game()
STATIC = pathlib.Path(__file__).parent / 'static'


async def index(request):
    return web.FileResponse(STATIC / 'index.html')


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=10)
    await ws.prepare(request)
    slot = game.join(ws)
    print('client connected as', 'spectator' if slot is None else 'Player %d' % (slot + 1))
    await ws.send_json({'t': 'hello', 'slot': slot})
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                game.handle(ws, json.loads(msg.data))
    finally:
        game.leave(ws)
        print('client disconnected', '' if slot is None else '(Player %d)' % (slot + 1))
    return ws


async def game_loop():
    loop = asyncio.get_running_loop()
    next_tick = loop.time()
    while True:
        game.update()
        data = json.dumps(game.snapshot())
        socks = [ws for ws in game.clients if not ws.closed]
        if socks:
            await asyncio.gather(*(ws.send_str(data) for ws in socks), return_exceptions=True)
        next_tick += 1 / FPS
        delay = next_tick - loop.time()
        if delay < -0.5:          # fell far behind (e.g. laptop slept) - don't try to catch up
            next_tick = loop.time()
        await asyncio.sleep(max(0, delay))


async def start_loop(app):
    app['loop_task'] = asyncio.create_task(game_loop())


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))   # no packet is sent; just picks the LAN interface
            return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'


def main():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/ws', ws_handler)
    app.router.add_static('/static', STATIC)
    app.on_startup.append(start_loop)
    print('=' * 50)
    print(' Tank Battle server is running!')
    print(' On each computer, open:  http://%s:%d' % (lan_ip(), PORT))
    print('=' * 50)
    web.run_app(app, port=PORT, print=None)


if __name__ == '__main__':
    main()
