import pygame
import pytest

from client import settings as S
from client.character import Character
from client.classes import ARCHER, MAGE, TANK, WARRIOR
from client.combat import Attack, Fighter, Projectile
from client.enemy import ATTACKING, DEFEATED, HURT, IDLE, PURSUING, Enemy
from client.player import Player

GROUND = [pygame.Rect(0, S.GROUND_Y, S.LEVEL_WIDTH, 100)]


class NoCrit:
    def random(self):
        return 0.999


class AlwaysCrit:
    def random(self):
        return 0.0


def fighter(x=100, hp=100, invuln=0.5):
    return Fighter(x, 200, 30, 50, hp, hurt_invuln=invuln, hurt_stun=0.2)


def make_player(cls=WARRIOR, rng=None):
    p = Player(Character(cls), rng or NoCrit())
    p.update(0.5, 0, set(), GROUND)  # settle on ground
    return p


def test_attack_hits_each_target_only_once():
    a, b = fighter(100), fighter(140)
    atk = Attack(a, 10, 100, 60, 40, delay=0, duration=0.5)
    assert atk.try_hit(b) is True
    assert atk.try_hit(b) is False
    assert atk.try_hit(a) is False


def test_attack_misses_out_of_reach_and_during_windup():
    a, far, near = fighter(100), fighter(600), fighter(140)
    atk = Attack(a, 10, 100, 60, 40, delay=0.2, duration=0.2)
    assert atk.try_hit(near) is False
    atk.update(0.25)
    assert atk.active and atk.try_hit(far) is False and atk.try_hit(near) is True


def test_attack_expires_and_cancel():
    a = fighter()
    atk = Attack(a, 10, 100, 60, 40, delay=0, duration=0.1)
    atk.update(0.2)
    assert atk.finished
    atk2 = Attack(a, 10, 100, 60, 40, delay=0, duration=1)
    atk2.cancel()
    assert atk2.finished


def test_blast_hits_both_sides():
    owner, left, right = fighter(300), fighter(200), fighter(380)
    blast = Attack(owner, 10, 100, 260, 80, 0, 0.3, centered=True)
    assert blast.try_hit(left) and blast.try_hit(right)


def test_damage_knockback_and_immunity():
    f = fighter(hp=100)
    assert f.take_damage(30, 1, 300) is True
    assert f.hp == 70 and f.vx == 300 and f.invuln == 0.5
    assert f.take_damage(30, 1, 300) is False
    assert f.hp == 70
    f.tick_timers(0.6)
    assert f.take_damage(30, -1, 300) is True and f.vx == -300


def test_hp_never_negative_and_dead_ignore_hits():
    f = fighter(hp=10)
    f.take_damage(999, 1, 0)
    assert f.hp == 0 and not f.alive
    f.invuln = 0
    assert f.take_damage(5, 1, 0) is False


def test_hit_cancels_windup_but_not_fired_projectile():
    f = fighter()
    f.attack = Attack(f, 10, 0, 50, 40, delay=0.3, duration=0.2)
    f.take_damage(5, 1, 0)
    assert f.attack.finished
    g = fighter()
    g.attack = Projectile(g, 10, 0, (20, 10), 0.0, 500, 400)
    g.take_damage(5, 1, 0)
    assert not g.attack.finished  # already in flight


def test_gravity_and_ground_landing():
    f = fighter()
    for _ in range(120):
        f.apply_physics(1 / 60, GROUND)
    assert f.on_ground and f.rect.bottom == S.GROUND_Y


def test_one_way_platform():
    plat = pygame.Rect(0, 350, 400, 16)
    f = Fighter(100, 250, 30, 50, 10)
    for _ in range(60):
        f.apply_physics(1 / 60, GROUND + [plat])
    assert f.rect.bottom == 350
    g = Fighter(100, 380, 30, 50, 10)
    g.vy = -600
    for _ in range(10):
        g.apply_physics(1 / 60, GROUND + [plat])
    assert not g.on_ground and g.rect.bottom < 430


# ----- projectiles -----
def test_projectile_waits_then_flies_and_expires():
    o = fighter(100)
    pr = Projectile(o, 10, 100, (20, 10), delay=0.1, speed=600, max_range=300)
    assert not pr.active
    pr.update(0.05)
    assert not pr.active and not pr.fired
    pr.update(0.06)
    assert pr.fired and pr.active
    x0 = pr.rect.x
    pr.update(0.1)
    assert pr.rect.x == x0 + 60
    for _ in range(10):
        pr.update(0.1)
    assert pr.finished


def test_projectile_hits_once_and_dies_without_pierce():
    o, t = fighter(100), fighter(300)
    pr = Projectile(o, 10, 100, (20, 10), 0, 600, 600)
    t.rect.centery = pr.rect.centery
    hits = 0
    for _ in range(40):
        pr.update(1 / 60)
        if pr.try_hit(t):
            hits += 1
    assert hits == 1 and pr.finished


