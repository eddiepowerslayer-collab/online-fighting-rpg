"""Headless tests of one solo endeavor (Run), skills, potions and enemy drops."""
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from client import settings as S
from client.character import Character
from client.classes import ARCHER, MAGE, TANK, WARRIOR
from client.enemy import Enemy
from client.items import Item
from client.run import Run

DT = 1 / 60


class Rng(random.Random):
    """random.Random whose .random() can be forced (for drop/crit tests)."""
    forced = None

    def random(self):
        return super().random() if self.forced is None else self.forced


def make_run(cls=WARRIOR, level=1, seed=1):
    run = Run(Character(cls), level, Rng(seed))
    run.enemies = []
    return run


def settle(run):
    run.step(0.5)


def fight(run, enemy, actions, frames=2000, until=None):
    run.enemies = [enemy]
    for _ in range(frames):
        run.step(DT, 0, actions)
        if until(run) or run.result:
            break


def test_warrior_kills_enemy_and_gains_xp():
    run = make_run()
    settle(run)
    fight(run, Enemy("grunt", run.player.rect.centerx + 70), {"light"},
          until=lambda r: r.character.progression.xp > 0)
    expected = round(run.enemies[0].xp * run.character.xp_multiplier)
    assert run.character.progression.xp == expected and run.kills == 1
    assert run.player.alive


def test_mage_kills_from_range_without_being_reached():
    run = make_run(MAGE)
    settle(run)
    fight(run, Enemy("grunt", run.player.rect.centerx + 300), {"light"},
          until=lambda r: r.kills == 1)
    assert run.kills == 1


def test_archer_power_shot_pierces_two_enemies():
    run = make_run(ARCHER)
    settle(run)
    px = run.player.rect.centerx
    run.enemies = [Enemy("runner", px + 150), Enemy("runner", px + 190)]
    for e in run.enemies:
        e.cooldown = 99
    for e in run.enemies:
        e.update(0.5, run.player, run.platforms)
    run.player.heavy_cd = 0
    run.step(DT, 0, {"heavy"})
    for _ in range(60):
        run.step(DT)
    hurt = [e for e in run.enemies if e.hp < e.max_hp]
    assert len(hurt) == 2


def test_enemy_damages_player_and_armor_reduces_it():
    dmg_taken = {}
    for cls in (WARRIOR, TANK):
        run = make_run(cls)
        settle(run)
        run.enemies = [Enemy("brute", run.player.rect.centerx + 70)]
        for _ in range(200):
            run.step(DT)
        dmg_taken[cls.name] = run.player.max_hp - run.player.hp
        assert dmg_taken[cls.name] > 0
    assert Character(TANK).damage_reduction > Character(WARRIOR).damage_reduction


def test_level_up_in_run_grants_free_points_and_heals():
    run = make_run()
    run.character.progression.add_xp(95)
    run.player.sync_after_level_up()
    settle(run)
    fight(run, Enemy("grunt", run.player.rect.centerx + 70), {"light"},
          until=lambda r: r.character.progression.level == 2)
    ch = run.character
    assert ch.progression.level == 2 and ch.progression.stat_points == 3
    assert run.player.hp == run.player.max_hp == ch.max_hp and run.levels_gained == 1


def test_defeat_ends_run_and_keeps_progress():
    run = make_run()
    run.character.gold = 7
    run.player.hp = 1
    run.enemies = [Enemy("brute", run.player.rect.centerx + 70)]
    for _ in range(600):
        run.step(DT)
        if run.result:
            break
    assert run.result == "defeat" and run.character.gold == 7
    assert run.character.dungeon_unlocked == 1


def test_reaching_gate_wins_and_unlocks_next_dungeon():
    run = make_run(level=1)
    p = run.player
    p.px, p.py = float(run.exit_rect.x), float(run.exit_rect.y)
    p.rect.topleft = (run.exit_rect.x, run.exit_rect.y)
    run.step(DT)
    assert run.result == "victory"
    assert run.character.dungeon_unlocked == 2 and run.character.gold == 50
    run.step(DT)  # finished runs do not keep simulating
    assert run.character.gold == 50


def test_drops_reach_inventory_and_gold():
    run = make_run()
    settle(run)
    run.rng.forced = 0.0  # force every drop roll to succeed
    e = Enemy("grunt", run.player.rect.centerx + 20)
    e.take_damage(10_000, 1, 0)
    run._reward(e)
    kinds = sorted(d.kind for d in run.pickups)
    assert "item" in kinds
    for d in run.pickups:
        d.rect.center = run.player.rect.center
    run.step(DT)
    assert len(run.character.inventory) == 1 and isinstance(run.character.inventory[0], Item)
    assert run.loot == run.character.inventory


def test_defeated_enemy_respawns_later():
    run = make_run()
    e = Enemy("grunt", 2000)
    run.enemies = [e]
    e.take_damage(10_000, 1, 0)
    run._reward(e)
    for _ in range(int((S.ENEMY_RESPAWN_TIME + 3) * 60)):
        run.step(DT)
    assert len(run.enemies) == 1 and run.enemies[0].alive


