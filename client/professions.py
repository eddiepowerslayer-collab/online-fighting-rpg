"""Professions (unlocked at character level 10) and their crafting recipes."""
from dataclasses import dataclass

PROFESSION_UNLOCK_LEVEL = 10
MAX_PROFESSION_LEVEL = 20
MATERIALS = ("Iron Ore", "Herb", "Hide", "Cloth", "Gem")
MATERIAL_WEIGHTS = (3, 3, 3, 3, 1)
MATERIAL_COLORS = {"Iron Ore": (170, 170, 185), "Herb": (110, 200, 110), "Hide": (190, 140, 90),
                   "Cloth": (220, 200, 230), "Gem": (120, 220, 255)}


def profession_xp_needed(level: int) -> int:
    return 40 * level


@dataclass(frozen=True)
class Recipe:
    name: str
    kind: str                 # "equip" | "potion"
    materials: tuple          # (("Iron Ore", 3), ...)
    gold: int = 0
    min_level: int = 1        # profession level required
    xp: int = 10
    slot: str = ""            # equip only
    bonuses: tuple = ()       # equip only: ((stat, base), ...)
    desc: str = ""


@dataclass(frozen=True)
class Profession:
    name: str
    description: str
    recipes: tuple

    def recipe(self, name):
        return next((r for r in self.recipes if r.name == name), None)


ALCHEMY = Profession("Alchemy", "Brew potions and elixirs you can drink during endeavors.", (
    Recipe("Health Potion", "potion", (("Herb", 2),), 5, 1, 8, desc="Press Q in a run: heal 40% max HP."),
    Recipe("Elixir of Swiftness", "potion", (("Herb", 2), ("Hide", 1)), 10, 2, 12, desc="Press R: +25% speed for 60s."),
    Recipe("Elixir of Power", "potion", (("Herb", 3), ("Gem", 1)), 20, 4, 18, desc="Press E: +25% damage for 60s."),
    Recipe("Philosopher's Charm", "equip", (("Herb", 4), ("Gem", 3)), 40, 6, 25, "trinket",
           (("vitality", 1), ("intellect", 1))),
))
SMITHING = Profession("Smithing", "Forge weapons and armor from ore.", (
    Recipe("Forged Sword", "equip", (("Iron Ore", 4),), 10, 1, 10, "weapon", (("strength", 2),)),
    Recipe("Forged Dagger", "equip", (("Iron Ore", 3), ("Hide", 1)), 10, 1, 10, "weapon", (("agility", 2),)),
    Recipe("Iron Plate", "equip", (("Iron Ore", 6),), 20, 2, 14, "armor", (("vitality", 1), ("strength", 1))),
    Recipe("Forged Hammer", "equip", (("Iron Ore", 5), ("Gem", 1)), 25, 4, 18, "weapon",
           (("strength", 1), ("vitality", 1))),
    Recipe("Gemmed Longsword", "equip", (("Iron Ore", 6), ("Gem", 2)), 50, 7, 28, "weapon",
           (("strength", 2), ("dexterity", 1))),
))
SEWING = Profession("Sewing", "Stitch armor and charms from cloth and hide.", (
    Recipe("Leather Armor", "equip", (("Hide", 4),), 10, 1, 10, "armor", (("vitality", 2),)),
    Recipe("Cloth Robe", "equip", (("Cloth", 4),), 10, 1, 10, "armor", (("intellect", 1), ("vitality", 1))),
    Recipe("Traveler's Cloak", "equip", (("Cloth", 3), ("Hide", 2)), 20, 3, 16, "armor",
           (("agility", 1), ("dexterity", 1))),
    Recipe("Lucky Stitched Charm", "equip", (("Cloth", 3), ("Gem", 1)), 25, 4, 18, "trinket",
           (("agility", 1), ("dexterity", 1))),
    Recipe("Archmage Vestments", "equip", (("Cloth", 6), ("Gem", 2)), 50, 7, 28, "armor",
           (("intellect", 2), ("vitality", 1))),
))
JEWELCRAFTING = Profession("Jewelcrafting", "Cut gems into powerful trinkets.", (
    Recipe("Ruby Ring", "equip", (("Gem", 2), ("Iron Ore", 1)), 15, 1, 10, "trinket",
           (("strength", 1), ("vitality", 1))),
    Recipe("Sapphire Pendant", "equip", (("Gem", 3),), 20, 1, 12, "trinket", (("intellect", 2),)),
    Recipe("Emerald Charm", "equip", (("Gem", 2), ("Herb", 1)), 15, 2, 12, "trinket",
           (("dexterity", 1), ("agility", 1))),
    Recipe("Topaz Amulet", "equip", (("Gem", 3), ("Iron Ore", 1)), 25, 4, 18, "trinket", (("vitality", 2),)),
    Recipe("Dragon Eye Pendant", "equip", (("Gem", 6),), 80, 8, 30, "trinket",
           (("strength", 2), ("dexterity", 2))),
))

PROFESSIONS = {p.name: p for p in (ALCHEMY, SMITHING, SEWING, JEWELCRAFTING)}
PROFESSION_ORDER = list(PROFESSIONS)
CONSUMABLES = ("Health Potion", "Elixir of Power", "Elixir of Swiftness")


def craft_rarity_weights(profession_level: int):
    return [max(40, 80 - 3 * profession_level), 15 + 2 * profession_level, 5 + profession_level]
