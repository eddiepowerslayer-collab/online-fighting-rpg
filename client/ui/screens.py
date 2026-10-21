"""Menu scenes: class select, home, stats, equipment, dungeon level, results, run."""
import pygame

from .. import settings as S
from ..classes import STAT_LABELS, STAT_NAMES, STAT_SHORT
from ..dungeons import enemy_level, enemy_scaling, roster
from ..grades import grade_for_level
from ..items import SLOTS
from ..professions import (MATERIAL_COLORS, MATERIALS, MAX_PROFESSION_LEVEL, PROFESSION_ORDER,
                           PROFESSION_UNLOCK_LEVEL, PROFESSIONS, profession_xp_needed)
from ..progression import STAT_LIMIT
from ..skills import (ACTIVE_ORDER, BASIC_IDS, BIND_KEYS, GOD_SKILL_EVERY, SKILLS, SKILLS_BY_ID)
from . import hud
from .net_screens import MarketScreen
from .widgets import (BG, DIM, GOLD, GREEN, PANEL, TEXT, Button, Screen, bar, panel,
                      text, wrap)

JUMP_KEYS = {pygame.K_w, pygame.K_UP, pygame.K_SPACE}
LIGHT_KEYS = {pygame.K_j, pygame.K_z}
HEAVY_KEYS = {pygame.K_k, pygame.K_x}
DODGE_KEYS = {pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_l}
SKILL_KEYS = {pygame.K_1: "skill1", pygame.K_2: "skill2", pygame.K_3: "skill3",
              pygame.K_4: "skill4", pygame.K_5: "skill5", pygame.K_6: "skill6"}
POTION_KEYS = {pygame.K_q: "use:Health Potion", pygame.K_e: "use:Elixir of Power",
               pygame.K_r: "use:Elixir of Swiftness"}

STAT_EFFECTS = {
    "strength": "Boosts Strength attacks. +0.3% damage reduction per point.",
    "vitality": "+10 max HP and +0.4% damage reduction per point.",
    "defense": "+0.4% damage reduction per point.",
    "agility": "Boosts Agility attacks. +1% move speed, +0.4% crit chance per point.",
    "intellect": "Boosts Intellect attacks. +1% XP gained per point.",
    "dexterity": "Boosts Dexterity attacks. +0.4% crit chance per point.",
    "luck": "+0.2% crit chance and +0.5% drop chance per point.",
}


def back_button(screen_obj, label="Back"):
    return Button((30, 480, 140, 44), label, screen_obj.game.go_home)




