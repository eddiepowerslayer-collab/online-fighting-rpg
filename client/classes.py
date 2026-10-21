"""Class definitions: base stats and attack profiles. Pure data, no pygame."""
from dataclasses import dataclass

STAT_NAMES = ("strength", "vitality", "defense", "agility", "intellect", "dexterity", "luck")
STAT_LABELS = {"strength": "Strength", "vitality": "Vitality", "defense": "Defense", "agility": "Agility",
               "intellect": "Intellect", "dexterity": "Dexterity", "luck": "Luck"}
STAT_SHORT = {"strength": "STR", "vitality": "VIT", "defense": "DEF", "agility": "AGI",
              "intellect": "INT", "dexterity": "DEX", "luck": "LCK"}
HP_BASE = 40
HP_PER_VIT = 10


@dataclass(frozen=True)
class AttackProfile:
    name: str
    kind: str          # "melee" | "projectile" | "blast"
    damage: int
    knockback: int
    cooldown: float
    delay: float       # windup before the hitbox is live / projectile leaves
    duration: float    # how long a melee/blast hitbox stays live
    reach: int         # hitbox width (projectile: its length)
    height: int
    lock: float        # time the player can't act after starting the attack
    scales: str        # which stat boosts this attack's damage
    speed: int = 0     # projectile speed
    range: int = 0     # projectile max travel distance
    pierce: int = 0    # extra targets a projectile passes through
    color: tuple = (255, 255, 255)


@dataclass(frozen=True)
class ClassDef:
    name: str
    description: str
    color: tuple
    base_stats: dict
    hp_per_level: int
    move_speed: int
    base_crit: float
    base_reduction: float
    light: AttackProfile
    heavy: AttackProfile
    starter_item: str

    @property
    def primary_stat(self) -> str:
        return self.light.scales

    @property
    def base_hp(self) -> int:
        return HP_BASE + HP_PER_VIT * self.base_stats["vitality"]


WARRIOR = ClassDef(
    "Warrior", "Sturdy front-line fighter. Strong slashes and a crushing heavy cleave.",
    (70, 130, 220), dict(strength=10, vitality=8, agility=5, intellect=2, dexterity=4, defense=6, luck=3),
    hp_per_level=12, move_speed=260, base_crit=0.02, base_reduction=0.05,
    light=AttackProfile("Slash", "melee", 12, 240, 0.35, 0.05, 0.14, 52, 44, 0.25, "strength"),
    heavy=AttackProfile("Cleave", "melee", 32, 560, 1.1, 0.28, 0.18, 70, 54, 0.55, "strength"),
    starter_item="Training Sword")

ASSASSIN = ClassDef(
    "Assassin", "Fast and evasive. Rapid stabs, frequent critical hits and a long lunge.",
    (160, 90, 200), dict(strength=4, vitality=5, agility=10, intellect=2, dexterity=8, defense=3, luck=5),
    hp_per_level=9, move_speed=320, base_crit=0.08, base_reduction=0.0,
    light=AttackProfile("Stab", "melee", 8, 120, 0.20, 0.02, 0.10, 42, 40, 0.14, "agility"),
    heavy=AttackProfile("Lunge", "melee", 20, 300, 0.80, 0.12, 0.14, 84, 40, 0.30, "agility"),
    starter_item="Practice Dagger")

MAGE = ClassDef(
    "Mage", "Fragile caster. Ranged fire bolts and a burst of flame that hits all around.",
    (230, 120, 60), dict(strength=2, vitality=4, agility=5, intellect=10, dexterity=4, defense=2, luck=3),
    hp_per_level=8, move_speed=250, base_crit=0.03, base_reduction=0.0,
    light=AttackProfile("Firebolt", "projectile", 14, 150, 0.50, 0.10, 0.0, 18, 14, 0.20,
                        "intellect", speed=520, range=560, color=(255, 150, 50)),
    heavy=AttackProfile("Flame Burst", "blast", 30, 450, 1.60, 0.35, 0.20, 230, 90, 0.50,
                        "intellect", color=(255, 110, 40)),
    starter_item="Apprentice Staff")

TANK = ClassDef(
    "Tank", "Heavily armored. Huge health, damage reduction, slow attacks and a shield bash.",
    (110, 120, 140), dict(strength=8, vitality=12, agility=3, intellect=2, dexterity=3, defense=10, luck=2),
    hp_per_level=15, move_speed=220, base_crit=0.01, base_reduction=0.20,
    light=AttackProfile("Mace Swing", "melee", 10, 300, 0.50, 0.10, 0.16, 50, 56, 0.35, "strength"),
    heavy=AttackProfile("Shield Bash", "melee", 22, 800, 1.40, 0.30, 0.20, 64, 70, 0.60, "strength"),
    starter_item="Old Buckler")

ARCHER = ClassDef(
    "Archer", "Precise ranged fighter. Quick arrows and a piercing power shot.",
    (90, 170, 90), dict(strength=3, vitality=5, agility=7, intellect=2, dexterity=10, defense=3, luck=4),
    hp_per_level=9, move_speed=270, base_crit=0.05, base_reduction=0.0,
    light=AttackProfile("Arrow", "projectile", 10, 140, 0.40, 0.08, 0.0, 26, 8, 0.18,
                        "dexterity", speed=700, range=650, color=(230, 220, 160)),
    heavy=AttackProfile("Power Shot", "projectile", 26, 400, 1.20, 0.30, 0.0, 34, 10, 0.40,
                        "dexterity", speed=900, range=820, pierce=2, color=(255, 240, 120)),
    starter_item="Short Bow")

CLASS_ORDER = [WARRIOR, ASSASSIN, MAGE, TANK, ARCHER]
CLASSES = {c.name: c for c in CLASS_ORDER}
