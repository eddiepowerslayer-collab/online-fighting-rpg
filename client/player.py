import random

from . import settings as S
from .character import CRIT_MULT, Character
from .combat import Attack, Fighter, Projectile
from .skills import BASIC_IDS, BIND_KEYS, SKILLS_BY_ID


class Player(Fighter):
    """The in-run combat body of a Character. Permanent data lives on
    self.character; everything here is temporary combat state."""

    def __init__(self, character=None, rng=None, spawn=S.PLAYER_SPAWN):
        self.character = character or Character()
        self.rng = rng or random.Random()
        cfg = S.PLAYER
        super().__init__(spawn[0], spawn[1], cfg["width"], cfg["height"],
                         self.character.max_hp, cfg["hurt_invuln"], cfg["hurt_stun"])
        self.light_cd = self.heavy_cd = self.lock = 0.0
        self.dodge_t = self.dodge_cd = 0.0
        self.cooldowns = {}      # skill id -> seconds remaining
        self.energy = self.max_energy = 100.0   # resource spent by skills (basic attacks are free)
        self.buffs = {}          # name -> dict(time, damage, reduction, speed, invuln)
        self.messages = []       # short texts for the run log, drained by Run

    # ----- buffs -----
    def _buff_sum(self, key):
        return sum(b[key] for b in self.buffs.values())

    @property
    def buff_damage(self):
        return 1.0 + self._buff_sum("damage")

    @property
    def buff_speed(self):
        return 1.0 + self._buff_sum("speed")

    @property
    def damage_reduction(self):
        return min(0.9, self.character.damage_reduction + self._buff_sum("reduction"))

    def add_buff(self, name, time, damage=0.0, reduction=0.0, speed=0.0, invuln=False):
        self.buffs[name] = dict(time=time, damage=damage, reduction=reduction, speed=speed, invuln=invuln)

    def use_consumable(self, name):
        """Drink a potion from the character's stock. Returns a log message or None."""
        ch = self.character
        if not self.alive or ch.consumables.get(name, 0) <= 0:
            return None
        if name == "Health Potion":
            if self.hp >= self.max_hp:
                return None
            heal = round(self.max_hp * 0.40)
            self.hp = min(self.max_hp, self.hp + heal)
            msg = f"Health Potion: +{heal} HP"
        elif name == "Elixir of Power":
            self.add_buff("Elixir of Power", 60.0, damage=0.25)
            msg = "Elixir of Power: +25% damage for 60s"
        elif name == "Elixir of Swiftness":
            self.add_buff("Elixir of Swiftness", 60.0, speed=0.25)
            msg = "Elixir of Swiftness: +25% speed for 60s"
        else:
            return None
        ch.consumables[name] -= 1
        return msg

    @property
    def class_name(self):
        return self.character.class_def.name

    @property
    def progression(self):
        return self.character.progression

    def sync_after_level_up(self):
        self.max_hp = self.character.max_hp
        self.hp = self.max_hp

    def respawn(self, pos, facing=1, invuln=2.0):
        self.energy = self.max_energy
        """Used by the arena: full heal, reposition, brief spawn protection."""
        self.px, self.py = float(pos[0]), float(pos[1])
        self.rect.topleft = (int(self.px), int(self.py))
        self.vx = self.vy = 0.0
        self.hp, self.facing = self.max_hp, facing
        self.invuln, self.stun, self.lock, self.dodge_t = invuln, 0.0, 0.0, 0.0
        self.attack, self.cooldowns, self.buffs = None, {}, {}

    def _start_attack(self, prof):
        return self._build_attack(prof, self.character.attack_damage(prof))

    def _use_binding(self, key):
        """Activate whatever is bound to `key` (J, K or 1-6). Returns an Attack, or None."""
        ch = self.character
        sid = ch.bindings.get(key)
        if sid == "basic_light":
            if self.light_cd > 0:
                return None
            self.light_cd = ch.class_def.light.cooldown
            return self._start_attack(ch.class_def.light)
        if sid == "basic_heavy":
            if self.heavy_cd > 0:
                return None
            self.heavy_cd = ch.class_def.heavy.cooldown
            return self._start_attack(ch.class_def.heavy)
        return self._try_skill_id(sid) if sid else None

    def _try_skill(self, slot):
        return self._use_binding(str(slot))

    def _try_skill_id(self, sid):
        ch = self.character
        rank = ch.skill_rank(sid)
        if rank <= 0 or sid not in SKILLS_BY_ID or self.cooldowns.get(sid, 0) > 0:
            return None
        sk = SKILLS_BY_ID[sid]
        if self.energy < sk.energy_cost:
            self.messages.append(f"Not enough energy for {sk.name}")
            return None
        self.energy -= sk.energy_cost
        self.cooldowns[sid] = sk.cooldown_for(rank)
        self.messages.append(f"{sk.name}!")
        if sk.kind == "attack":
            return self._build_attack(sk.profile, ch.skill_damage(sk))
        if sk.kind == "heal":
            amt = round(self.max_hp * sk.heal_fraction(rank))
            self.hp = min(self.max_hp, self.hp + amt)
            self.messages.append(f"Restored {amt} HP")
        elif sk.kind == "buff":
            v = sk.effect_values(rank)
            self.add_buff(sk.name, sk.duration, v.get("damage", 0.0), v.get("reduction", 0.0),
                          v.get("speed", 0.0), bool(v.get("invuln")))
        return None

    def hotbar(self):
        """What each bound key does right now (used by the HUD and sent to arena clients)."""
        ch, out = self.character, []
        for key in BIND_KEYS:
            sid = ch.bindings.get(key)
            if sid in BASIC_IDS:
                prof = ch.class_def.light if sid == "basic_light" else ch.class_def.heavy
                cd = self.light_cd if sid == "basic_light" else self.heavy_cd
                out.append({"key": key.upper(), "name": prof.name, "cd": round(cd, 1), "max": prof.cooldown,
                            "cost": 0, "god": False})
            elif sid in SKILLS_BY_ID and ch.skill_rank(sid) > 0:
                sk = SKILLS_BY_ID[sid]
                out.append({"key": key.upper(), "name": sk.name, "cd": round(self.cooldowns.get(sid, 0.0), 1),
                            "max": sk.cooldown_for(ch.skill_rank(sid)), "cost": sk.energy_cost, "god": sk.god})
        return out

    def _build_attack(self, prof, dmg):
        crit = self.rng.random() < self.character.crit_chance
        if crit:
            dmg = round(dmg * CRIT_MULT)
        dmg = round(dmg * self.buff_damage)
        if prof.kind == "projectile":
            atk = Projectile(self, dmg, prof.knockback, (prof.reach, prof.height),
                             prof.delay, prof.speed, prof.range, prof.pierce)
        else:
            atk = Attack(self, dmg, prof.knockback, prof.reach, prof.height,
                         prof.delay, prof.duration, centered=(prof.kind == "blast"))
        atk.crit, atk.color = crit, prof.color
        self.attack = atk
        self.lock = prof.lock
        return atk

    def update(self, dt, axis, actions, platforms):
        """Advance one frame. Returns a new Attack if one was started."""
        cfg = S.PLAYER
        cd = self.character.class_def
        self.tick_timers(dt)
        self.light_cd = max(0.0, self.light_cd - dt)
        self.heavy_cd = max(0.0, self.heavy_cd - dt)
        self.lock = max(0.0, self.lock - dt)
        self.dodge_cd = max(0.0, self.dodge_cd - dt)
        for sid in list(self.cooldowns):
            self.cooldowns[sid] = max(0.0, self.cooldowns[sid] - dt)
        for name in list(self.buffs):
            self.buffs[name]["time"] -= dt
            if self.buffs[name]["time"] <= 0:
                del self.buffs[name]
        if any(b["invuln"] for b in self.buffs.values()):
            self.invuln = max(self.invuln, 0.05)
        for a in actions:
            if a.startswith("use:"):
                msg = self.use_consumable(a[4:])
                if msg:
                    self.messages.append(msg)
        self.energy = min(self.max_energy, self.energy + 12.0 * dt)
        bind_key = next(({"light": "j", "heavy": "k"}.get(a) or a[5:] for a in sorted(actions)
                         if a in ("light", "heavy") or a.startswith("skill")), None)
        new_attack = None
        if not self.alive:
            self.vx = 0.0
        elif self.dodge_t > 0:
            self.dodge_t -= dt
            self.vx, self.vy = self.facing * cfg["dodge_speed"], 0.0
        elif self.stun > 0:
            self.apply_friction(dt)
        else:
            locked = self.lock > 0
            self.vx = axis * self.character.move_speed * self.buff_speed * (0.25 if locked else 1.0)
            if axis and not locked:
                self.facing = axis
            if "jump" in actions and self.on_ground and not locked:
                self.vy = -cfg["jump_speed"]
            if "dodge" in actions and self.dodge_cd <= 0 and not locked:
                if axis:
                    self.facing = axis
                self.dodge_t = cfg["dodge_time"]
                self.dodge_cd = cfg["dodge_cooldown"]
                self.invuln = max(self.invuln, cfg["dodge_time"] + 0.05)
            elif bind_key and not locked:
                new_attack = self._use_binding(bind_key)
        self.apply_physics(dt, platforms)
        return new_attack
