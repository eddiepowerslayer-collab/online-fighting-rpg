"""Deterministic XP / level / stat-point math. No pygame, no randomness."""
from dataclasses import dataclass, field

from .classes import STAT_NAMES

MAX_LEVEL = 3000
STAT_POINTS_PER_LEVEL = 3
SKILL_POINTS_PER_LEVEL = 1


STAT_LIMIT = 5000            # max points that can be placed in a single stat
SLOWDOWN_START = 25          # levels 1-25 keep the original fast curve
SLOWDOWN_SCALE = 40.0
SLOWDOWN_POWER = 1.25


def base_xp(level: int) -> int:
    """The original (fast) curve. Enemy XP rewards are derived from this."""
    return 100 + 30 * (level - 1) + (level - 1) ** 2 // 2


def slowdown(level: int) -> float:
    """1.0 up to level 25, then smoothly grows: ~3x at 100, ~23x at 500, ~55x at 1000."""
    if level <= SLOWDOWN_START:
        return 1.0
    return 1.0 + ((level - SLOWDOWN_START) / SLOWDOWN_SCALE) ** SLOWDOWN_POWER


def xp_to_next(level: int) -> int:
    """XP required to go from `level` to `level + 1` (0 at max level)."""
    if level >= MAX_LEVEL:
        return 0
    return round(base_xp(level) * slowdown(level))


def xp_level_modifier(player_level: int, enemy_level: int) -> float:
    """Diminishing XP for enemies far below you; a small bonus for tougher ones."""
    diff = player_level - enemy_level
    free = max(5, player_level // 10)
    if diff <= 0:
        return 1.0 + 0.02 * min(25, -diff)
    if diff <= free:
        return 1.0
    return max(0.05, 1.0 - (diff - free) / (player_level * 0.5 + 10))


@dataclass
class Progression:
    level: int = 1
    xp: int = 0
    stat_points: int = 0
    skill_points: int = 0
    allocated: dict = field(default_factory=lambda: {s: 0 for s in STAT_NAMES})

    @property
    def xp_needed(self) -> int:
        return xp_to_next(self.level)

    def _level_up(self):
        self.level += 1
        self.stat_points += STAT_POINTS_PER_LEVEL
        self.skill_points += SKILL_POINTS_PER_LEVEL

    def add_xp(self, amount: int) -> int:
        """Add XP; returns the number of levels gained (handles multi level-ups)."""
        if amount <= 0 or self.level >= MAX_LEVEL:
            return 0
        self.xp += amount
        gained = 0
        while self.level < MAX_LEVEL and self.xp >= xp_to_next(self.level):
            self.xp -= xp_to_next(self.level)
            self._level_up()
            gained += 1
        if self.level >= MAX_LEVEL:
            self.xp = 0
        return gained

    def add_levels(self, n: int) -> int:
        """Grant whole levels directly (dev tools / tests). Returns levels gained."""
        gained = 0
        while gained < n and self.level < MAX_LEVEL:
            self._level_up()
            gained += 1
        self.xp = 0
        return gained

    def spend_points(self, stat: str, amount) -> int:
        """Spend up to `amount` (an int, or "max") free points on a stat. Never overspends or
        exceeds STAT_LIMIT. Returns how many points were actually spent."""
        if stat not in self.allocated:
            return 0
        if amount == "max":
            amount = self.stat_points
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
            return 0
        n = min(amount, self.stat_points, STAT_LIMIT - self.allocated[stat])
        if n <= 0:
            return 0
        self.allocated[stat] += n
        self.stat_points -= n
        return n

    def spend_point(self, stat: str) -> bool:
        """Spend one free stat point on any stat. False if none left or bad stat."""
        return self.spend_points(stat, 1) == 1
