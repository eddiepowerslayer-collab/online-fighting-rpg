"""Authoritative arena simulation (pure logic: no sockets, no pygame display).
Clients only send inputs; the server decides movement, hits, damage, kills and results.
Supports 1v1..5v5 (two teams, no friendly fire) and free-for-all."""
import random

import pygame

from client import settings as S
from client.character import Character
from client.dungeons import enemy_level, spawn_plan
from client.enemy import DEFEATED, Enemy
from client.items import item_to_dict, roll_item
from client.player import Player
from client.professions import MATERIALS, MATERIAL_WEIGHTS
from client.progression import xp_level_modifier
from client.skills import BASIC_IDS, SKILLS_BY_ID
from shared import modes as M
from shared.protocol import ARENA_ACTIONS

ARENA_WIDTH = 1800
ARENA_DAMAGE_SCALE = 0.4        # slows fights down so they aren't one-shots
GEAR_CAP = 10                   # normalized ruleset: max gear bonus per stat
RANK_CAP = 3                    # normalized ruleset: max skill rank
DISCONNECT_GRACE = 30.0         # seconds a dropped player can reconnect before forfeiting
PLATFORMS = [(330, 370, 240), (780, 300, 240), (1230, 370, 240)]
TEAM_COLORS = [(70, 140, 255), (255, 90, 90)]