class HomeScreen(Screen):
    def __init__(self, game):
        super().__init__(game)
        ch = game.character
        pr = ch.progression
        if ch.profession:
            prof_sub, prof_badge = f"{ch.profession} Lv {ch.profession_level}", ""
        elif ch.can_choose_profession:
            prof_sub, prof_badge = "Choose yours!", "!"
        else:
            prof_sub, prof_badge = f"Unlocks at level {PROFESSION_UNLOCK_LEVEL}", ""
        self.buttons = [
            Button((500, 92, 215, 66), "Stats", lambda: game.open(StatsScreen),
                   sub="Spend free points", badge=str(pr.stat_points) if pr.stat_points else ""),
            Button((725, 92, 205, 66), "Skills", lambda: game.open(SkillsScreen),
                   sub="Learn, upgrade, bind", badge=str(pr.skill_points) if pr.skill_points else ""),
            Button((500, 166, 215, 66), "Equipment", lambda: game.open(EquipmentScreen),
                   sub=f"{len(ch.inventory)} item(s) in bag"),
            Button((725, 166, 205, 66), "Profession", lambda: game.open(ProfessionScreen),
                   sub=prof_sub, badge=prof_badge, enabled=bool(ch.profession) or ch.can_choose_profession),
            Button((500, 240, 215, 66), "Marketplace", lambda: game.open(MarketScreen), sub="buy and sell"),
            Button((725, 240, 205, 66), "Arena", game.go_lobby, sub="PvP and co-op", color=(255, 150, 120)),
            Button((500, 314, 430, 66), "Go on Endeavor", game.start_run,
                   sub=f"Solo: Dungeon Level {ch.dungeon_selected}  (enemy level {enemy_level(ch.dungeon_selected)})",
                   color=GOLD),
            Button((500, 388, 430, 66), "Dungeon Level", lambda: game.open(DungeonScreen),
                   sub=f"Selected {ch.dungeon_selected}   |   Unlocked up to {ch.dungeon_unlocked}"),
            Button((780, 22, 150, 36), "Characters", game.switch_character),
        ]

    def handle_event(self, e):
        if S.DEV_MODE and e.type == pygame.KEYDOWN:
            amount = {pygame.K_F1: 1, pygame.K_F2: 10, pygame.K_F3: 100, pygame.K_F4: 1000}.get(e.key)
            if amount or e.key == pygame.K_F5:
                ch = self.game.character
                if amount:
                    ch.add_levels(amount)
                else:
                    ch.gold += 1000
                    for m in MATERIALS:
                        ch.materials[m] += 20
                self.game.autosave()       # dev shortcuts only work if the server accepts the save
                self.game.reload_character()
                self.game.go_home()
                return
        super().handle_event(e)

    def draw(self, screen):
        f, ch = self.game.fonts, self.game.character
        pr, cd = ch.progression, ch.class_def
        screen.fill(BG)
        text(screen, f["t"], "HOME", (30, 26))
        if self.game.host_info:
            text(screen, f["xs"], f"Hosting. Friends join with  {self.game.host_info}", (140, 40), GREEN)
        if S.DEV_MODE:
            text(screen, f["xs"], "DEV: F1/F2/F3/F4 = +1/+10/+100/+1000 levels   F5 = gold + materials", (140, 58), (255, 120, 120))
        panel(screen, pygame.Rect(30, 90, 450, 420))
        text(screen, f["t"], ch.name, (50, 100), cd.color)
        text(screen, f["s"], f"{cd.name}   Level {pr.level}", (50, 142))
        text(screen, f["s"], ch.grade.label, (300, 142), ch.grade.color)
        needed = pr.xp_needed
        bar(screen, pygame.Rect(50, 170, 410, 16), pr.xp / needed if needed else 1.0, (90, 170, 250))
        text(screen, f["xs"], f"XP {pr.xp:,}/{needed:,}" if needed else "XP MAX", (56, 171))
        text(screen, f["s"], f"Max HP {ch.max_hp:,}", (50, 194), (240, 120, 120))
        text(screen, f["s"], f"Gold {ch.gold:,}", (190, 194), GOLD)
        text(screen, f["s"], f"Stat pts {pr.stat_points}  Skill pts {pr.skill_points}", (290, 194),
             GREEN if (pr.stat_points or pr.skill_points) else DIM)
        y = 222
        for st in STAT_NAMES:
            star = "  (primary)" if st == cd.primary_stat else ""
            text(screen, f["s"], f"{STAT_LABELS[st]:<10} {ch.stat_total(st)}{star}", (50, y), GOLD if star else TEXT)
            y += 21
        y += 4
        text(screen, f["s"], "Equipped", (50, y), DIM)
        y += 20
        for slot in SLOTS:
            item = ch.equipment[slot]
            label = f"{slot.title()}: " + (f"{item.label}  {item.describe()}" if item else "(empty)")
            text(screen, f["xs"], label, (50, y), item.color if item else DIM)
            y += 17
        y += 6
        mats = "  ".join(f"{m.split()[0]} {ch.materials[m]}" for m in MATERIALS if ch.materials[m])
        text(screen, f["xs"], f"Skills known: {len(ch.skills)}   Materials: " + (mats or "none"), (50, y), DIM)
        self.draw_buttons(screen)

