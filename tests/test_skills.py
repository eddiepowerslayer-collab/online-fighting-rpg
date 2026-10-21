import pytest

from client.character import Character
from client.classes import ARCHER, ASSASSIN, CLASS_ORDER, MAGE, TANK, WARRIOR
from client.skills import ACTIVE_ORDER, GOD_UPGRADE_COST, SKILLS, SKILLS_BY_ID


def test_each_class_has_five_regular_and_three_god_skills():
    for c in CLASS_ORDER:
        group = SKILLS[c.name]
        assert len([s for s in group if not s.god]) == 5 and len([s for s in group if s.god]) == 3
        assert len(ACTIVE_ORDER[c.name]) == 6  # keys 1-3 regular actives, 4-6 god skills
        assert all(SKILLS_BY_ID[i].class_name == c.name for i in ACTIVE_ORDER[c.name])


def test_buy_new_skill_then_upgrade_uses_skill_points():
    ch = Character(WARRIOR)
    ch.progression.add_levels(3)           # 3 skill points
    assert ch.buy_skill("war_whirlwind") and ch.skill_rank("war_whirlwind") == 1
    assert ch.buy_skill("war_whirlwind") and ch.skill_rank("war_whirlwind") == 2
    assert ch.progression.skill_points == 1
    assert ch.buy_skill("war_iron_skin") and ch.progression.skill_points == 0
    assert ch.buy_skill("war_whirlwind") is False    # out of points


def test_cannot_buy_other_class_or_locked_or_maxed_skills():
    ch = Character(WARRIOR)
    ch.progression.skill_points = 50
    assert ch.buy_skill("mag_fireball") is False        # wrong class
    assert ch.buy_skill("war_battle_cry") is False      # unlock level 8
    ch.progression.level = 8
    assert ch.buy_skill("war_battle_cry")
    for _ in range(10):
        ch.buy_skill("war_whirlwind")
    assert ch.skill_rank("war_whirlwind") == 5          # capped at max rank
    assert ch.buy_skill("nonexistent") is False


def test_passive_skills_change_stats():
    ch = Character(WARRIOR)
    ch.progression.skill_points = 10
    hp0, dr0 = ch.max_hp, ch.damage_reduction
    ch.buy_skill("war_iron_skin")
    ch.progression.level = 12
    ch.buy_skill("war_hardened")
    assert ch.damage_reduction == pytest.approx(dr0 + 0.02 + 0.0)
    assert ch.max_hp > hp0
    a = Character(ASSASSIN)
    a.progression.skill_points = 5
    s0, c0 = a.move_speed, a.crit_chance
    a.buy_skill("ass_shadow_step")
    assert a.move_speed == pytest.approx(s0 * 1.03)
    mage = Character(MAGE)
    mage.progression.skill_points = 5
    d0 = mage.damage_multiplier("intellect")
    mage.buy_skill("mag_arcane_mind")
    assert mage.damage_multiplier("intellect") == pytest.approx(d0 * 1.03)


def test_active_skill_scales_with_rank():
    ch = Character(MAGE)
    ch.progression.skill_points = 5
    sk = SKILLS_BY_ID["mag_fireball"]
    ch.buy_skill(sk.id)
    d1 = ch.skill_damage(sk)
    ch.buy_skill(sk.id)
    assert ch.skill_damage(sk) > d1
    assert sk.cooldown_for(2) < sk.cooldown_for(1)


def test_god_skills_granted_every_1000_levels_and_never_bought():
    ch = Character(WARRIOR)
    ch.progression.skill_points = 100
    assert ch.buy_skill("war_g_cleave") is False        # can't buy a god skill
    ch.add_levels(998)
    assert ch.grant_god_skills() == [] and not any(SKILLS_BY_ID[k].god for k in ch.skills)
    ch.add_levels(1)                                    # level 1000
    assert ch.progression.level == 1000 and ch.skill_rank("war_g_cleave") == 1
    assert ch.skill_rank("war_g_unbreakable") == 0
    ch.add_levels(1000)                                 # level 2000
    assert ch.skill_rank("war_g_unbreakable") == 1 and ch.skill_rank("war_g_wrath") == 0
    ch.add_levels(1000)                                 # level 3000
    assert ch.skill_rank("war_g_wrath") == 1
    assert ch.grant_god_skills() == []                  # idempotent


def test_god_skill_upgrade_costs_three_points():
    ch = Character(TANK)
    ch.add_levels(999)
    ch.progression.skill_points = 5
    assert ch.skill_rank("tan_g_slam") == 1
    assert ch.buy_skill("tan_g_slam") and ch.progression.skill_points == 5 - GOD_UPGRADE_COST
    assert ch.buy_skill("tan_g_slam") is False          # only 2 left


def test_xp_path_grants_god_skill_via_add_xp():
    ch = Character(ARCHER)
    ch.progression.level = 999
    ch.add_xp(10**9)
    assert ch.progression.level >= 1000 and ch.skill_rank("arc_g_rain") == 1
