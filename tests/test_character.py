import pytest

from client import settings as S
from client.character import Character
from client.classes import ARCHER, ASSASSIN, CLASS_ORDER, MAGE, TANK, WARRIOR
from client.items import make_item, roll_item


def test_base_hp_per_class():
    assert [c.base_hp for c in CLASS_ORDER] == [120, 90, 80, 160, 90]
    assert Character(WARRIOR).max_hp == 120  # starter sword gives no VIT


def test_every_class_has_a_starter_item_and_primary_stat():
    for c in CLASS_ORDER:
        ch = Character(c)
        assert any(ch.equipment.values())
        assert sum(ch.gear_bonus(st) for st in c.base_stats) == 1  # starter gear: +1 to one stat
        assert c.primary_stat in c.base_stats


def test_classes_are_mechanically_distinct():
    assert MAGE.light.kind == "projectile" and MAGE.heavy.kind == "blast"
    assert ARCHER.light.kind == "projectile" and ARCHER.heavy.pierce > 0
    assert WARRIOR.light.kind == "melee" and TANK.heavy.knockback > WARRIOR.heavy.knockback
    assert ASSASSIN.light.cooldown < WARRIOR.light.cooldown
    assert Character(TANK).damage_reduction > Character(MAGE).damage_reduction
    assert Character(ASSASSIN).move_speed > Character(TANK).move_speed


def test_level_up_then_spend_points_changes_stats():
    ch = Character(WARRIOR)
    hp0, str0 = ch.max_hp, ch.stat_total("strength")
    ch.progression.add_xp(100)
    assert ch.progression.stat_points == 3
    assert ch.spend_point("vitality") and ch.spend_point("vitality") and ch.spend_point("strength")
    assert ch.progression.stat_points == 0
    assert ch.stat_total("strength") == str0 + 1
    assert ch.max_hp == hp0 + 12 + 20  # level bonus (12) + 2 VIT (20)
    assert ch.spend_point("strength") is False


def test_points_in_primary_stat_raise_damage_but_wrong_stat_does_not():
    ch = Character(WARRIOR)
    base = ch.attack_damage(WARRIOR.light)
    ch.progression.stat_points = 5
    ch.spend_point("intellect")
    assert ch.attack_damage(WARRIOR.light) == base
    for _ in range(4):
        ch.spend_point("strength")
    assert ch.attack_damage(WARRIOR.light) > base


def test_level_scales_damage():
    ch = Character(WARRIOR)
    d1 = ch.damage_multiplier("strength")
    ch.progression.level = 6
    assert ch.damage_multiplier("strength") == pytest.approx(d1 * 1.3)


def test_secondary_effects():
    ch = Character(MAGE)
    xp0, crit0, spd0, dr0 = ch.xp_multiplier, ch.crit_chance, ch.move_speed, ch.damage_reduction
    ch.progression.allocated["intellect"] += 5
    ch.progression.allocated["agility"] += 5
    ch.progression.allocated["vitality"] += 5
    assert ch.xp_multiplier == pytest.approx(xp0 + 0.05)
    assert ch.crit_chance > crit0 and ch.move_speed > spd0 and ch.damage_reduction > dr0


def test_equip_swap_and_unequip():
    ch = Character(WARRIOR)
    sword, bow = make_item("Iron Sword", "Rare"), make_item("Hunting Bow")
    ch.inventory += [sword, bow]
    start = ch.equipment["weapon"]
    assert ch.equip(sword)
    assert ch.equipment["weapon"] == sword and start in ch.inventory and sword not in ch.inventory
    assert ch.gear_bonus("strength") == 4
    assert ch.equip(make_item("Chain Mail")) is False  # not in bag
    assert ch.unequip("weapon") and ch.equipment["weapon"] is None and sword in ch.inventory
    assert ch.unequip("weapon") is False


def test_equipping_vitality_gear_raises_max_hp():
    ch = Character(WARRIOR)
    vest = make_item("Leather Vest", "Epic")
    ch.inventory.append(vest)
    hp0 = ch.max_hp
    ch.equip(vest)
    assert ch.max_hp == hp0 + 60


def test_dungeon_unlock_and_selection():
    ch = Character()
    assert ch.select_dungeon(2) is False and ch.dungeon_selected == 1
    ch.complete_dungeon(1)
    assert ch.dungeon_unlocked == 2 and ch.select_dungeon(2)
    ch.complete_dungeon(1)  # replaying an old level never locks anything
    assert ch.dungeon_unlocked == 2
    for n in range(1, 150):
        ch.complete_dungeon(n)
    assert ch.dungeon_unlocked == S.MAX_DUNGEON == 100