class StatsScreen(Screen):
    ROW_Y, ROW_H = 98, 52
    AMOUNTS = (("+1", 1), ("+10", 10), ("+100", 100), ("+MAX", "max"))

    def __init__(self, game):
        super().__init__(game)
        self.msg = ""
        self.rebuild()

    def spend(self, stat, amount):
        r = self.game.char_call("spend_stat", stat=stat, amount=amount)   # the server validates and saves
        self.msg = (f"+{r['result']} {STAT_LABELS[stat]}" if r.get("ok") else r.get("error", "Couldn't spend points."))
        self.rebuild()

    def rebuild(self):
        pr = self.game.character.progression
        self.buttons = [back_button(self)]
        for i, st in enumerate(STAT_NAMES):
            for j, (label, amt) in enumerate(self.AMOUNTS):
                b = Button((440 + j * 62, self.ROW_Y + i * self.ROW_H + 3, 58, 42), label,
                           lambda st=st, amt=amt: self.spend(st, amt),
                           enabled=pr.stat_points > 0 and pr.allocated[st] < STAT_LIMIT, color=GREEN)
                b.tag = (st, amt)
                self.buttons.append(b)

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.game.go_home()
        else:
            super().handle_event(e)

    def _preview(self):
        ch, pr = self.game.character, self.game.character.progression
        mouse = pygame.mouse.get_pos()
        for b in self.buttons:
            if hasattr(b, "tag") and b.rect.collidepoint(mouse):
                st, amt = b.tag
                n = min(pr.stat_points if amt == "max" else amt, pr.stat_points, STAT_LIMIT - pr.allocated[st])
                cur = ch.stat_total(st)
                return f"{STAT_LABELS[st]}: {cur} -> {cur + max(0, n)}   (spends {max(0, n)} of {pr.stat_points} points)"
        return self.msg or f"Each stat can hold up to {STAT_LIMIT} points. Hover a button to preview."

    def draw(self, screen):
        f, ch = self.game.fonts, self.game.character
        pr, cd = ch.progression, ch.class_def
        screen.fill(BG)
        text(screen, f["t"], "STATS", (30, 22))
        text(screen, f["m"], f"Free points: {pr.stat_points:,}", (200, 30), GREEN if pr.stat_points else DIM)
        text(screen, f["xs"], self._preview(), (30, 70), (200, 210, 230))
        for i, st in enumerate(STAT_NAMES):
            y = self.ROW_Y + i * self.ROW_H
            panel(screen, pygame.Rect(30, y, 400, 48))
            primary = st == cd.primary_stat
            text(screen, f["m"], f"{STAT_LABELS[st]}  {ch.stat_total(st)}", (44, y + 3), GOLD if primary else TEXT)
            if primary:
                text(screen, f["xs"], "primary", (260, y + 8), GOLD)
            text(screen, f["xs"], f"base {cd.base_stats[st]} + {pr.allocated[st]} pts + {ch.gear_bonus(st)} gear",
                 (44, y + 29), DIM)
        panel(screen, pygame.Rect(716, 96, 220, 366))
        text(screen, f["m"], "Derived", (732, 104))
        rows = [("Max HP", f"{ch.max_hp:,}"), (cd.light.name, f"{ch.attack_damage(cd.light):,} dmg"),
                (cd.heavy.name, f"{ch.attack_damage(cd.heavy):,} dmg"), ("Crit chance", f"{ch.crit_chance * 100:.1f}%"),
                ("Move speed", f"{ch.move_speed:.0f}"), ("Damage reduction", f"{ch.damage_reduction * 100:.1f}%"),
                ("XP bonus", f"+{(ch.xp_multiplier - 1) * 100:.0f}%"), ("Drop bonus", f"+{(ch.drop_multiplier - 1) * 100:.1f}%")]
        y = 136
        for k, v in rows:
            text(screen, f["xs"], k, (732, y), DIM)
            text(screen, f["s"], v, (732, y + 15), TEXT)
            y += 40
        self.draw_buttons(screen)

class EquipmentScreen(Screen):
    PER_PAGE = 7

    def __init__(self, game):
        super().__init__(game)
        self.offset = 0
        self.rebuild()

    def rebuild(self):
        ch = self.game.character
        self.offset = max(0, min(self.offset, max(0, len(ch.inventory) - self.PER_PAGE)))
        self.buttons = [back_button(self)]
        for i, slot in enumerate(SLOTS):
            item = ch.equipment[slot]
            self.buttons.append(Button(
                (30, 120 + i * 84, 410, 72), slot.title(), lambda s=slot: self._unequip(s),
                enabled=item is not None,
                sub=(f"{item.label}  {item.describe()}  (click to unequip)" if item else "empty"),
                sub_color=item.color if item else DIM))
        for i, item in enumerate(ch.inventory[self.offset:self.offset + self.PER_PAGE]):
            self.buttons.append(Button(
                (470, 120 + i * 50, 460, 44), f"{item.label}",
                lambda it=item: self._equip(it), sub="", color=item.color))
            self.buttons[-1].label = f"{item.label}   {item.describe()}"

    def _equip(self, item):
        idx = self.game.character.inventory.index(item)
        r = self.game.char_call("equip", item_index=idx)
        if not r.get("ok"):
            self.game.say(r.get("error", "Can't equip that."), (240, 110, 110))
        self.rebuild()

    def _unequip(self, slot):
        r = self.game.char_call("unequip", slot=slot)
        if not r.get("ok"):
            self.game.say(r.get("error", "Can't unequip that."), (240, 110, 110))
        self.rebuild()

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.game.go_home()
        elif e.type == pygame.MOUSEWHEEL:
            self.offset -= e.y
            self.rebuild()
        else:
            super().handle_event(e)

    def draw(self, screen):
        f, ch = self.game.fonts, self.game.character
        screen.fill(BG)
        text(screen, f["t"], "EQUIPMENT", (30, 26))
        text(screen, f["m"], "Equipped", (30, 84), DIM)
        text(screen, f["m"], f"Bag ({len(ch.inventory)})", (470, 84), DIM)
        if not ch.inventory:
            text(screen, f["s"], "Empty. Enemies drop gear on endeavors.", (470, 130), DIM)
        else:
            text(screen, f["xs"], "Click an item to equip it. Scroll for more.", (600, 90), DIM)
        bonus = " ".join(f"+{ch.gear_bonus(s)} {STAT_SHORT[s]}" for s in STAT_NAMES if ch.gear_bonus(s))
        text(screen, f["s"], "Gear bonuses: " + (bonus or "none"), (30, 390), GOLD)
        self.draw_buttons(screen)