def learn(run, sid, ranks=1):
    run.character.progression.skill_points += ranks
    for _ in range(ranks):
        assert run.character.buy_skill(sid)
    run.player.sync_after_level_up()


def test_whirlwind_hits_enemies_on_both_sides_and_respects_cooldown():
    run = make_run()
    settle(run)
    learn(run, "war_whirlwind")
    px = run.player.rect.centerx
    left, right = Enemy("grunt", px - 90), Enemy("grunt", px + 90)
    run.enemies = [left, right]
    for e in run.enemies:
        e.cooldown = 99
        e.update(0.5, run.player, run.platforms)
    run.step(DT, 0, {"skill1"})
    for _ in range(30):
        run.step(DT)
    assert left.hp < left.max_hp and right.hp < right.max_hp
    assert run.player.cooldowns["war_whirlwind"] > 0
    run.player.lock = 0
    assert run.player._try_skill(1) is None            # still cooling down


def test_unlearned_skill_does_nothing():
    run = make_run()
    settle(run)
    run.step(DT, 0, {"skill1"})
    assert not run.attacks and not run.player.cooldowns


def test_battle_cry_buff_boosts_damage_then_expires():
    run = make_run()
    settle(run)
    run.character.progression.level = 8
    learn(run, "war_battle_cry")
    base = run.player._start_attack(run.character.class_def.light).damage
    run.player.light_cd = run.player.lock = 0
    run.step(DT, 0, {"skill2"})
    assert "Battle Cry" in run.player.buffs
    run.player.rng = type("R", (), {"random": lambda s: 0.999})()
    buffed = run.player._start_attack(run.character.class_def.light).damage
    assert buffed == round(base * 1.2)
    for _ in range(int(9 * 60)):
        run.step(DT)
    assert not run.player.buffs


def test_second_wind_heals_and_god_invulnerability_blocks_damage():
    run = make_run(TANK)
    settle(run)
    run.character.progression.level = 8
    learn(run, "tan_second_wind")
    run.player.hp = 10
    run.step(DT, 0, {"skill2"})
    assert run.player.hp > 10 + run.player.max_hp * 0.15

    run2 = make_run(WARRIOR)
    settle(run2)
    run2.character.add_levels(1999)                    # level 2000: Unbreakable granted
    run2.player.sync_after_level_up()
    assert run2.character.skill_rank("war_g_unbreakable") == 1
    run2.step(DT, 0, {"skill5"})
    hp = run2.player.hp
    run2.enemies = [Enemy("brute", run2.player.rect.centerx + 60, 5)]
    for _ in range(200):
        run2.step(DT)
    assert run2.player.hp == hp


def test_god_skill_message_when_crossing_level_1000():
    run = make_run()
    run.character.progression.level = 999
    run.player.sync_after_level_up()
    settle(run)
    e = Enemy("grunt", run.player.rect.centerx + 40, 1)
    e.xp = 10**11
    e.take_damage(10_000, 1, 0)
    run._reward(e)
    assert run.character.progression.level >= 1000 and run.character.skill_rank("war_g_cleave") == 1
    assert any("GOD SKILL" in m for m, _, _ in run.messages)


def test_potions_consume_stock_and_apply_effects():
    run = make_run()
    settle(run)
    ch, p = run.character, run.player
    ch.consumables.update({"Health Potion": 1, "Elixir of Power": 1, "Elixir of Swiftness": 1})
    p.hp = 20
    run.step(DT, 0, {"use:Health Potion"})
    assert p.hp > 20 and ch.consumables["Health Potion"] == 0
    p.hp = 20
    run.step(DT, 0, {"use:Health Potion"})
    assert p.hp == 20                                   # none left, nothing happens
    run.step(DT, 0, {"use:Elixir of Power", "use:Elixir of Swiftness"})
    assert p.buff_damage == 1.25 and p.buff_speed == 1.25
    assert ch.consumables["Elixir of Power"] == 0
    p.hp = p.max_hp
    ch.consumables["Health Potion"] = 1
    run.step(DT, 0, {"use:Health Potion"})
    assert ch.consumables["Health Potion"] == 1         # full HP: not wasted


def test_run_uses_enemy_level_for_dungeon_and_material_drops():
    run = Run(Character(WARRIOR), 30, Rng(3))
    assert run.enemy_level == 180 and all(e.level == 180 for e in run.enemies)
    run = make_run()
    settle(run)
    run.rng.forced = 0.0
    e = Enemy("grunt", run.player.rect.centerx + 20)
    e.take_damage(10_000, 1, 0)
    run._reward(e)
    for d in run.pickups:
        d.rect.center = run.player.rect.center
    run.step(DT)
    assert sum(run.character.materials.values()) > 0 and run.materials_gained


def test_ranged_enemy_hurts_player_in_a_run():
    run = make_run()
    settle(run)
    run.enemies = [Enemy("slinger", run.player.rect.centerx + 260, 25)]
    for _ in range(400):
        run.step(DT)
    assert run.player.hp < run.player.max_hp