def test_projectile_pierces_n_extra_targets():
    o = fighter(100)
    ts = [fighter(250), fighter(330), fighter(410), fighter(490)]
    pr = Projectile(o, 10, 100, (20, 10), 0, 600, 900, pierce=2)
    for t in ts:
        t.rect.centery = pr.rect.centery
    hit = []
    for _ in range(60):
        pr.update(1 / 60)
        for t in ts:
            if pr.try_hit(t):
                hit.append(t)
    assert len(hit) == 3 and ts[3] not in hit


# ----- player / classes -----
def test_player_light_attack_cooldown_and_damage_scaling():
    p = make_player()
    expected = round(WARRIOR.light.damage * p.character.damage_multiplier("strength"))
    a1 = p.update(1 / 60, 0, {"light"}, GROUND)
    assert a1 is not None and a1.damage == expected and not a1.crit
    assert p.update(1 / 60, 0, {"light"}, GROUND) is None
    p.character.progression.level = 6
    p.light_cd = p.lock = 0
    a2 = p.update(1 / 60, 0, {"light"}, GROUND)
    assert a2.damage == round(WARRIOR.light.damage * p.character.damage_multiplier("strength"))
    assert a2.damage > a1.damage


def test_crit_multiplies_damage():
    normal = make_player(rng=NoCrit()).update(1 / 60, 0, {"light"}, GROUND)
    crit = make_player(rng=AlwaysCrit()).update(1 / 60, 0, {"light"}, GROUND)
    assert crit.crit and crit.damage > normal.damage


def test_mage_and_archer_fire_projectiles_and_mage_blasts():
    mage = make_player(MAGE)
    assert isinstance(mage.update(1 / 60, 0, {"light"}, GROUND), Projectile)
    mage.heavy_cd = mage.lock = 0
    blast = mage.update(1 / 60, 0, {"heavy"}, GROUND)
    assert blast.centered
    archer = make_player(ARCHER)
    shot = archer.update(1 / 60, 0, {"heavy"}, GROUND)
    assert isinstance(shot, Projectile) and shot.pierce == 2


def test_player_move_speed_uses_class_and_agility():
    fast, slow = make_player(), make_player(TANK)
    fast.update(1 / 60, 1, set(), GROUND)
    slow.update(1 / 60, 1, set(), GROUND)
    assert fast.vx > slow.vx > 0


def test_player_jump_and_dodge_iframes():
    p = make_player()
    p.update(1 / 60, 0, {"jump"}, GROUND)
    assert p.vy < 0 and not p.on_ground
    q = make_player()
    q.update(1 / 60, 1, {"dodge"}, GROUND)
    assert q.dodge_t > 0 and q.invuln > 0
    assert q.take_damage(10, 1, 100) is False


# ----- enemies -----
def _place(f, x):
    f.px = float(x)
    f.rect.x = round(x)


def _setup_enemy(kind="grunt", dist=200):
    p = make_player()
    e = Enemy(kind, p.rect.centerx + dist)
    e.update(0.5, p, GROUND)
    return p, e


def test_enemy_idle_then_pursues_then_attacks():
    p, e = _setup_enemy(dist=900)
    e.update(1 / 60, p, GROUND)
    assert e.state == IDLE
    _place(e, p.px + 300)
    e.update(1 / 60, p, GROUND)
    assert e.state == PURSUING
    x0 = e.rect.x
    for _ in range(30):
        e.update(1 / 60, p, GROUND)
    assert e.rect.x < x0
    _place(e, p.px + 40)
    e.cooldown = 0
    e.update(1 / 60, p, GROUND)
    for _ in range(3):
        e.update(1 / 60, p, GROUND)
    assert e.state == ATTACKING and e.attack is not None


def test_enemy_hurt_and_defeated_states():
    p, e = _setup_enemy()
    assert e.take_damage(5, 1, 100) and e.state == HURT
    e.invuln = 0
    e.take_damage(10_000, 1, 0)
    assert e.state == DEFEATED and not e.alive
    for _ in range(90):
        e.update(1 / 60, p, GROUND)
    assert e.removable


def test_enemy_types_differ():
    g, r, b = (S.ENEMY_TYPES[k] for k in ("grunt", "runner", "brute"))
    assert r["speed"] > 2 * g["speed"] and r["damage"] > g["damage"]
    assert b["hp"] > 2 * g["hp"] and b["damage"] > 2 * g["damage"] and b["windup"] > g["windup"]


def test_dungeon_level_scales_enemies():
    e1, e5 = Enemy("grunt", 500, 1), Enemy("grunt", 500, 5)
    assert e5.max_hp > e1.max_hp and e5.damage > e1.damage and e5.xp > e1.xp


def test_enemy_stats_and_xp_scale_with_enemy_level():
    from client.progression import base_xp
    e1, e100 = Enemy("grunt", 500, 1), Enemy("grunt", 500, 100)
    assert e100.max_hp > 20 * e1.max_hp and e100.damage > 5 * e1.damage
    assert e1.xp == round(base_xp(1) / S.KILLS_PER_LEVEL)
    assert e100.xp == round(base_xp(100) / S.KILLS_PER_LEVEL)