class DungeonScreen(Screen):
    PER_PAGE = 10

    def __init__(self, game):
        super().__init__(game)
        self.pages = (S.MAX_DUNGEON + self.PER_PAGE - 1) // self.PER_PAGE
        self.page = (game.character.dungeon_selected - 1) // self.PER_PAGE
        self.rebuild()

    def pick(self, level):
        self.game.character.select_dungeon(level)
        self.game.autosave()
        self.rebuild()

    def turn(self, delta):
        self.page = max(0, min(self.pages - 1, self.page + delta))
        self.rebuild()

    def rebuild(self):
        ch = self.game.character
        self.buttons = [back_button(self)]
        self.buttons.append(Button((200, 480, 120, 44), "< Prev", lambda: self.turn(-1), enabled=self.page > 0))
        self.buttons.append(Button((330, 480, 120, 44), "Next >", lambda: self.turn(1),
                                   enabled=self.page < self.pages - 1))
        first = self.page * self.PER_PAGE + 1
        for i in range(self.PER_PAGE):
            n = first + i
            c, r = i % 5, i // 5
            ok = n <= ch.dungeon_unlocked
            g = grade_for_level(enemy_level(n))
            self.buttons.append(Button((45 + c * 180, 110 + r * 84, 160, 72), f"Level {n}",
                                       lambda n=n: self.pick(n), enabled=ok,
                                       sub=f"enemy Lv {enemy_level(n)}" if ok else "locked",
                                       sub_color=g.color, selected=n == ch.dungeon_selected))

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.game.go_home()
        else:
            super().handle_event(e)

    def draw(self, screen):
        f, ch = self.game.fonts, self.game.character
        screen.fill(BG)
        text(screen, f["t"], "DUNGEON LEVEL", (30, 26))
        text(screen, f["xs"], "Reach a level's gate to unlock the next. Enemy level grows with dungeon level.",
             (30, 84), DIM)
        text(screen, f["s"], f"Page {self.page + 1}/{self.pages}", (470, 492), DIM)
        n = ch.dungeon_selected
        R = enemy_level(n)
        g = grade_for_level(R)
        hp, dmg = enemy_scaling(R)
        panel(screen, pygame.Rect(45, 290, 880, 180))
        text(screen, f["m"], f"Selected: Dungeon Level {n}", (65, 304), GOLD)
        text(screen, f["m"], f"Enemy level {R}  ({g.label})", (480, 304), g.color)
        text(screen, f["s"], f"Enemy HP x{hp:.1f}    Enemy damage x{dmg:.1f}    XP per kill scales with enemy level",
             (65, 340))
        names = ", ".join(S.ENEMY_TYPES[k]["name"] for k in roster(R))
        for i, line in enumerate(wrap(f["s"], "Enemies: " + names, 830)[:3]):
            text(screen, f["s"], line, (65, 368 + i * 22), TEXT)
        text(screen, f["xs"], f"Highest unlocked: {ch.dungeon_unlocked} of {S.MAX_DUNGEON}.  "
             "Recommended: be near the enemy level.", (65, 444), DIM)
        self.draw_buttons(screen)


