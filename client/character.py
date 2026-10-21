"""Permanent character data (class, progression, skills, gear, profession, dungeon
progress). Kept separate from temporary combat state (see player.py / run.py)."""
from . import settings as S
from .classes import CLASSES, HP_BASE, HP_PER_VIT, STAT_NAMES, WARRIOR
from .grades import grade_for_level
from .items import SLOTS, build_item, item_from_dict, item_to_dict, make_item
from .professions import (CONSUMABLES, MATERIALS, MAX_PROFESSION_LEVEL, PROFESSION_UNLOCK_LEVEL,
                          PROFESSIONS, craft_rarity_weights, profession_xp_needed)
from .progression import MAX_LEVEL, Progression, xp_to_next
from .skills import (ACTIVE_ORDER, BASIC_IDS, BIND_KEYS, GOD_SKILL_EVERY, SKILLS, SKILLS_BY_ID,
                     default_bindings)

CRIT_MULT = 1.75
SAVE_VERSION = 1


class CharacterDataError(ValueError):
    """Saved/received character data is malformed or inconsistent."""


def _int(v, lo, hi, what):
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise CharacterDataError(f"bad {what}")
    return v


class Character:
    def __init__(self, class_def=WARRIOR, name="Hero"):
        self.name = name
        self.id = None             # database id (set by the server)
        self.rev = 0               # save revision (optimistic concurrency)
        self.gear_cap = None       # arena normalisation: max gear bonus per stat
        self.class_def = class_def
        self.progression = Progression()
        self.gold = 0
        self.inventory = []
        self.equipment = {slot: None for slot in SLOTS}
        self.dungeon_unlocked = 1
        self.dungeon_selected = 1
        self.skills = {}                                   # skill id -> rank (no cap on how many)
        self.bindings = default_bindings(class_def.name)   # key -> skill id (J, K, 1-6)
        self.profession = None
        self.profession_level = 1
        self.profession_xp = 0
        self.materials = {m: 0 for m in MATERIALS}
        self.consumables = {c: 0 for c in CONSUMABLES}
        starter = make_item(class_def.starter_item)
        self.equipment[starter.slot] = starter

    # ----- grade -----
    @property
    def grade(self):
        return grade_for_level(self.progression.level)

    # ----- stats -----
    def gear_bonus(self, stat) -> int:
        total = sum(i.bonus(stat) for i in self.equipment.values() if i)
        return total if self.gear_cap is None else min(total, self.gear_cap)

    def stat_total(self, stat) -> int:
        return (self.class_def.base_stats[stat] + self.progression.allocated[stat]
                + self.gear_bonus(stat))

    def passive_bonus(self, key) -> float:
        total = 0.0
        for sid, rank in self.skills.items():
            sk = SKILLS_BY_ID[sid]
            if sk.kind == "passive":
                total += sk.bonus_per_rank(key) * rank
        return total

    @property
    def level_multiplier(self) -> float:
        return 1.0 + 0.06 * (self.progression.level - 1)

    @property
    def max_hp(self) -> int:
        base = (HP_BASE + HP_PER_VIT * self.stat_total("vitality")
                + self.class_def.hp_per_level * (self.progression.level - 1))
        return round(base * (1.0 + self.passive_bonus("max_hp")))

    def damage_multiplier(self, stat) -> float:
        """Level x stat scaling (baseline stat value is 5) x passive skill bonus."""
        return (self.level_multiplier * max(0.4, 1.0 + 0.04 * (self.stat_total(stat) - 5))
                * (1.0 + self.passive_bonus("damage")))

    def attack_damage(self, profile) -> int:
        return round(profile.damage * self.damage_multiplier(profile.scales))

    def skill_damage(self, skill) -> int:
        rank = max(1, self.skill_rank(skill.id))
        return round(skill.profile.damage * self.damage_multiplier(skill.profile.scales)
                     * skill.damage_scale(rank))

    @property
    def crit_chance(self) -> float:
        t = self.stat_total("agility") + self.stat_total("dexterity")
        return min(0.75, self.class_def.base_crit + 0.004 * t + 0.002 * self.stat_total("luck")
                   + self.passive_bonus("crit"))

    @property
    def move_speed(self) -> float:
        return (self.class_def.move_speed * (1.0 + 0.01 * self.stat_total("agility"))
                * (1.0 + self.passive_bonus("speed")))

    @property
    def damage_reduction(self) -> float:
        r = (self.class_def.base_reduction + 0.004 * self.stat_total("vitality")
             + 0.003 * self.stat_total("strength") + 0.004 * self.stat_total("defense")
             + self.passive_bonus("reduction"))
        return min(0.6, r)

    @property
    def drop_multiplier(self) -> float:
        return 1.0 + 0.005 * self.stat_total("luck")

    @property
    def xp_multiplier(self) -> float:
        return 1.0 + 0.01 * self.stat_total("intellect") + self.passive_bonus("xp")

    # ----- levelling -----
    def add_xp(self, amount) -> int:
        n = self.progression.add_xp(amount)
        self.grant_god_skills()
        return n

    def add_levels(self, n) -> int:
        got = self.progression.add_levels(n)
        self.grant_god_skills()
        return got

    def grant_god_skills(self):
        """A new god skill is granted at every 1000 levels. Idempotent. Returns new ones."""
        gods = [s for s in SKILLS[self.class_def.name] if s.god]
        new = []
        for i in range(min(len(gods), self.progression.level // GOD_SKILL_EVERY)):
            if gods[i].id not in self.skills:
                self.skills[gods[i].id] = 1
                new.append(gods[i])
        return new

    # ----- stat points -----
    def spend_point(self, stat) -> bool:
        return self.progression.spend_point(stat)

    def spend_points(self, stat, amount) -> int:
        return self.progression.spend_points(stat, amount)

    # ----- skills -----
    def skill_rank(self, skill_id) -> int:
        return self.skills.get(skill_id, 0)

    def skill_in_slot(self, slot):
        """Skill id bound to number key `slot` (kept for older callers)."""
        return self.bindings.get(str(slot))

    # ----- key bindings -----
    def can_bind(self, skill_id) -> bool:
        """An unlocked active skill (or one of the class's basic attacks)."""
        if skill_id in BASIC_IDS:
            return True
        sk = SKILLS_BY_ID.get(skill_id)
        return bool(sk and sk.class_name == self.class_def.name and sk.active and self.skill_rank(skill_id) > 0)

    def set_binding(self, key, skill_id) -> bool:
        """Bind (or with None, unequip) a key. Never touches the skills themselves.
        A skill sits on one key at a time: binding it elsewhere moves it."""
        if key not in BIND_KEYS or (skill_id is not None and not self.can_bind(skill_id)):
            return False
        if skill_id is not None:
            for k, v in self.bindings.items():
                if v == skill_id and k != key:
                    self.bindings[k] = None
        self.bindings[key] = skill_id
        return True

    def swap_bindings(self, a="j", b="k"):
        self.bindings[a], self.bindings[b] = self.bindings.get(b), self.bindings.get(a)

    def reset_bindings(self):
        self.bindings = default_bindings(self.class_def.name)

    def skill_label(self, skill_id):
        if skill_id == "basic_light":
            return self.class_def.light.name
        if skill_id == "basic_heavy":
            return self.class_def.heavy.name
        return SKILLS_BY_ID[skill_id].name

    def can_buy_skill(self, skill_id) -> bool:
        sk = SKILLS_BY_ID.get(skill_id)
        if sk is None or sk.class_name != self.class_def.name:
            return False
        rank = self.skill_rank(skill_id)
        if rank >= sk.max_rank or self.progression.level < sk.unlock_level:
            return False
        if sk.god and rank == 0:       # god skills can only be granted by level
            return False
        return self.progression.skill_points >= sk.upgrade_cost

    def buy_skill(self, skill_id) -> bool:
        """Learn a new skill (rank 1) or upgrade a known one with skill points."""
        if not self.can_buy_skill(skill_id):
            return False
        self.progression.skill_points -= SKILLS_BY_ID[skill_id].upgrade_cost
        self.skills[skill_id] = self.skill_rank(skill_id) + 1
        return True

    # ----- gear -----
    def equip(self, item) -> bool:
        if item not in self.inventory:
            return False
        self.inventory.remove(item)
        old = self.equipment[item.slot]
        if old:
            self.inventory.append(old)
        self.equipment[item.slot] = item
        return True

    def unequip(self, slot) -> bool:
        item = self.equipment.get(slot)
        if not item:
            return False
        self.equipment[slot] = None
        self.inventory.append(item)
        return True

    # ----- dungeons -----
    def complete_dungeon(self, level):
        self.dungeon_unlocked = min(S.MAX_DUNGEON, max(self.dungeon_unlocked, level + 1))

    def select_dungeon(self, level) -> bool:
        if 1 <= level <= self.dungeon_unlocked:
            self.dungeon_selected = level
            return True
        return False

    # ----- professions -----
    @property
    def can_choose_profession(self) -> bool:
        return self.profession is None and self.progression.level >= PROFESSION_UNLOCK_LEVEL

    def choose_profession(self, name) -> bool:
        if not self.can_choose_profession or name not in PROFESSIONS:
            return False
        self.profession = name
        return True

    def can_craft(self, recipe) -> bool:
        return (self.profession is not None and recipe in PROFESSIONS[self.profession].recipes
                and self.profession_level >= recipe.min_level and self.gold >= recipe.gold
                and all(self.materials.get(m, 0) >= n for m, n in recipe.materials))

    def craft(self, recipe_name, rng):
        """Craft a recipe. Returns (ok, message, item_or_None)."""
        if self.profession is None:
            return False, "Choose a profession first.", None
        recipe = PROFESSIONS[self.profession].recipe(recipe_name)
        if recipe is None:
            return False, "Unknown recipe.", None
        if self.profession_level < recipe.min_level:
            return False, f"Needs {self.profession} level {recipe.min_level}.", None
        if self.gold < recipe.gold:
            return False, f"Needs {recipe.gold} gold.", None
        missing = [f"{n - self.materials.get(m, 0)} {m}" for m, n in recipe.materials
                   if self.materials.get(m, 0) < n]
        if missing:
            return False, "Missing: " + ", ".join(missing), None
        self.gold -= recipe.gold
        for m, n in recipe.materials:
            self.materials[m] -= n
        item, msg = None, ""
        if recipe.kind == "potion":
            count = 1 + self.profession_level // 5
            self.consumables[recipe.name] = self.consumables.get(recipe.name, 0) + count
            msg = f"Brewed {count}x {recipe.name}."
        else:
            rarity = rng.choices(["Common", "Rare", "Epic"],
                                 weights=craft_rarity_weights(self.profession_level))[0]
            power = 1 + self.profession_level // 2 + self.progression.level // 20
            item = build_item(recipe.name, recipe.slot, recipe.bonuses, rarity, power, self.grade.short)
            self.inventory.append(item)
            msg = f"Crafted {rarity} {item.label}!  {item.describe()}"
        self._gain_profession_xp(recipe.xp)
        return True, msg, item

    def _gain_profession_xp(self, amount):
        if self.profession_level >= MAX_PROFESSION_LEVEL:
            return
        self.profession_xp += amount
        while (self.profession_level < MAX_PROFESSION_LEVEL
               and self.profession_xp >= profession_xp_needed(self.profession_level)):
            self.profession_xp -= profession_xp_needed(self.profession_level)
            self.profession_level += 1
        if self.profession_level >= MAX_PROFESSION_LEVEL:
            self.profession_xp = 0


    # ----- (de)serialisation -----
    def to_dict(self) -> dict:
        pr = self.progression
        return {
            "version": SAVE_VERSION, "name": self.name, "class": self.class_def.name,
            "level": pr.level, "xp": pr.xp, "stat_points": pr.stat_points,
            "skill_points": pr.skill_points, "allocated": dict(pr.allocated), "gold": self.gold,
            "inventory": [item_to_dict(i) for i in self.inventory],
            "equipment": {s: (item_to_dict(i) if i else None) for s, i in self.equipment.items()},
            "dungeon_unlocked": self.dungeon_unlocked, "dungeon_selected": self.dungeon_selected,
            "skills": dict(self.skills), "bindings": dict(self.bindings), "profession": self.profession,
            "profession_level": self.profession_level, "profession_xp": self.profession_xp,
            "materials": dict(self.materials), "consumables": dict(self.consumables),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        """Build a Character from untrusted data, validating everything."""
        try:
            if not isinstance(d, dict) or d.get("class") not in CLASSES:
                raise CharacterDataError("unknown class")
            ch = cls(CLASSES[d["class"]], str(d.get("name", "Hero"))[:16])
            pr = ch.progression
            pr.level = _int(d.get("level"), 1, MAX_LEVEL, "level")
            pr.xp = _int(d.get("xp"), 0, max(0, xp_to_next(pr.level)), "xp")
            pr.stat_points = _int(d.get("stat_points"), 0, 10**7, "stat points")
            pr.skill_points = _int(d.get("skill_points"), 0, 10**7, "skill points")
            alloc = d.get("allocated", {})
            if not isinstance(alloc, dict):
                raise CharacterDataError("bad allocation")
            pr.allocated = {s: _int(alloc.get(s, 0), 0, 10**7, "allocation") for s in STAT_NAMES}
            ch.gold = _int(d.get("gold"), 0, 10**12, "gold")
            ch.inventory = [item_from_dict(x) for x in d.get("inventory", [])]
            if len(ch.inventory) > 500:
                raise CharacterDataError("bag too large")
            ch.equipment = {s: None for s in SLOTS}
            for slot, x in (d.get("equipment") or {}).items():
                if slot in ch.equipment and x is not None:
                    item = item_from_dict(x)
                    if item.slot != slot:
                        raise CharacterDataError("item in wrong slot")
                    ch.equipment[slot] = item
            ch.dungeon_unlocked = _int(d.get("dungeon_unlocked", 1), 1, S.MAX_DUNGEON, "dungeon")
            ch.dungeon_selected = min(_int(d.get("dungeon_selected", 1), 1, S.MAX_DUNGEON, "dungeon"),
                                      ch.dungeon_unlocked)
            for sid, rank in (d.get("skills") or {}).items():
                sk = SKILLS_BY_ID.get(sid)
                if sk is None or sk.class_name != ch.class_def.name:
                    raise CharacterDataError("bad skill")
                ch.skills[sid] = _int(rank, 1, sk.max_rank, "skill rank")
            prof = d.get("profession")
            if prof is not None and prof not in PROFESSIONS:
                raise CharacterDataError("bad profession")
            ch.profession = prof
            ch.profession_level = _int(d.get("profession_level", 1), 1, MAX_PROFESSION_LEVEL, "profession level")
            ch.profession_xp = _int(d.get("profession_xp", 0), 0, 10**6, "profession xp")
            for m in MATERIALS:
                ch.materials[m] = _int((d.get("materials") or {}).get(m, 0), 0, 10**9, "material")
            for k in CONSUMABLES:
                ch.consumables[k] = _int((d.get("consumables") or {}).get(k, 0), 0, 10**9, "consumable")
            ch.grant_god_skills()
            raw = d.get("bindings")
            if raw is not None:
                if not isinstance(raw, dict):
                    raise CharacterDataError("bad bindings")
                for key in BIND_KEYS:
                    v = raw.get(key)
                    if v is not None and v not in BASIC_IDS and not (
                            v in SKILLS_BY_ID and SKILLS_BY_ID[v].class_name == ch.class_def.name and SKILLS_BY_ID[v].active):
                        raise CharacterDataError("bad binding")
                    ch.bindings[key] = v
            return ch
        except (ValueError, TypeError, AttributeError, KeyError) as e:
            if isinstance(e, CharacterDataError):
                raise
            raise CharacterDataError(f"malformed character data: {e}") from e

    def check_progress_consistency(self):
        """Stat/skill point budgets must match the level (catches tampered saves)."""
        pr = self.progression
        if pr.stat_points + sum(pr.allocated.values()) != 3 * (pr.level - 1):
            raise CharacterDataError("stat points do not match level")
        spent = 0
        for sid, rank in self.skills.items():
            sk = SKILLS_BY_ID[sid]
            spent += (rank - 1) * sk.upgrade_cost if sk.god else rank
        if pr.skill_points + spent != pr.level - 1:
            raise CharacterDataError("skill points do not match level")
