import random

import pytest

from client.character import Character
from client.classes import WARRIOR
from client.grades import grade_for_level
from client.professions import PROFESSION_UNLOCK_LEVEL, PROFESSIONS


def stocked(level=PROFESSION_UNLOCK_LEVEL):
    ch = Character(WARRIOR)
    ch.add_levels(level - 1)
    ch.gold = 500
    ch.materials = {m: 50 for m in ch.materials}
    return ch


def test_profession_unlocks_at_level_10_only():
    ch = Character(WARRIOR)
    ch.add_levels(8)                         # level 9
    assert not ch.can_choose_profession and ch.choose_profession("Smithing") is False
    ch.add_levels(1)                         # level 10
    assert ch.can_choose_profession
    assert ch.choose_profession("Smithing") and ch.profession == "Smithing"
    assert ch.choose_profession("Alchemy") is False      # can't change
    assert not ch.can_choose_profession


def test_at_least_four_professions_including_the_requested_ones():
    assert {"Alchemy", "Smithing", "Sewing"} <= set(PROFESSIONS) and len(PROFESSIONS) >= 4


def test_cannot_craft_without_profession_or_materials():
    ch = stocked()
    assert ch.craft("Forged Sword", random.Random(1))[0] is False
    ch.choose_profession("Smithing")
    ch.materials["Iron Ore"] = 1
    ok, msg, item = ch.craft("Forged Sword", random.Random(1))
    assert not ok and "Iron Ore" in msg and item is None
    assert ch.materials["Iron Ore"] == 1                 # nothing consumed on failure


def test_craft_equipment_consumes_materials_and_gold():
    ch = stocked()
    ch.choose_profession("Smithing")
    ok, msg, item = ch.craft("Forged Sword", random.Random(1))
    assert ok and item in ch.inventory
    assert ch.materials["Iron Ore"] == 46 and ch.gold == 490
    assert item.slot == "weapon" and item.bonus("strength") >= 2 and item.grade == "F"
    assert ch.equip(item) and ch.equipment["weapon"] == item


def test_craft_requires_gold_and_profession_level():
    ch = stocked()
    ch.choose_profession("Smithing")
    ch.gold = 0
    assert "gold" in ch.craft("Forged Sword", random.Random(1))[1]
    ch.gold = 500
    assert "level" in ch.craft("Gemmed Longsword", random.Random(1))[1]


def test_crafting_gives_profession_xp_and_levels():
    ch = stocked()
    ch.choose_profession("Smithing")
    ch.materials = {m: 500 for m in ch.materials}
    for _ in range(12):
        ch.craft("Forged Sword", random.Random(2))
    assert ch.profession_level > 1
    assert ch.can_craft(PROFESSIONS["Smithing"].recipe("Iron Plate"))  # level 2 recipe unlocked


def test_alchemy_potions_stack_in_consumables():
    ch = stocked()
    ch.choose_profession("Alchemy")
    ok, msg, item = ch.craft("Health Potion", random.Random(1))
    assert ok and item is None and ch.consumables["Health Potion"] == 1


def test_crafted_gear_scales_with_levels():
    low, high = stocked(10), stocked(10)
    high.add_levels(190)                                  # level 200
    for c in (low, high):
        c.choose_profession("Smithing")
    a = low.craft("Forged Sword", random.Random(5))[2]
    b = high.craft("Forged Sword", random.Random(5))[2]
    assert b.bonus("strength") > a.bonus("strength")
    assert b.grade == grade_for_level(200).short == "C"