class SkillsScreen(Screen):
    ROW_H = 68

    def __init__(self, game):
        super().__init__(game)
        self.rebuild()

    def buy(self, sid):
        r = self.game.char_call("buy_skill", skill_id=sid)
        if not r.get("ok"):
            self.game.say(r.get("error", "Can't do that."), (240, 110, 110))
        self.rebuild()

    def _layout(self):
        cn = self.game.character.class_def.name
        normal = [s for s in SKILLS[cn] if not s.god]
        gods = [s for s in SKILLS[cn] if s.god]
        for col_x, group in ((30, normal), (490, gods)):
            for i, sk in enumerate(group):
                yield sk, pygame.Rect(col_x, 118 + i * self.ROW_H, 440 if col_x == 30 else 440, 62)

    def rebuild(self):
        ch = self.game.character
        self.skill_buttons = {}
        self.buttons = [back_button(self), Button((190, 484, 230, 44), "Key Bindings (J / K)",
                                                  lambda: self.game.open(BindingsScreen), color=GOLD)]
        for sk, rect in self._layout():
            rank = ch.skill_rank(sk.id)
            if sk.god and rank == 0:
                label, enabled = "Locked", False
            elif ch.progression.level < sk.unlock_level:
                label, enabled = f"Lv {sk.unlock_level}", False
            elif rank >= sk.max_rank:
                label, enabled = "Max", False
            else:
                label = f"{'Learn' if rank == 0 else 'Upgrade'} ({sk.upgrade_cost})"
                enabled = ch.can_buy_skill(sk.id)
            b = Button((rect.right - 118, rect.y + 10, 108, 42), label, lambda sid=sk.id: self.buy(sid),
                       enabled=enabled, color=GREEN if enabled else TEXT)
            self.skill_buttons[sk.id] = b
            self.buttons.append(b)

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.game.go_home()
        else:
            super().handle_event(e)

    def draw(self, screen):
        f, ch = self.game.fonts, self.game.character
        pr = ch.progression
        screen.fill(BG)
        text(screen, f["t"], "SKILLS", (30, 26))
        text(screen, f["m"], f"Skill points: {pr.skill_points}", (30, 80), GREEN if pr.skill_points else DIM)
        text(screen, f["xs"], "1 point = learn or upgrade (max rank 5)", (250, 86), DIM)
        text(screen, f["m"], "God Skills", (490, 80), (255, 225, 100))
        for sk, rect in self._layout():
            rank = ch.skill_rank(sk.id)
            panel(screen, rect, PANEL, (255, 225, 100) if sk.god and rank else (74, 80, 110))
            col = (255, 225, 100) if sk.god else TEXT
            text(screen, f["m"], sk.name, (rect.x + 12, rect.y + 5), col if rank else DIM)
            text(screen, f["xs"], f"Rank {rank}/{sk.max_rank}", (rect.x + 250, rect.y + 9), GOLD if rank else DIM)
            text(screen, f["xs"], sk.desc, (rect.x + 12, rect.y + 28), (170, 180, 200))
            if sk.kind == "passive":
                meta = "Passive"
            else:
                cd = sk.cooldown_for(max(1, rank))
                meta = f"Cooldown {cd:g}s   Energy {sk.energy_cost}"
            if sk.god:
                idx = [s.id for s in SKILLS[ch.class_def.name] if s.god].index(sk.id)
                meta += f"   (granted at level {GOD_SKILL_EVERY * (idx + 1)})"
            elif sk.unlock_level > 1:
                meta += f"   Unlocks at level {sk.unlock_level}"
            text(screen, f["xs"], meta, (rect.x + 12, rect.y + 44), DIM)
        text(screen, f["xs"], f"God skills are granted free at levels {GOD_SKILL_EVERY}, "
             f"{2 * GOD_SKILL_EVERY} and {3 * GOD_SKILL_EVERY}.", (490, 332), DIM)
        text(screen, f["xs"], "Upgrading a god skill costs 3 skill points per rank.", (490, 350), DIM)
        self.draw_buttons(screen)


