import pygame

from client import settings as S
from client.character import Character
from client.combat import Projectile
from client.dungeons import enemy_level, roster, spawn_plan
from client.enemy import ATTACKING, Enemy
from client.grades import grade_for_level
from client.player import Player

GROUND = [pygame.Rect(0, S.GROUND_Y, S.LEVEL_WIDTH, 100)]


def test_dungeon_to_enemy_level_mapping_spans_all_grades():
    assert enemy_level(1) == 1 and enemy_level(10) == 20
    assert grade_for_level(enemy_level(1)).short == "F"
    assert grade_for_level(enemy_level(50)).short == "A"
    assert grade_for_level(enemy_level(100)).short == "God"
    levels = [enemy_level(d) for d in range(1, S.MAX_DUNGEON + 1)]
    assert levels == sorted(levels)


def test_new_enemy_types_unlock_as_levels_rise():
    assert roster(1) == ["grunt", "runner", "brute"]
    assert "skeleton" in roster(25) and "slinger" in roster(25) and "wraith" not in roster(24)
    assert roster(2000)[-1] == "titan" and len(roster(2000)) == len(S.ENEMY_TYPES) >= 11


def test_enemies_get_stronger_by_tier():
    order = ["grunt", "skeleton", "wraith", "golem", "warlock", "demon", "dragon", "titan"]
    hps = [S.ENEMY_TYPES[k]["hp"] for k in order]
    dmgs = [S.ENEMY_TYPES[k]["damage"] for k in order]
    assert dmgs == sorted(dmgs) and hps[-1] > hps[0] * 50
    mins = [S.ENEMY_TYPES[k]["min_level"] for k in order]
    assert mins == sorted(mins)


def test_spawn_plan_is_deterministic_valid_and_ends_with_boss():
    a, b = spawn_plan(40), spawn_plan(40)
    assert a == b and len(a) == len(S.SPAWN_XS)
    assert all(S.ENEMY_TYPES[k]["min_level"] <= enemy_level(40) for k, _ in a)
    assert spawn_plan(1)[-1][0] == "brute"
    assert spawn_plan(100)[-1][0] == "titan"
    assert {k for k, _ in spawn_plan(1)} <= {"grunt", "runner", "brute"}


def test_ranged_enemy_keeps_distance_and_fires_projectile():
    p = Player(Character())
    p.update(0.5, 0, set(), GROUND)
    e = Enemy("slinger", p.rect.centerx + 300, 25)
    e.update(0.5, p, GROUND)
    assert e.ranged
    atk = None
    for _ in range(30):
        atk = e.update(1 / 60, p, GROUND) or atk
    assert isinstance(atk, Projectile) and e.state == ATTACKING
    assert atk.owner is e and atk.damage == e.damage
    # too close: it backs away instead of meleeing
    q = Player(Character())
    q.update(0.5, 0, set(), GROUND)
    e2 = Enemy("slinger", q.rect.centerx + 60, 25)
    e2.update(0.5, q, GROUND)
    e2.cooldown = 99
    x0 = e2.rect.x
    for _ in range(20):
        e2.update(1 / 60, q, GROUND)
    assert e2.rect.x > x0


def test_enemy_projectile_can_hit_player_and_be_dodged():
    p = Player(Character())
    p.update(0.5, 0, set(), GROUND)
    e = Enemy("slinger", p.rect.centerx + 250, 1)
    e.update(0.5, p, GROUND)
    atk = e.update(1 / 60, p, GROUND)
    assert atk is not None
    hit = False
    for _ in range(120):
        atk.update(1 / 60)
        if atk.try_hit(p):
            hit = True
            break
    assert hit
    q = Player(Character())
    q.update(0.5, 0, set(), GROUND)
    q.invuln = 5.0                                         # e.g. mid-dodge
    assert q.take_damage(10, 1, 0) is False
