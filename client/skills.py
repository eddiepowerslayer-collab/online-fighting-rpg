"""Class skills. Each class has 5 regular skills (2 passives, 3 actives on keys 1-3)
and 3 god skills (actives on keys 4-6) granted at levels 1000, 2000 and 3000."""
from dataclasses import dataclass

from .classes import AttackProfile

GOD_SKILL_EVERY = 1000
GOD_UPGRADE_COST = 3
MAX_RANK = 5


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    class_name: str
    kind: str                  # "passive" | "attack" | "heal" | "buff"
    desc: str
    unlock_level: int = 1
    max_rank: int = MAX_RANK
    god: bool = False
    cooldown: float = 0.0
    profile: AttackProfile = None   # attack skills
    bonus: tuple = ()               # passives: ((key, per_rank), ...)
    effect: tuple = ()              # buffs: ((key, base, per_rank), ...)
    duration: float = 0.0
    heal: float = 0.0               # heal skills: fraction of max HP at rank 1
    heal_step: float = 0.0
    cost: int = 0                   # energy cost (0 = default for the skill's kind)

    @property
    def energy_cost(self) -> int:
        return self.cost or (60 if self.god else {"attack": 20, "buff": 30, "heal": 35}.get(self.kind, 0))

    @property
    def upgrade_cost(self) -> int:
        return GOD_UPGRADE_COST if self.god else 1

    @property
    def active(self) -> bool:
        return self.kind != "passive"

    def damage_scale(self, rank: int) -> float:
        return 1.0 + 0.30 * (rank - 1)

    def cooldown_for(self, rank: int) -> float:
        return round(self.cooldown * (1.0 - 0.05 * (rank - 1)), 2)

    def effect_values(self, rank: int) -> dict:
        return {k: base + step * (rank - 1) for k, base, step in self.effect}

    def heal_fraction(self, rank: int) -> float:
        return min(1.0, self.heal + self.heal_step * (rank - 1))

    def bonus_per_rank(self, key: str) -> float:
        return dict(self.bonus).get(key, 0.0)


def _blast(name, dmg, reach, height, kb, scales, color, delay=0.2):
    return AttackProfile(name, "blast", dmg, kb, 0, delay, 0.25, reach, height, 0.3, scales, color=color)


def _proj(name, dmg, size, speed, rng, scales, color, pierce=0, kb=250, delay=0.2):
    return AttackProfile(name, "projectile", dmg, kb, 0, delay, 0.0, size[0], size[1], 0.3, scales,
                         speed=speed, range=rng, pierce=pierce, color=color)


def _melee(name, dmg, reach, height, kb, scales, color, delay=0.15):
    return AttackProfile(name, "melee", dmg, kb, 0, delay, 0.2, reach, height, 0.35, scales, color=color)


def _s(cls, sid, name, kind, desc, **kw):
    return Skill(f"{cls[:3].lower()}_{sid}", name, cls, kind, desc, **kw)


WARRIOR_SKILLS = (
    _s("Warrior", "iron_skin", "Iron Skin", "passive", "+2% damage reduction per rank.", bonus=(("reduction", 0.02),)),
    _s("Warrior", "whirlwind", "Whirlwind", "attack", "Spin and strike all around you.", cooldown=6,
       profile=_blast("Whirlwind", 24, 200, 90, 450, "strength", (200, 220, 255))),
    _s("Warrior", "battle_cry", "Battle Cry", "buff", "+20% damage (more per rank) for 8s.", unlock_level=8,
       cooldown=16, duration=8, effect=(("damage", 0.20, 0.05),)),
    _s("Warrior", "hardened", "Battle Hardened", "passive", "+5% max HP per rank.", unlock_level=12,
       bonus=(("max_hp", 0.05),)),
    _s("Warrior", "earthshatter", "Earthshatter", "attack", "Smash the ground in a huge area.", unlock_level=20,
       cooldown=14, profile=_blast("Earthshatter", 50, 320, 70, 700, "strength", (190, 150, 100), 0.3)),
    _s("Warrior", "g_cleave", "Titan's Cleave", "attack", "GOD: a colossal wave of steel.", god=True, cooldown=25,
       profile=_blast("Titan's Cleave", 400, 700, 120, 1000, "strength", (255, 240, 160), 0.3)),
    _s("Warrior", "g_unbreakable", "Unbreakable", "buff", "GOD: invulnerable for 6s.", god=True, cooldown=60,
       duration=6, effect=(("invuln", 1, 0),)),
    _s("Warrior", "g_wrath", "Warlord's Wrath", "buff", "GOD: +100% damage for 12s.", god=True, cooldown=90,
       duration=12, effect=(("damage", 1.0, 0.2),)),
)

