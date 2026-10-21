"""One endeavor (a run through a dungeon level). Temporary combat state only;
rewards are written back onto the permanent Character."""
import random
from collections import deque

import pygame

from . import settings as S
from .camera import Camera
from .combat import FloatingText
from .enemy import Enemy
from .dungeons import enemy_level, spawn_plan
from .items import roll_item
from .professions import MATERIALS, MATERIAL_WEIGHTS
from .player import Player
from .professions import PROFESSION_UNLOCK_LEVEL
from .progression import xp_level_modifier
from .skills import SKILLS_BY_ID

WHITE, RED, GOLD, GREEN, BLUE = (255, 255, 255), (255, 90, 90), (250, 210, 60), (120, 230, 120), (120, 190, 255)


class Pickup:
    def __init__(self, kind, value, midbottom):
        self.kind, self.value = kind, value
        self.life = 60.0 if kind == "item" else 15.0
        self.rect = pygame.Rect(0, 0, 18, 18)
        self.rect.midbottom = midbottom


class Run:
    def __init__(self, character, dungeon_level=1, rng=None):
        self.character = character
        self.level = dungeon_level
        self.rng = rng or random.Random()
        ground = pygame.Rect(0, S.GROUND_Y, S.LEVEL_WIDTH, S.SCREEN_H - S.GROUND_Y)
        self.platforms = [ground] + [pygame.Rect(x, y, w, S.PLATFORM_THICKNESS)
                                     for x, y, w in S.PLATFORMS]
        self.player = Player(character, self.rng)
        self.enemy_level = enemy_level(dungeon_level)
        self.enemies = [Enemy(k, x, self.enemy_level) for k, x in spawn_plan(dungeon_level)]
        self.exit_rect = pygame.Rect(S.LEVEL_WIDTH - 160, S.GROUND_Y - 130, 70, 130)
        self.attacks, self.texts, self.pickups, self.respawn_queue = [], [], [], []
        self.messages = deque(maxlen=4)
        self.camera = Camera(S.LEVEL_WIDTH, S.SCREEN_W)
        self.camera.update(self.player.rect, 0, snap=True)
        self.level_up_flash = 0.0
        self.result = None          # None | "victory" | "defeat" | "retreat"
        self.end_timer = 0.0
        self.xp_gained = self.gold_gained = self.kills = self.levels_gained = self.bonus_gold = 0
        self.loot = []
        self.materials_gained = {}
        self.log(f"Dungeon Level {dungeon_level} (enemy level {self.enemy_level}). Reach the gate!", WHITE)

    def log(self, text, color=WHITE):
        self.messages.append((text, color, 6.0))

    # ---------- simulation ----------
    def step(self, dt, axis=0, actions=()):
        if self.result:
            return
        p = self.player
        new = p.update(dt, axis, actions, self.platforms)
        if new:
            self.attacks.append(new)
        for msg in p.messages:
            self.log(msg, BLUE)
        p.messages.clear()
        for e in self.enemies:
            a = e.update(dt, p, self.platforms)
            if a:
                self.attacks.append(a)

        for atk in self.attacks:
            atk.update(dt)
            targets = self.enemies if atk.owner is p else [p]
            for t in targets:
                if t.alive and atk.try_hit(t):
                    direction = 1 if t.rect.centerx >= atk.owner.rect.centerx else -1
                    dmg = atk.damage
                    if t is p:
                        dmg = max(1, round(dmg * (1 - p.damage_reduction)))
                    if t.take_damage(dmg, direction, atk.knockback):
                        self._on_hit(atk, t, dmg)
        self.attacks = [a for a in self.attacks if not a.finished]

        self._update_enemies(dt)
        self._update_pickups(dt)
        for t in self.texts:
            t.update(dt)
        self.texts = [t for t in self.texts if t.life > 0]
        self.messages = deque(((m, c, ttl - dt) for m, c, ttl in self.messages if ttl - dt > 0), maxlen=4)
        self.level_up_flash = max(0.0, self.level_up_flash - dt)
        self.camera.update(p.rect, dt)

        if not p.alive:
            self.end_timer -= dt
            if self.end_timer <= 0:
                self.result = "defeat"
        elif p.rect.colliderect(self.exit_rect):
            self.result = "victory"
            self.bonus_gold = 50 * self.level
            self.character.gold += self.bonus_gold
            self.character.complete_dungeon(self.level)

    def retreat(self):
        if not self.result:
            self.result = "retreat"

    def _on_hit(self, atk, target, dmg):
        p = self.player
        pos = (target.rect.centerx - 6, target.rect.top - 10)
        if target is p:
            self.texts.append(FloatingText(str(dmg), pos, RED))
            self.log(f"{atk.owner.name} hits you for {dmg}", RED)
            if not p.alive:
                self.end_timer = 2.0
                self.log("You were defeated.", RED)
            return
        label = f"CRIT {dmg}" if atk.crit else str(dmg)
        self.texts.append(FloatingText(label, pos, GOLD if atk.crit else WHITE))
        self.log(f"You hit {target.name} for {dmg}" + (" (critical!)" if atk.crit else ""), GOLD if atk.crit else WHITE)
        if not target.alive:
            self._reward(target)

    def _reward(self, enemy):
        p, ch = self.player, self.character
        xp = max(1, round(enemy.xp * ch.xp_multiplier
                          * xp_level_modifier(ch.progression.level, enemy.level)))
        self.kills += 1
        self.xp_gained += xp
        self.log(f"{enemy.name} defeated! +{xp} XP", GOLD)
        self.texts.append(FloatingText(f"+{xp} XP", (enemy.rect.centerx - 20, enemy.rect.top - 30), BLUE, 1.2))
        known = set(ch.skills)
        levels = ch.add_xp(xp)
        if levels:
            p.sync_after_level_up()
            self.levels_gained += levels
            self.level_up_flash = 2.0
            self.log(f"LEVEL UP! Level {ch.progression.level} ({ch.grade.label}). Spend points at home!", GOLD)
            for sid in set(ch.skills) - known:
                self.log(f"GOD SKILL GAINED: {SKILLS_BY_ID[sid].name}!", (255, 225, 100))
                self.level_up_flash = 3.0
            if ch.can_choose_profession and ch.progression.level - levels < PROFESSION_UNLOCK_LEVEL:
                self.log("You can now choose a profession at home!", GOLD)
        mult = S.DIFFICULTY["drop_chance"] * ch.drop_multiplier
        if self.rng.random() < enemy.cfg["drop_chance"] * mult:
            if self.rng.random() < 0.4:
                self.pickups.append(Pickup("health", 30, enemy.rect.midbottom))
            else:
                self.pickups.append(Pickup("coin", self.rng.randint(5, 15) * (1 + self.enemy_level // 5), enemy.rect.midbottom))
        if self.rng.random() < enemy.cfg["item_chance"] * mult:
            pos = (enemy.rect.centerx + 24, enemy.rect.bottom)
            self.pickups.append(Pickup("item", roll_item(self.rng, self.level, self.enemy_level), pos))
        if self.rng.random() < S.MATERIAL_DROP_CHANCE * mult:
            mat = self.rng.choices(MATERIALS, weights=MATERIAL_WEIGHTS)[0]
            qty = self.rng.randint(1, 2) + self.enemy_level // 200
            self.pickups.append(Pickup("material", (mat, qty), (enemy.rect.centerx - 24, enemy.rect.bottom)))
        self.respawn_queue.append([S.ENEMY_RESPAWN_TIME, enemy.kind, enemy.spawn_x])

    def _update_enemies(self, dt):
        p = self.player
        self.enemies = [e for e in self.enemies if not e.removable]
        for entry in self.respawn_queue:
            entry[0] -= dt
        due = [e for e in self.respawn_queue if e[0] <= 0 and abs(e[2] - p.rect.centerx) > 500]
        for entry in due:
            self.respawn_queue.remove(entry)
            self.enemies.append(Enemy(entry[1], entry[2], self.enemy_level))

    def _update_pickups(self, dt):
        p, ch = self.player, self.character
        keep = []
        for d in self.pickups:
            d.life -= dt
            if p.alive and d.rect.colliderect(p.rect):
                if d.kind == "coin":
                    ch.gold += d.value
                    self.gold_gained += d.value
                    self.log(f"+{d.value} gold", GOLD)
                elif d.kind == "health":
                    healed = min(d.value, p.max_hp - p.hp)
                    p.hp += healed
                    self.log(f"+{healed} HP", GREEN)
                elif d.kind == "material":
                    name, qty = d.value
                    ch.materials[name] = ch.materials.get(name, 0) + qty
                    self.materials_gained[name] = self.materials_gained.get(name, 0) + qty
                    self.log(f"+{qty} {name}", (200, 220, 255))
                else:
                    ch.inventory.append(d.value)
                    self.loot.append(d.value)
                    self.log(f"Found {d.value.rarity} {d.value.label}!", d.value.color)
            elif d.life > 0:
                keep.append(d)
        self.pickups = keep
