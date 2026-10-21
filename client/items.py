"""Equipment items. Pure data + deterministic generation from an rng."""
from dataclasses import dataclass

SLOTS = ("weapon", "armor", "trinket")
RARITY = {"Common": (1, (200, 200, 200)), "Rare": (2, (90, 160, 255)), "Epic": (3, (200, 110, 255))}

# name -> (slot, ((stat, base_bonus), ...)). Rarity multiplies the base bonus.
TEMPLATES = {
    "Iron Sword": ("weapon", (("strength", 2),)),
    "Hunting Bow": ("weapon", (("dexterity", 2),)),
    "Oak Staff": ("weapon", (("intellect", 2),)),
    "Twin Daggers": ("weapon", (("agility", 2),)),
    "War Hammer": ("weapon", (("strength", 1), ("vitality", 1))),
    "Leather Vest": ("armor", (("vitality", 2),)),
    "Chain Mail": ("armor", (("vitality", 1), ("strength", 1))),
    "Mage Robe": ("armor", (("intellect", 1), ("vitality", 1))),
    "Scout Cloak": ("armor", (("agility", 1), ("dexterity", 1))),
    "Lucky Charm": ("trinket", (("agility", 1), ("dexterity", 1))),
    "Power Ring": ("trinket", (("strength", 1), ("intellect", 1))),
    "Vital Amulet": ("trinket", (("vitality", 2),)),
    # class starter gear (never dropped)
    "Training Sword": ("weapon", (("strength", 1),)),
    "Practice Dagger": ("weapon", (("agility", 1),)),
    "Apprentice Staff": ("weapon", (("intellect", 1),)),
    "Old Buckler": ("armor", (("vitality", 1),)),
    "Short Bow": ("weapon", (("dexterity", 1),)),
}
STARTER_NAMES = {"Training Sword", "Practice Dagger", "Apprentice Staff", "Old Buckler", "Short Bow"}
DROP_NAMES = sorted(n for n in TEMPLATES if n not in STARTER_NAMES)
SHORT = {"strength": "STR", "vitality": "VIT", "defense": "DEF", "agility": "AGI", "intellect": "INT",
         "dexterity": "DEX", "luck": "LCK"}


@dataclass(frozen=True)
class Item:
    name: str
    slot: str
    rarity: str
    bonuses: tuple  # ((stat, value), ...)
    grade: str = "F"

    @property
    def label(self) -> str:
        return f"[{self.grade}] {self.name}"

    @property
    def color(self):
        return RARITY[self.rarity][1]

    def bonus(self, stat) -> int:
        return dict(self.bonuses).get(stat, 0)

    def describe(self) -> str:
        return " ".join(f"+{v} {SHORT[s]}" for s, v in self.bonuses)


def build_item(name, slot, base_bonuses, rarity="Common", power=1, grade="F") -> Item:
    mult = RARITY[rarity][0] * power
    return Item(name, slot, rarity, tuple((s, v * mult) for s, v in base_bonuses), grade)


def make_item(name: str, rarity: str = "Common", power: int = 1, grade: str = "F") -> Item:
    slot, base = TEMPLATES[name]
    return build_item(name, slot, base, rarity, power, grade)


def rarity_weights(dungeon_level: int):
    return [max(20, 80 - 6 * dungeon_level), 15 + 3 * dungeon_level, 2 + 2 * dungeon_level]


def roll_item(rng, dungeon_level: int, enemy_level: int = 1) -> Item:
    """Random gear drop. Bonuses scale with the enemy level that dropped it."""
    from .grades import grade_for_level
    rarity = rng.choices(list(RARITY), weights=rarity_weights(dungeon_level))[0]
    power = 1 + enemy_level // 10
    return make_item(rng.choice(DROP_NAMES), rarity, power, grade_for_level(enemy_level).short)


def item_to_dict(item: Item) -> dict:
    return {"name": item.name, "slot": item.slot, "rarity": item.rarity,
            "bonuses": [[s, v] for s, v in item.bonuses], "grade": item.grade}


def item_from_dict(d: dict) -> Item:
    """Validates untrusted data. Raises ValueError on anything malformed."""
    from .classes import STAT_NAMES
    if not isinstance(d, dict):
        raise ValueError("item must be an object")
    name, slot, rarity, grade = d.get("name"), d.get("slot"), d.get("rarity"), d.get("grade", "F")
    if not (isinstance(name, str) and 0 < len(name) <= 40 and isinstance(grade, str) and len(grade) <= 4):
        raise ValueError("bad item name/grade")
    if slot not in SLOTS or rarity not in RARITY:
        raise ValueError("bad item slot/rarity")
    bonuses = []
    for pair in d.get("bonuses", []):
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or pair[0] not in STAT_NAMES
                or not isinstance(pair[1], int) or isinstance(pair[1], bool) or not 0 < pair[1] <= 10**9):
            raise ValueError("bad item bonus")
        bonuses.append((pair[0], pair[1]))
    if len(bonuses) > 6:
        raise ValueError("too many bonuses")
    return Item(name, slot, rarity, tuple(bonuses), grade)