def test_item_generation():
    import random
    assert make_item("Iron Sword", "Epic").bonus("strength") == 6
    a = [roll_item(random.Random(5), 3) for _ in range(5)]
    b = [roll_item(random.Random(5), 3) for _ in range(5)]
    assert a == b
    assert all(i.slot in ("weapon", "armor", "trinket") for i in a)




# ---------- unlimited skills, bindings (J and K), stat effects ----------
from client.skills import BIND_KEYS, SKILLS


def test_more_than_five_skills_can_be_unlocked_and_kept():
    ch = Character(WARRIOR)
    ch.add_levels(24)
    ch.progression.skill_points = 100
    for sk in [s for s in SKILLS["Warrior"] if not s.god]:
        assert ch.buy_skill(sk.id)
    assert len(ch.skills) == 5
    ch.add_levels(1000)                                # god skills arrive too
    ch.progression.skill_points = 100
    assert len(ch.skills) > 5
    restored = Character.from_dict(ch.to_dict())
    assert restored.skills == ch.skills and len(restored.skills) == len(ch.skills)


def test_default_bindings_match_previous_hotkeys():
    ch = Character(WARRIOR)
    assert ch.bindings["j"] == "basic_light" and ch.bindings["k"] == "basic_heavy"
    assert ch.bindings["1"] == "war_whirlwind" and ch.bindings["5"] == "war_g_unbreakable"
    assert set(ch.bindings) == set(BIND_KEYS)


def learned(cls=WARRIOR, levels=24):
    ch = Character(cls)
    ch.add_levels(levels)
    for sk in SKILLS[cls.name]:
        if sk.active and not sk.god and ch.progression.level >= sk.unlock_level:
            ch.progression.skill_points += 1
            ch.buy_skill(sk.id)
    return ch


def test_any_unlocked_skill_can_be_assigned_to_j_and_k_without_losing_skills():
    ch = learned()
    skills_before = dict(ch.skills)
    assert ch.set_binding("j", "war_earthshatter") and ch.set_binding("k", "war_whirlwind")
    assert ch.bindings["j"] == "war_earthshatter" and ch.bindings["k"] == "war_whirlwind"
    assert ch.bindings["1"] is None                      # a skill sits on one key: it moved off "1"
    assert ch.skills == skills_before                    # nothing was deleted


def test_swap_unequip_and_reset_never_delete_skills():
    ch = learned()
    ch.set_binding("j", "war_whirlwind")
    ch.swap_bindings("j", "k")
    assert ch.bindings["j"] == "basic_heavy" and ch.bindings["k"] == "war_whirlwind"
    assert ch.set_binding("k", None) and ch.bindings["k"] is None and ch.skill_rank("war_whirlwind") == 1
    ch.reset_bindings()
    assert ch.bindings["j"] == "basic_light" and ch.bindings["k"] == "basic_heavy" and ch.bindings["1"] == "war_whirlwind"


def test_cannot_bind_locked_foreign_or_passive_skills():
    ch = Character(WARRIOR)
    ch.progression.skill_points = 5
    assert ch.set_binding("j", "war_battle_cry") is False       # not unlocked
    assert ch.set_binding("j", "mag_fireball") is False         # another class
    ch.buy_skill("war_iron_skin")
    assert ch.set_binding("j", "war_iron_skin") is False        # passives can't be bound
    assert ch.set_binding("z", "basic_light") is False and ch.set_binding("j", "nonsense") is False
    assert ch.bindings["j"] == "basic_light"


def test_bindings_are_saved_per_character():
    a, b = learned(), Character(WARRIOR, "Other")
    a.set_binding("j", "war_whirlwind")
    ra, rb = Character.from_dict(a.to_dict()), Character.from_dict(b.to_dict())
    assert ra.bindings["j"] == "war_whirlwind" and rb.bindings["j"] == "basic_light"


def test_tampered_bindings_are_rejected_on_load():
    import pytest
    from client.character import CharacterDataError
    d = Character(WARRIOR).to_dict()
    d["bindings"]["j"] = "mag_fireball"
    with pytest.raises(CharacterDataError):
        Character.from_dict(d)


def test_stat_points_change_real_combat_numbers():
    ch = Character(WARRIOR)
    ch.progression.stat_points = 300
    base = (ch.attack_damage(WARRIOR.light), ch.max_hp, ch.damage_reduction, ch.crit_chance, ch.drop_multiplier)
    ch.spend_points("strength", 100)
    ch.spend_points("vitality", 100)
    ch.spend_points("luck", 100)
    now = (ch.attack_damage(WARRIOR.light), ch.max_hp, ch.damage_reduction, ch.crit_chance, ch.drop_multiplier)
    assert all(n > b for n, b in zip(now, base))
    ch2 = Character(WARRIOR)
    ch2.progression.stat_points = 100
    dr0 = ch2.damage_reduction
    ch2.spend_points("defense", 100)
    assert ch2.damage_reduction > dr0