ASSASSIN_SKILLS = (
    _s("Assassin", "shadow_step", "Shadow Step", "passive", "+3% move speed per rank.", bonus=(("speed", 0.03),)),
    _s("Assassin", "flurry", "Blade Flurry", "attack", "A whirl of blades around you.", cooldown=5,
       profile=_blast("Blade Flurry", 18, 130, 60, 250, "agility", (230, 200, 255), 0.1)),
    _s("Assassin", "lethal", "Lethal Precision", "passive", "+3% crit chance per rank.", unlock_level=6,
       bonus=(("crit", 0.03),)),
    _s("Assassin", "vanish", "Vanish", "buff", "Untouchable and +30% speed for 2.5s.", unlock_level=10,
       cooldown=14, duration=2.5, effect=(("invuln", 1, 0), ("speed", 0.30, 0.05))),
    _s("Assassin", "deathmark", "Deathmark", "attack", "A long, devastating lunge.", unlock_level=20,
       cooldown=12, profile=_melee("Deathmark", 60, 140, 40, 500, "agility", (255, 80, 120), 0.12)),
    _s("Assassin", "g_cuts", "Thousand Cuts", "attack", "GOD: slash everything nearby.", god=True, cooldown=25,
       profile=_blast("Thousand Cuts", 350, 500, 100, 600, "agility", (255, 255, 255), 0.2)),
    _s("Assassin", "g_phantom", "Phantom", "buff", "GOD: untouchable and fast for 8s.", god=True, cooldown=60,
       duration=8, effect=(("invuln", 1, 0), ("speed", 0.5, 0.1))),
    _s("Assassin", "g_mark", "Reaper's Mark", "buff", "GOD: +100% damage for 12s.", god=True, cooldown=90,
       duration=12, effect=(("damage", 1.0, 0.2),)),
)

MAGE_SKILLS = (
    _s("Mage", "arcane_mind", "Arcane Mind", "passive", "+3% damage per rank.", bonus=(("damage", 0.03),)),
    _s("Mage", "fireball", "Fireball", "attack", "A heavy fireball that pierces one extra foe.", cooldown=5,
       profile=_proj("Fireball", 35, (30, 24), 480, 650, "intellect", (255, 120, 30), pierce=1, kb=300, delay=0.25)),
    _s("Mage", "mana_shield", "Mana Shield", "buff", "+30% damage reduction for 8s.", unlock_level=8,
       cooldown=18, duration=8, effect=(("reduction", 0.30, 0.05),)),
    _s("Mage", "scholar", "Scholar", "passive", "+5% XP gained per rank.", unlock_level=12, bonus=(("xp", 0.05),)),
    _s("Mage", "meteor", "Meteor", "attack", "Call down a meteor blast.", unlock_level=20, cooldown=14,
       profile=_blast("Meteor", 70, 360, 120, 700, "intellect", (255, 90, 30), 0.4)),
    _s("Mage", "g_cataclysm", "Cataclysm", "attack", "GOD: tear the sky apart.", god=True, cooldown=25,
       profile=_blast("Cataclysm", 500, 800, 160, 1000, "intellect", (255, 200, 120), 0.4)),
    _s("Mage", "g_timestop", "Time Stop", "buff", "GOD: invulnerable for 5s.", god=True, cooldown=60,
       duration=5, effect=(("invuln", 1, 0),)),
    _s("Mage", "g_ascend", "Archmage's Ascension", "buff", "GOD: +100% damage for 12s.", god=True, cooldown=90,
       duration=12, effect=(("damage", 1.0, 0.2),)),
)