def normalized_character(data: dict, ruleset: str = "normalized") -> Character:
    """Build the character used in the arena. 'normalized' makes everyone comparable: level
    capped at ARENA_LEVEL, stat points scaled to that budget, gear and skill ranks capped,
    no god skills. 'open' uses the real character."""
    ch = Character.from_dict(data)
    if ruleset == "open":
        return ch
    pr = ch.progression
    lvl = min(pr.level, M.ARENA_LEVEL)
    budget = 3 * (lvl - 1)
    total = sum(pr.allocated.values())
    if total > budget:
        pr.allocated = {s: v * budget // total for s, v in pr.allocated.items()}
    pr.level, pr.xp, pr.stat_points, pr.skill_points = lvl, 0, 0, 0
    ch.gear_cap = GEAR_CAP
    ch.skills = {sid: min(rank, RANK_CAP) for sid, rank in ch.skills.items()
                 if not SKILLS_BY_ID[sid].god and SKILLS_BY_ID[sid].unlock_level <= lvl}
    for key, sid in list(ch.bindings.items()):          # drop bindings to skills that don't exist here
        if sid not in BASIC_IDS and sid not in ch.skills:
            ch.bindings[key] = None
    return ch


def balance_teams(entries):
    """Snake-draft by level so both teams are about equally strong. Returns team index list."""
    order = sorted(range(len(entries)), key=lambda i: -entries[i]["level"])
    teams = [0] * len(entries)
    for rank, i in enumerate(order):
        teams[i] = (0, 1, 1, 0)[rank % 4]
    return teams


class ArenaPlayer:
    def __init__(self, pid, entry, team, ruleset, rng):
        self.pid = pid
        self.char_id, self.account_id = entry["char_id"], entry["account_id"]
        self.name, self.team = entry["name"], team
        self.character = normalized_character(entry["data"], ruleset)
        self.body = Player(self.character, rng)
        self.body.world_width = ARENA_WIDTH
        self.body.arena_player = self
        self.axis = 0
        self.pending = set()
        self.kills = self.deaths = 0
        self.respawn_t = 0.0
        self.connected = True
        self.disconnect_t = 0.0
        self.left = False            # forfeited / left the match
        self.real_level = entry.get("level", 1)
        self.coop_xp = self.coop_gold = 0      # co-op rewards earned so far
        self.coop_loot, self.coop_mats = [], {}


class Arena:
    def __init__(self, match_id, mode, entries, rng=None, ruleset="normalized"):
        if mode not in M.MODE_ORDER:
            raise ValueError("unknown mode")
        self.match_id, self.mode, self.ruleset = match_id, mode, ruleset
        self.rng = rng or random.Random()
        teams = (balance_teams(entries) if M.is_team_mode(mode)
                 else [0] * len(entries) if mode == "coop" else list(range(len(entries))))
        self.players = [ArenaPlayer(i, e, teams[i], ruleset, self.rng) for i, e in enumerate(entries)]
        ground = pygame.Rect(0, S.GROUND_Y, ARENA_WIDTH, 100)
        self.platforms = [ground] + [pygame.Rect(x, y, w, S.PLATFORM_THICKNESS) for x, y, w in PLATFORMS]
        self.team_scores = [0, 0]
        self.attacks, self.events = [], []
        self.state = "countdown"
        self.countdown = M.COUNTDOWN
        self.time_left = M.TIME_LIMIT
        self.tick = 0
        self.aborted = False
        self.target = M.kill_target(mode)
        self.enemies = []
        if mode == "coop":
            self._init_coop()
        for ap in self.players:
            self._spawn(ap, invuln=0.0)

    # ---------------------------------------------------------- co-op PvE
    def _init_coop(self):
        d = M.COOP_DUNGEON
        self.coop_level = enemy_level(d)
        plan = spawn_plan(d)
        plan = plan[:7] + [plan[-1]]                      # 7 enemies + the boss
        n = len(self.players)
        for i, (kind, x) in enumerate(plan):
            e = Enemy(kind, 500 + (x - 900) * 1200 // 3900, self.coop_level)
            e.world_width = ARENA_WIDTH
            e.max_hp = e.hp = round(e.max_hp * (1 + 0.5 * (n - 1)))     # tougher with more players
            e.eid = 100 + i
            e.boss = i == len(plan) - 1
            self.enemies.append(e)
        self.time_left = M.COOP_TIME_LIMIT

    def _coop_enemy_down(self, enemy, killer):
        killer.kills += 1
        self.events.append({"k": "kill", "t": enemy.eid, "by": killer.pid, "n": enemy.name})
        for ap in self.players:
            if ap.left:
                continue
            ap.coop_xp += max(1, round(enemy.xp * xp_level_modifier(ap.real_level, enemy.level)))
            ap.coop_gold += self.rng.randint(5, 15) * (1 + enemy.level // 5)
            if self.rng.random() < enemy.cfg["item_chance"] * (3 if enemy.boss else 1):
                ap.coop_loot.append(item_to_dict(roll_item(self.rng, M.COOP_DUNGEON, enemy.level)))
            if self.rng.random() < 0.4:
                m = self.rng.choices(MATERIALS, weights=MATERIAL_WEIGHTS)[0]
                ap.coop_mats[m] = ap.coop_mats.get(m, 0) + self.rng.randint(1, 2)

    def _step_coop(self, dt):
        alive = [ap for ap in self.players if not ap.left and ap.body.alive]
        for e in self.enemies:
            if alive:
                target = min(alive, key=lambda ap: abs(ap.body.rect.centerx - e.rect.centerx)).body
            else:
                target = self.players[0].body
            atk = e.update(dt, target, self.platforms)
            if atk:
                self.attacks.append(atk)
        self.enemies = [e for e in self.enemies if not e.removable]

    # ---------------------------------------------------------- setup
    def _spawn_point(self, ap):
        h = S.PLAYER["height"]
        if M.is_team_mode(self.mode):
            mates = [p for p in self.players if p.team == ap.team]
            slot = mates.index(ap)
            x = 150 + slot * 60 if ap.team == 0 else ARENA_WIDTH - 150 - slot * 60 - 34
            return x, S.GROUND_Y - h, (1 if ap.team == 0 else -1)
        if self.mode == "coop":
            return 150 + ap.pid * 60, S.GROUND_Y - h, 1
        n = len(self.players)
        x = 200 + (ARENA_WIDTH - 400) * ap.pid // max(1, n - 1) if n > 1 else ARENA_WIDTH // 2
        return x, S.GROUND_Y - h, (1 if x < ARENA_WIDTH // 2 else -1)

    def _spawn(self, ap, invuln=2.0):
        x, y, facing = self._spawn_point(ap)
        ap.body.respawn((x, y), facing, invuln)

    def player(self, pid):
        return self.players[pid] if 0 <= pid < len(self.players) else None

    def set_input(self, pid, axis, actions):
        ap = self.player(pid)
        if ap is None or ap.left:
            return
        ap.axis = axis if axis in (-1, 0, 1) else 0
        ap.pending |= {a for a in actions if a in ARENA_ACTIONS}

    def set_connected(self, pid, connected):
        ap = self.player(pid)
        if ap and not ap.left:
            ap.connected = connected
            ap.disconnect_t = 0.0
            if not connected:
                ap.axis, ap.pending = 0, set()

    def leave(self, pid):
        ap = self.player(pid)
        if ap:
            ap.left = True
            ap.body.hp = 0
            ap.axis, ap.pending = 0, set()

    # ---------------------------------------------------------- simulation
    def step(self, dt):
        if self.state == "ended":
            return
        self.tick += 1
        if self.state == "countdown":
            self.countdown -= dt
            if self.countdown <= 0:
                self.state = "active"
            return
        self.time_left -= dt
        for ap in self.players:
            if ap.left:
                continue
            if not ap.connected:
                ap.disconnect_t += dt
                if ap.disconnect_t > DISCONNECT_GRACE:
                    self.leave(ap.pid)
                    continue
            body = ap.body
            if not body.alive:
                ap.respawn_t -= dt
                if ap.respawn_t <= 0:
                    self._spawn(ap)
                else:
                    body.update(dt, 0, (), self.platforms)
                continue
            actions, ap.pending = ap.pending, set()
            atk = body.update(dt, ap.axis if ap.connected else 0, actions, self.platforms)
            body.messages.clear()
            if atk:
                self.attacks.append(atk)
        if self.mode == "coop":
            self._step_coop(dt)
        self._process_attacks(dt)
        self._check_end()

    def _process_attacks(self, dt):
        team_mode = M.is_team_mode(self.mode)
        for atk in self.attacks:
            atk.update(dt)
            if isinstance(atk.owner, Enemy):
                self._enemy_attack(atk)
                continue
            owner = atk.owner.arena_player
            if self.mode == "coop":
                for e in self.enemies:
                    if e.alive and atk.try_hit(e):
                        direction = 1 if e.rect.centerx >= owner.body.rect.centerx else -1
                        if e.take_damage(atk.damage, direction, atk.knockback):
                            self.events.append({"k": "hit", "x": e.rect.centerx, "y": e.rect.top, "d": atk.damage,
                                                "c": int(atk.crit), "t": e.eid, "by": owner.pid})
                            if not e.alive:
                                self._coop_enemy_down(e, owner)
                continue
            for ap in self.players:
                if ap is owner or ap.left or not ap.body.alive:
                    continue
                if team_mode and ap.team == owner.team:
                    continue                                   # no friendly fire
                if atk.try_hit(ap.body):
                    direction = 1 if ap.body.rect.centerx >= owner.body.rect.centerx else -1
                    dmg = max(1, round(atk.damage * ARENA_DAMAGE_SCALE * (1 - ap.body.damage_reduction)))
                    if ap.body.take_damage(dmg, direction, atk.knockback):
                        r = ap.body.rect
                        self.events.append({"k": "hit", "x": r.centerx, "y": r.top, "d": dmg,
                                            "c": int(atk.crit), "t": ap.pid, "by": owner.pid})
                        if not ap.body.alive:
                            self._kill(owner, ap)
        self.attacks = [a for a in self.attacks if not a.finished]

    def _enemy_attack(self, atk):
        for ap in self.players:
            if ap.left or not ap.body.alive:
                continue
            if atk.try_hit(ap.body):
                direction = 1 if ap.body.rect.centerx >= atk.owner.rect.centerx else -1
                dmg = max(1, round(atk.damage * (1 - ap.body.damage_reduction)))
                if ap.body.take_damage(dmg, direction, atk.knockback):
                    r = ap.body.rect
                    self.events.append({"k": "hit", "x": r.centerx, "y": r.top, "d": dmg, "c": 0,
                                        "t": ap.pid, "by": atk.owner.eid})
                    if not ap.body.alive:
                        ap.deaths += 1
                        ap.respawn_t = M.RESPAWN_TIME

    def _kill(self, killer, victim):
        killer.kills += 1
        victim.deaths += 1
        victim.respawn_t = M.RESPAWN_TIME
        if M.is_team_mode(self.mode):
            self.team_scores[killer.team] += 1
        self.events.append({"k": "kill", "t": victim.pid, "by": killer.pid})

    def _active_players(self):
        return [p for p in self.players if not p.left]

    def _check_end(self):
        alive = self._active_players()
        if not alive:
            self.aborted = True
            self.state = "ended"
        elif self.mode == "coop":
            if not any(e.alive for e in self.enemies):
                self.state = "ended"
        elif M.is_team_mode(self.mode):
            if max(self.team_scores) >= self.target or len({p.team for p in alive}) < 2:
                self.state = "ended"
        elif max(p.kills for p in self.players) >= self.target or len(alive) < 2:
            self.state = "ended"
        if self.time_left <= 0:
            self.state = "ended"

    # ---------------------------------------------------------- results / snapshots
    def results(self) -> dict:
        team_mode = M.is_team_mode(self.mode)
        if self.mode == "coop":
            won = not any(e.alive for e in self.enemies)
            rows = [{"pid": p.pid, "name": p.name, "team": 0, "kills": p.kills, "deaths": p.deaths,
                     "result": "win" if won else "loss", "left": p.left, "char_id": p.char_id,
                     "account_id": p.account_id} for p in self.players]
            return {"mode": self.mode, "aborted": self.aborted, "team_scores": self.team_scores, "players": rows}
        if team_mode:
            a, b = self.team_scores
            remaining = {p.team for p in self._active_players()}
            if len(remaining) == 1:                      # the other team forfeited
                winners = remaining
            else:
                winners = {0} if a > b else {1} if b > a else set()
            outcome = {p.pid: ("draw" if not winners else "win" if p.team in winners else "loss")
                       for p in self.players}
        else:
            best = max(p.kills for p in self.players)
            top = [p for p in self.players if p.kills == best and not p.left]
            only = [p for p in self._active_players()]
            if len(only) == 1:
                top = only
            outcome = {p.pid: ("loss" if p not in top else "win" if len(top) == 1 else "draw")
                       for p in self.players}
        rows = [{"pid": p.pid, "name": p.name, "team": p.team, "kills": p.kills, "deaths": p.deaths,
                 "result": outcome[p.pid], "left": p.left, "char_id": p.char_id,
                 "account_id": p.account_id} for p in self.players]
        return {"mode": self.mode, "aborted": self.aborted, "team_scores": self.team_scores,
                "players": rows}

    def snapshot(self) -> dict:
        players = []
        for ap in self.players:
            b = ap.body
            players.append({"id": ap.pid, "x": b.rect.x, "y": b.rect.y, "f": b.facing, "hp": b.hp,
                            "mhp": b.max_hp, "al": int(b.alive and not ap.left), "inv": int(b.invuln > 0),
                            "rt": round(max(0.0, ap.respawn_t), 1) if not b.alive and not ap.left else 0,
                            "k": ap.kills, "d": ap.deaths, "buff": int(bool(b.buffs)),
                            "dc": int(not ap.connected), "dodge": int(b.dodge_t > 0)})
        atks = []
        for a in self.attacks:
            if a.active:
                kind = 1 if hasattr(a, "speed") else 2 if a.centered else 0
                atks.append([a.rect.x, a.rect.y, a.rect.w, a.rect.h, kind, "%02x%02x%02x" % tuple(a.color)])
        enemies = [[e.eid, e.rect.x, e.rect.y, e.facing, e.hp, e.max_hp, e.kind, int(e.alive),
                    int(e.telegraphing), int(e.boss)] for e in self.enemies] if self.mode == "coop" else None
        snap = {"t": "snap", "tick": self.tick, "state": self.state,
                "cd": round(max(0.0, self.countdown), 1), "tl": round(max(0.0, self.time_left), 1),
                "ts": list(self.team_scores), "players": players, "atks": atks, "ev": self.events}
        if enemies is not None:
            snap["en"] = enemies
        self.events = []
        return snap

    def you(self, pid) -> dict:
        """Private per-player info (hotbar, cooldowns, energy) attached to that player's snapshots."""
        ap = self.player(pid)
        return {"skills": ap.body.hotbar(), "energy": int(ap.body.energy)}
