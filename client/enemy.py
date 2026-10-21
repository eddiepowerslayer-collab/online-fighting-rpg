from . import settings as S
from .combat import Attack, Fighter, Projectile
from .dungeons import enemy_scaling
from .progression import base_xp

IDLE, PURSUING, ATTACKING, HURT, DEFEATED = "idle", "pursuing", "attacking", "hurt", "defeated"
DEFEAT_LINGER = 1.0


class Enemy(Fighter):
    """`level` is the enemy level: HP, damage and XP all scale with it."""

    def __init__(self, kind, x, level=1):
        self.kind = kind
        self.cfg = cfg = S.ENEMY_TYPES[kind]
        hp_m, dmg_m = enemy_scaling(level)
        hp = max(1, round(cfg["hp"] * S.DIFFICULTY["enemy_hp"] * hp_m))
        super().__init__(x, S.GROUND_Y - cfg["height"], cfg["width"], cfg["height"], hp,
                         S.ENEMY_HIT_INVULN, cfg["hurt_time"])
        self.level = level
        self.spawn_x = x
        self.state = IDLE
        self.state_t = 0.0
        self.cooldown = 0.0
        self.damage = max(1, round(cfg["damage"] * S.DIFFICULTY["enemy_damage"] * dmg_m))
        self.xp = max(1, round(cfg["xp_weight"] * base_xp(level) / S.KILLS_PER_LEVEL
                               * S.DIFFICULTY["xp"]))

    @property
    def name(self):
        return self.cfg["name"]

    @property
    def ranged(self):
        return bool(self.cfg.get("ranged"))

    @property
    def removable(self):
        return self.state == DEFEATED and self.state_t >= DEFEAT_LINGER

    @property
    def telegraphing(self):
        return self.state == ATTACKING and self.attack is not None and self.attack.delay > 0

    def take_damage(self, amount, direction, knockback):
        hit = super().take_damage(amount, direction, knockback)
        if hit:
            self.state, self.state_t = (HURT, 0.0) if self.alive else (DEFEATED, 0.0)
            if self.state == HURT:
                self.cooldown = max(self.cooldown, 0.3)
        return hit

    def _start_attack(self, sign):
        cfg = self.cfg
        self.state, self.vx = ATTACKING, 0.0
        self.state_t = cfg["windup"] + 0.25
        if self.ranged:
            atk = Projectile(self, self.damage, cfg["knockback"], (24, 12), cfg["windup"],
                             cfg["proj_speed"], cfg["attack_range"] + 80)
            atk.color = cfg["color"]
        else:
            atk = Attack(self, self.damage, cfg["knockback"], cfg["attack_range"] + 14,
                         int(self.rect.height * 0.8), cfg["windup"], 0.15)
        self.attack = atk
        return atk

    def update(self, dt, player, platforms):
        """Advance AI one frame. Returns a new Attack if one was started."""
        self.tick_timers(dt)
        self.cooldown = max(0.0, self.cooldown - dt)
        cfg, new_attack = self.cfg, None
        dx = player.rect.centerx - self.rect.centerx
        dy = abs(player.rect.centery - self.rect.centery)
        dist, sign = abs(dx), (1 if dx >= 0 else -1)

        if self.state == DEFEATED:
            self.state_t += dt
            self.apply_friction(dt)
        elif self.state == HURT:
            self.apply_friction(dt)
            if self.stun <= 0:
                self.state = PURSUING
        elif self.state == ATTACKING:
            self.vx = 0.0
            self.state_t -= dt
            if self.state_t <= 0:
                self.state, self.cooldown, self.attack = PURSUING, cfg["attack_cooldown"], None
        elif not player.alive:
            self.state, self.vx = IDLE, 0.0
        elif self.state == IDLE:
            self.vx = 0.0
            if dist < cfg["aggro"]:
                self.state = PURSUING
        else:  # PURSUING
            self.facing = sign
            rng = cfg["attack_range"]
            if dist > cfg["aggro"] * 1.6:
                self.state, self.vx = IDLE, 0.0
            elif dist <= rng and dy < (90 if self.ranged else 60) and self.cooldown <= 0:
                new_attack = self._start_attack(sign)
            elif self.ranged and dist < rng * 0.35:
                self.vx = -sign * cfg["speed"]          # back away to keep distance
            elif self.ranged:
                self.vx = sign * cfg["speed"] if dist > rng * 0.8 else 0.0
            else:
                self.vx = sign * cfg["speed"] if dist > rng * 0.7 else 0.0
        self.apply_physics(dt, platforms)
        return new_attack
