"""Dungeon levels 1..MAX_DUNGEON map to enemy levels (so dungeon ~100 = level 2000),
and decide which enemies spawn."""
import random

from . import settings as S


def enemy_level(dungeon_level: int) -> int:
    return max(1, round(0.2 * dungeon_level * dungeon_level))


def enemy_scaling(level: int):
    """(HP multiplier, damage multiplier) for an enemy of the given level."""
    return 1.0 + 0.25 * (level - 1), 1.0 + 0.08 * (level - 1)


def roster(level: int):
    return [k for k, c in S.ENEMY_TYPES.items() if c["min_level"] <= level]


def spawn_plan(dungeon_level: int):
    """Deterministic list of (enemy kind, x). Newer/stronger types are weighted higher;
    the final slot is the strongest type available."""
    kinds = roster(enemy_level(dungeon_level))
    weights = [1 + S.ENEMY_TYPES[k]["tier"] for k in kinds]
    rng = random.Random(dungeon_level * 7919)
    plan = [(rng.choices(kinds, weights)[0], x) for x in S.SPAWN_XS[:-1]]
    boss = max(kinds, key=lambda k: (S.ENEMY_TYPES[k]["tier"], S.ENEMY_TYPES[k]["hp"]))
    plan.append((boss, S.SPAWN_XS[-1]))
    return plan
