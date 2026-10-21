"""Shared combat primitives: Fighter physics/health, Attack hitboxes, floating text."""
import pygame
from . import settings as S


class Fighter:
    def __init__(self, x, y, w, h, max_hp, hurt_invuln=0.0, hurt_stun=0.0):
        self.rect = pygame.Rect(int(x), int(y), w, h)
        self.px, self.py = float(x), float(y)
        self.vx = self.vy = 0.0
        self.on_ground = False
        self.facing = 1
        self.max_hp = max_hp
        self.hp = max_hp
        self.hurt_invuln = hurt_invuln
        self.hurt_stun = hurt_stun
        self.invuln = self.flash = self.stun = 0.0
        self.attack = None  # the Attack this fighter currently owns, if any
        self.world_width = S.LEVEL_WIDTH

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def tick_timers(self, dt):
        self.invuln = max(0.0, self.invuln - dt)
        self.flash = max(0.0, self.flash - dt)
        self.stun = max(0.0, self.stun - dt)

    def take_damage(self, amount, direction, knockback) -> bool:
        """Apply a hit. Returns False if ignored (dead or temporarily immune)."""
        if not self.alive or self.invuln > 0:
            return False
        self.hp = max(0, self.hp - amount)
        self.invuln = self.hurt_invuln
        self.stun = self.hurt_stun
        self.flash = 0.15
        self.vx = direction * knockback
        self.vy = -260.0
        self.on_ground = False
        if self.attack and not self.attack.fired:
            self.attack.cancel()
        return True

    def apply_friction(self, dt):
        self.vx *= max(0.0, 1.0 - 6.0 * dt)

    def apply_physics(self, dt, platforms):
        """Gravity + movement. Platforms (and ground) are one-way: land from above."""
        self.vy = min(self.vy + S.GRAVITY * dt, S.MAX_FALL_SPEED)
        self.px = max(0.0, min(self.px + self.vx * dt, self.world_width - self.rect.width))
        prev_bottom = self.rect.bottom
        self.py += self.vy * dt
        self.rect.topleft = (round(self.px), round(self.py))
        self.on_ground = False
        if self.vy >= 0:
            for p in platforms:
                if (self.rect.right > p.left and self.rect.left < p.right
                        and prev_bottom <= p.top + 2 and self.rect.bottom >= p.top):
                    self.rect.bottom = p.top
                    self.py = float(self.rect.y)
                    self.vy = 0.0
                    self.on_ground = True
                    break


class Attack:
    """A hitbox that follows its owner. Each target can be hit at most once."""

    fired = False  # True once a projectile has left its owner (can't be cancelled)

    def __init__(self, owner, damage, knockback, reach, height, delay, duration, centered=False):
        self.centered = centered
        self.crit = False
        self.color = (255, 255, 255)
        self.owner = owner
        self.damage = damage
        self.knockback = knockback
        self.facing = owner.facing
        self.delay = delay
        self.time_left = duration
        self.hit_ids = set()
        self.rect = pygame.Rect(0, 0, reach, height)
        self._reposition()

    def _reposition(self):
        o = self.owner.rect
        self.rect.centery = o.centery
        if self.centered:
            self.rect.centerx = o.centerx
        elif self.facing > 0:
            self.rect.left = o.right - 4
        else:
            self.rect.right = o.left + 4

    @property
    def active(self) -> bool:
        return self.delay <= 0 and self.time_left > 0

    @property
    def finished(self) -> bool:
        return self.time_left <= 0

    def cancel(self):
        self.time_left = 0.0

    def update(self, dt):
        if self.delay > 0:
            self.delay -= dt
        else:
            self.time_left -= dt
        self._reposition()

    def try_hit(self, target) -> bool:
        """True exactly once per target while overlapping an active hitbox."""
        if not self.active or target is self.owner or id(target) in self.hit_ids:
            return False
        if not self.rect.colliderect(target.rect):
            return False
        self.hit_ids.add(id(target))
        return True


class Projectile(Attack):
    """A bolt/arrow. Leaves the owner after `delay`, flies straight, can pierce."""

    def __init__(self, owner, damage, knockback, size, delay, speed, max_range, pierce=0):
        super().__init__(owner, damage, knockback, size[0], size[1], delay, 999.0)
        self.speed = speed * owner.facing
        self.max_range = max_range
        self.pierce = pierce
        self.hits = 0
        self.travelled = 0.0
        self.fx = float(self.rect.x)

    @property
    def fired(self):
        return self.delay <= 0

    def _reposition(self):
        o = self.owner.rect
        self.rect.centery = o.centery - 8
        if self.facing > 0:
            self.rect.left = o.right
        else:
            self.rect.right = o.left

    def update(self, dt):
        if self.delay > 0:
            self.delay -= dt
            self._reposition()
            self.fx = float(self.rect.x)
            return
        step = self.speed * dt
        self.fx += step
        self.rect.x = round(self.fx)
        self.travelled += abs(step)
        if self.travelled >= self.max_range or self.rect.right < 0 or self.rect.left > getattr(self.owner, 'world_width', S.LEVEL_WIDTH):
            self.time_left = 0.0

    def try_hit(self, target) -> bool:
        if not super().try_hit(target):
            return False
        self.hits += 1
        if self.hits > self.pierce:
            self.time_left = 0.0
        return True


class FloatingText:
    def __init__(self, text, pos, color, life=0.9):
        self.text, self.color = text, color
        self.x, self.y = pos
        self.life = self.max_life = life

    def update(self, dt):
        self.life -= dt
        self.y -= 45 * dt