TANK_SKILLS = (
    _s("Tank", "fortress", "Fortress", "passive", "+3% damage reduction per rank.", bonus=(("reduction", 0.03),)),
    _s("Tank", "shockwave", "Shockwave", "attack", "Knock back everything near you.", cooldown=6,
       profile=_blast("Shockwave", 18, 220, 80, 900, "strength", (180, 190, 210), 0.15)),
    _s("Tank", "second_wind", "Second Wind", "heal", "Restore 20% max HP (more per rank).", unlock_level=8,
       cooldown=20, heal=0.20, heal_step=0.05),
    _s("Tank", "vitality", "Ironclad Body", "passive", "+6% max HP per rank.", unlock_level=12,
       bonus=(("max_hp", 0.06),)),
    _s("Tank", "bulwark", "Bulwark", "buff", "+35% damage reduction for 8s.", unlock_level=20, cooldown=18,
       duration=8, effect=(("reduction", 0.35, 0.05),)),
    _s("Tank", "g_slam", "Colossus Slam", "attack", "GOD: a mountain-shaking slam.", god=True, cooldown=25,
       profile=_blast("Colossus Slam", 380, 650, 120, 1200, "strength", (200, 200, 220), 0.3)),
    _s("Tank", "g_aegis", "Aegis Eternal", "buff", "GOD: invulnerable for 8s.", god=True, cooldown=60,
       duration=8, effect=(("invuln", 1, 0),)),
    _s("Tank", "g_laststand", "Last Stand", "heal", "GOD: restore 60% max HP (more per rank).", god=True,
       cooldown=90, heal=0.60, heal_step=0.10),
)

ARCHER_SKILLS = (
    _s("Archer", "eagle_eye", "Eagle Eye", "passive", "+3% crit chance per rank.", bonus=(("crit", 0.03),)),
    _s("Archer", "volley", "Piercing Volley", "attack", "An arrow that pierces three foes.", cooldown=4,
       profile=_proj("Piercing Volley", 20, (30, 10), 800, 700, "dexterity", (240, 240, 170), pierce=3, kb=200, delay=0.1)),
    _s("Archer", "focus", "Hunter's Focus", "buff", "+25% damage (more per rank) for 8s.", unlock_level=8,
       cooldown=16, duration=8, effect=(("damage", 0.25, 0.05),)),
    _s("Archer", "fleet", "Fleet Foot", "passive", "+3% move speed per rank.", unlock_level=12,
       bonus=(("speed", 0.03),)),
    _s("Archer", "explosive", "Explosive Arrow", "attack", "A huge piercing arrow.", unlock_level=20, cooldown=12,
       profile=_proj("Explosive Arrow", 60, (44, 18), 750, 800, "dexterity", (255, 140, 60), pierce=2, kb=500, delay=0.3)),
    _s("Archer", "g_rain", "Rain of Arrows", "attack", "GOD: arrows blot out the sky.", god=True, cooldown=25,
       profile=_blast("Rain of Arrows", 350, 900, 140, 700, "dexterity", (255, 255, 200), 0.3)),
    _s("Archer", "g_wind", "Wind Walker", "buff", "GOD: untouchable and fast for 6s.", god=True, cooldown=60,
       duration=6, effect=(("invuln", 1, 0), ("speed", 0.5, 0.1))),
    _s("Archer", "g_hunt", "Divine Hunt", "buff", "GOD: +100% damage for 12s.", god=True, cooldown=90,
       duration=12, effect=(("damage", 1.0, 0.2),)),
)

SKILLS = {"Warrior": WARRIOR_SKILLS, "Assassin": ASSASSIN_SKILLS, "Mage": MAGE_SKILLS,
          "Tank": TANK_SKILLS, "Archer": ARCHER_SKILLS}
SKILLS_BY_ID = {s.id: s for group in SKILLS.values() for s in group}
# Hotkey order: regular actives (keys 1-3) then god skills (keys 4-6).
ACTIVE_ORDER = {c: [s.id for s in g if s.active and not s.god] + [s.id for s in g if s.god]
                for c, g in SKILLS.items()}


# ---- key bindings (J, K and number keys are all rebindable; more keys can be added here) ----
BIND_KEYS = ("j", "k", "1", "2", "3", "4", "5", "6")
BASIC_IDS = ("basic_light", "basic_heavy")


def default_bindings(class_name: str) -> dict:
    b = {"j": "basic_light", "k": "basic_heavy", "1": None, "2": None, "3": None, "4": None, "5": None, "6": None}
    for i, sid in enumerate(ACTIVE_ORDER[class_name]):
        b[str(i + 1)] = sid
    return b