class ProfessionScreen(Screen):
    def __init__(self, game):
        super().__init__(game)
        self.selected = None
        self.msg = ""
        self.msg_color = TEXT
        self.cards = [(pygame.Rect(30 + i * 225, 120, 210, 250), n) for i, n in enumerate(PROFESSION_ORDER)]
        self.rebuild()

    def rebuild(self):
        ch = self.game.character
        self.buttons = [back_button(self)]
        if ch.profession is None:
            label = f"Learn {self.selected}" if self.selected else "Pick a profession"
            self.buttons.append(Button((300, 400, 360, 54), label, self._learn,
                                       enabled=bool(self.selected) and ch.can_choose_profession, color=GOLD))
            return
        prof = PROFESSIONS[ch.profession]
        for i, rc in enumerate(prof.recipes):
            can = ch.can_craft(rc)
            cost = ", ".join(f"{n} {m}" for m, n in rc.materials) + (f", {rc.gold}g" if rc.gold else "")
            locked = ch.profession_level < rc.min_level
            sub = f"Needs {ch.profession} Lv {rc.min_level}" if locked else cost
            self.buttons.append(Button((30, 112 + i * 68, 520, 62), rc.name, lambda n=rc.name: self._craft(n),
                                       enabled=can, sub=sub, color=GREEN if can else TEXT))

    def _learn(self):
        r = self.game.char_call("choose_profession", name=self.selected)
        if r.get("ok"):
            self.msg, self.msg_color = f"You are now a {self.selected}!", GREEN
        else:
            self.msg, self.msg_color = r.get("error", ""), (240, 120, 120)
        self.rebuild()

    def _craft(self, name):
        ok, msg, _ = self.game.character.craft(name, self.game.rng)
        if ok:
            self.game.autosave()
        self.msg, self.msg_color = msg, GREEN if ok else (240, 120, 120)
        self.rebuild()

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.game.go_home()
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.game.character.profession is None:
            for rect, n in self.cards:
                if rect.collidepoint(e.pos):
                    self.selected = n
                    self.rebuild()
                    return
        super().handle_event(e)

    def draw(self, screen):
        f, ch = self.game.fonts, self.game.character
        screen.fill(BG)
        text(screen, f["t"], "PROFESSION", (30, 26))
        if ch.profession is None:
            text(screen, f["s"], "Choose one profession. You can't change it later.", (30, 84), DIM)
            mouse = pygame.mouse.get_pos()
            for rect, n in self.cards:
                p = PROFESSIONS[n]
                sel = n == self.selected
                panel(screen, rect, (52, 58, 84) if rect.collidepoint(mouse) else PANEL, GOLD if sel else (74, 80, 110))
                text(screen, f["m"], n, (rect.centerx, rect.y + 24), TEXT, True)
                y = rect.y + 56
                for line in wrap(f["xs"], p.description, rect.w - 24):
                    text(screen, f["xs"], line, (rect.x + 12, y), DIM)
                    y += 17
                y += 8
                for rc in p.recipes[:5]:
                    text(screen, f["xs"], "- " + rc.name, (rect.x + 12, y), TEXT)
                    y += 16
            if not ch.can_choose_profession:
                text(screen, f["s"], f"Reach level {PROFESSION_UNLOCK_LEVEL} to choose.", (300, 470), (240, 120, 120))
        else:
            prof = PROFESSIONS[ch.profession]
            text(screen, f["m"], f"{ch.profession}  Lv {ch.profession_level}", (30, 80), GOLD)
            need = profession_xp_needed(ch.profession_level)
            maxed = ch.profession_level >= MAX_PROFESSION_LEVEL
            bar(screen, pygame.Rect(260, 84, 200, 14), 1.0 if maxed else ch.profession_xp / need, (120, 200, 120))
            text(screen, f["xs"], "MAX" if maxed else f"{ch.profession_xp}/{need}", (468, 85), DIM)
            text(screen, f["xs"], prof.description, (560, 88), DIM)
            panel(screen, pygame.Rect(580, 112, 350, 290))
            text(screen, f["m"], "Materials", (596, 122))
            y = 154
            for m in MATERIALS:
                text(screen, f["s"], f"{m}: {ch.materials[m]}", (596, y), MATERIAL_COLORS[m])
                y += 24
            text(screen, f["s"], f"Gold: {ch.gold}", (596, y + 4), GOLD)
            y += 36
            for k, v in ch.consumables.items():
                text(screen, f["xs"], f"{k} x{v}", (596, y), (200, 230, 200))
                y += 17
            for i, rc in enumerate(prof.recipes):
                if rc.desc:
                    text(screen, f["xs"], rc.desc, (46, 112 + i * 68 + 48), (150, 170, 190))
                elif rc.kind == "equip":
                    text(screen, f["xs"], f"{rc.slot.title()}: " + " ".join(f"+{v} {STAT_SHORT[s]}" for s, v in rc.bonuses)
                         + " (scales with levels)", (46, 112 + i * 68 + 48), (150, 170, 190))
            text(screen, f["xs"], "Dungeons drop materials. Gear bonuses grow with profession and character level.",
                 (30, 456), DIM)
        if self.msg:
            for i, line in enumerate(wrap(f["s"], self.msg, 600)[:2]):
                text(screen, f["s"], line, (200, 484 + i * 20), self.msg_color)
        self.draw_buttons(screen)


class BindingsScreen(Screen):
    """Choose which unlocked skill each key (J, K, 1-6) triggers. Skills are never removed."""

    def __init__(self, game):
        super().__init__(game)
        self.sel = "j"
        self.msg = ""
        self.rebuild()

    def _summary(self, sid):
        ch = self.game.character
        if sid in BASIC_IDS:
            prof = ch.class_def.light if sid == "basic_light" else ch.class_def.heavy
            return f"cooldown {prof.cooldown:g}s, no energy cost"
        sk = SKILLS_BY_ID[sid]
        return f"cooldown {sk.cooldown_for(max(1, ch.skill_rank(sid))):g}s, {sk.energy_cost} energy"

    def assign(self, sid):
        r = self.game.char_call("set_binding", key=self.sel, skill_id=sid)
        self.msg = "" if r.get("ok") else r.get("error", "")
        self.rebuild()

    def op(self, t):
        r = self.game.char_call(t)
        self.msg = "" if r.get("ok") else r.get("error", "")
        self.rebuild()

    def rebuild(self):
        ch = self.game.character
        self.buttons = [Button((30, 484, 140, 44), "Back", lambda: self.game.open(SkillsScreen)),
                        Button((190, 484, 170, 44), "Swap J / K", lambda: self.op("swap_bindings")),
                        Button((370, 484, 230, 44), "Restore Defaults", lambda: self.op("reset_bindings"))]
        for i, key in enumerate(BIND_KEYS):
            sid = ch.bindings.get(key)
            known = sid in BASIC_IDS or (sid in SKILLS_BY_ID and ch.skill_rank(sid) > 0)
            name = ch.skill_label(sid) if sid and known else ("(not learned yet)" if sid else "(empty)")
            self.buttons.append(Button((30, 100 + i * 46, 430, 42), f"{key.upper()}:  {name}", lambda k=key: self.pick(k),
                                       selected=key == self.sel, sub="" ))
        opts = [("basic_light", ch.skill_label("basic_light")), ("basic_heavy", ch.skill_label("basic_heavy"))]
        opts += [(sk.id, sk.name) for sk in SKILLS[ch.class_def.name] if sk.active and ch.skill_rank(sk.id) > 0]
        self.option_ids = opts
        for i, (sid, name) in enumerate(opts):
            self.buttons.append(Button((490 + (i % 2) * 225, 130 + (i // 2) * 46, 215, 42), name,
                                       lambda sid=sid: self.assign(sid), selected=ch.bindings.get(self.sel) == sid))
        self.buttons.append(Button((490, 130 + ((len(opts) + 1) // 2) * 46 + 6, 440, 42), "Unequip this key",
                                   lambda: self.assign(None), color=(240, 150, 150)))

    def pick(self, key):
        self.sel = key
        self.rebuild()

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.game.open(SkillsScreen)
        else:
            super().handle_event(e)

    def draw(self, screen):
        f, ch = self.game.fonts, self.game.character
        screen.fill(BG)
        text(screen, f["t"], "KEY BINDINGS", (30, 22))
        text(screen, f["xs"], "Pick a key on the left, then a skill on the right. Changing a binding never removes a skill.",
             (30, 70), DIM)
        sid = ch.bindings.get(self.sel)
        text(screen, f["m"], f"Assign to {self.sel.upper()}", (490, 100), GOLD)
        for i, key in enumerate(BIND_KEYS):
            s2 = ch.bindings.get(key)
            if s2 and (s2 in BASIC_IDS or ch.skill_rank(s2) > 0):
                text(screen, f["xs"], self._summary(s2), (44, 100 + i * 46 + 26), DIM)
        for i, line in enumerate(wrap(f["xs"], "Only unlocked active skills and your basic attacks can be assigned. "
                                      "A skill sits on one key at a time.", 440)):
            text(screen, f["xs"], line, (490, 430 + i * 17), DIM)
        if self.msg:
            text(screen, f["s"], self.msg, (640, 494), (240, 110, 110))
        self.draw_buttons(screen)


class ResultsScreen(Screen):
    TITLES = {"victory": ("VICTORY", (120, 230, 120)), "defeat": ("DEFEATED", (240, 100, 100)),
              "retreat": ("RETREATED", (230, 200, 120))}

    def __init__(self, game, run):
        super().__init__(game)
        self.run = run
        self.buttons = [Button((330, 456, 300, 54), "Return Home", game.go_home, color=GOLD)]

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
            self.game.go_home()
        else:
            super().handle_event(e)

    def draw(self, screen):
        f, r, ch = self.game.fonts, self.run, self.game.character
        title, color = self.TITLES[r.result]
        screen.fill(BG)
        text(screen, f["l"], title, (S.SCREEN_W // 2, 70), color, True)
        text(screen, f["s"], f"Dungeon Level {r.level}  (enemy level {r.enemy_level})", (S.SCREEN_W // 2, 115), DIM, True)
        panel(screen, pygame.Rect(230, 135, 500, 300))
        rows = [f"Enemies defeated: {r.kills}", f"XP gained: {r.xp_gained}",
                f"Levels gained: {r.levels_gained}  (now {ch.progression.level}, {ch.grade.label})",
                f"Gold: +{r.gold_gained}" + (f"  (+{r.bonus_gold} clear bonus)" if r.bonus_gold else "")]
        y = 158
        for line in rows:
            text(screen, f["m"], line, (260, y), TEXT)
            y += 34
        mats = "  ".join(f"{k} x{v}" for k, v in r.materials_gained.items())
        text(screen, f["s"], "Materials: " + (mats or "none"), (260, y - 4), (200, 220, 255))
        y += 26
        text(screen, f["m"], "Loot:", (260, y), GOLD)
        y += 28
        for item in r.loot[:4]:
            text(screen, f["s"], f"{item.label}  {item.describe()}", (280, y), item.color)
            y += 21
        if not r.loot:
            text(screen, f["s"], "none", (280, y), DIM)
        if r.result == "victory" and ch.dungeon_unlocked > r.level:
            text(screen, f["s"], f"Dungeon Level {ch.dungeon_unlocked} unlocked!", (S.SCREEN_W // 2, 436), GREEN, True)
        self.draw_buttons(screen)


class RunScreen(Screen):
    def __init__(self, game, run):
        super().__init__(game)
        self.run = run
        self.paused = False
        self.menu_index = 0
        self.actions = set()

    def handle_event(self, e):
        if e.type != pygame.KEYDOWN:
            return
        if self.paused:
            self._menu_key(e.key)
        elif e.key == pygame.K_ESCAPE:
            self.paused, self.menu_index = True, 0
        elif e.key in JUMP_KEYS:
            self.actions.add("jump")
        elif e.key in LIGHT_KEYS:
            self.actions.add("light")
        elif e.key in HEAVY_KEYS:
            self.actions.add("heavy")
        elif e.key in DODGE_KEYS:
            self.actions.add("dodge")
        elif e.key in SKILL_KEYS:
            self.actions.add(SKILL_KEYS[e.key])
        elif e.key in POTION_KEYS:
            self.actions.add(POTION_KEYS[e.key])

    def _menu_key(self, key):
        n = len(hud.PAUSE_ITEMS)
        if key == pygame.K_ESCAPE:
            self.paused = False
        elif key == pygame.K_UP:
            self.menu_index = (self.menu_index - 1) % n
        elif key == pygame.K_DOWN:
            self.menu_index = (self.menu_index + 1) % n
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            choice = self.menu_index
            if choice == 0:
                self.paused = False
            elif choice == 1:
                self.run.retreat()
            else:
                self.game.running = False

    def update(self, dt):
        actions, self.actions = self.actions, set()
        if not self.paused:
            keys = pygame.key.get_pressed()
            axis = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
            self.run.step(dt, axis, actions)
        if self.run.result:
            self.game.show_results(self.run)

    def draw(self, screen):
        r = self.run
        self.game.renderer.draw_background(r.camera.x)
        self.game.renderer.draw_world(r)
        hud.draw_hud(screen, r, self.game.fonts)
        if not r.player.alive:
            hud.draw_death(screen, self.game.fonts)
        if self.paused:
            hud.draw_pause(screen, self.game.fonts, self.menu_index)
