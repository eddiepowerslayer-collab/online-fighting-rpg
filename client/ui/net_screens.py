"""Screens that talk to the game server: connect, login, characters, marketplace, arena."""
import pygame

from .. import settings as S
from ..classes import CLASS_ORDER, STAT_LABELS
from ..grades import grade_for_level
from ..items import item_from_dict
from ..networking.interp import SnapshotBuffer
from shared import economy
from shared import modes as M
from shared.protocol import DEFAULT_PORT
from .widgets import (BG, DIM, GOLD, GREEN, PANEL, TEXT, Button, Screen, TextField, bar, panel, text, wrap)

RED = (240, 110, 110)
TEAM_COLORS = [(70, 140, 255), (255, 90, 90)]
FFA_COLORS = [(255, 200, 80), (120, 220, 120), (200, 120, 255), (90, 210, 220),
              (255, 140, 60), (240, 120, 180), (160, 200, 90), (200, 200, 210)]


# ====================================================================== connection
class ConnectScreen(Screen):
    def __init__(self, game, msg=""):
        super().__init__(game)
        self.host = TextField((330, 190, 300, 40), "Server address (IP of the host computer)", game.last_host, 40)
        self.port = TextField((330, 270, 140, 40), "Port", str(game.last_port), 5, digits=True)
        self.fields = [self.host, self.port]
        self.host.focused = True
        self.msg = msg
        self.buttons = [Button((330, 330, 300, 56), "Join Game", self.join, color=GOLD, sub="connect to a host"),
                        Button((330, 400, 300, 56), "Host a Game", self.host_game,
                               sub="run the server on this computer")]

    def _port(self):
        try:
            p = int(self.port.text)
            if 1 <= p <= 65535:
                return p
        except ValueError:
            pass
        self.msg = "Port must be a number between 1 and 65535."
        return None

    def join(self):
        p = self._port()
        if p:
            ok, m = self.game.connect(self.host.text.strip(), p)
            self.msg = "" if ok else m

    def host_game(self):
        p = self._port()
        if p:
            ok, m = self.game.host_server(p)
            self.msg = "" if ok else m

    def on_submit(self):
        self.join()

    def draw(self, screen):
        f = self.game.fonts
        screen.fill(BG)
        text(screen, f["l"], "Online Fighting RPG", (S.SCREEN_W // 2, 70), TEXT, True)
        text(screen, f["s"], "Play with people on the same network (Wi-Fi / LAN).", (S.SCREEN_W // 2, 118), DIM, True)
        text(screen, f["xs"], "One person clicks 'Host a Game' and tells the others the address shown after hosting.",
             (S.SCREEN_W // 2, 140), DIM, True)
        text(screen, f["xs"], "Everyone else types that address above and clicks 'Join Game'.",
             (S.SCREEN_W // 2, 158), DIM, True)
        if self.msg:
            for i, line in enumerate(wrap(f["s"], self.msg, 700)[:2]):
                text(screen, f["s"], line, (S.SCREEN_W // 2, 474 + i * 20), RED, True)
        self.draw_buttons(screen)


class LoginScreen(Screen):
    def __init__(self, game, msg=""):
        super().__init__(game)
        self.user = TextField((330, 170, 300, 40), "Username", game.last_user, 20)
        self.pw = TextField((330, 250, 300, 40), "Password", "", 40, password=True)
        self.fields = [self.user, self.pw]
        (self.pw if game.last_user else self.user).focused = True
        self.msg = msg
        self.buttons = [Button((330, 316, 300, 52), "Log In", self.login, color=GOLD),
                        Button((330, 378, 300, 52), "Register", self.register, sub="create a new account"),
                        Button((30, 480, 200, 44), "Change Server", game.disconnect)]

    def login(self):
        ok, m = self.game.login(self.user.text, self.pw.text)
        self.msg = "" if ok else m

    def register(self):
        ok, m = self.game.register(self.user.text, self.pw.text)
        self.msg = "" if ok else m

    def on_submit(self):
        self.login()

    def draw(self, screen):
        f = self.game.fonts
        screen.fill(BG)
        text(screen, f["t"], "Log In", (S.SCREEN_W // 2, 70), TEXT, True)
        text(screen, f["s"], f"Connected to {self.game.net.address[0]}:{self.game.net.address[1]}",
             (S.SCREEN_W // 2, 108), GREEN, True)
        text(screen, f["xs"], "Your account holds up to 6 characters. Your progress is saved on the host's computer.",
             (S.SCREEN_W // 2, 134), DIM, True)
        text(screen, f["xs"], "Passwords are stored hashed but travel unencrypted on the network: use a throwaway one.",
             (S.SCREEN_W // 2, 450), (200, 160, 100), True)
        if self.msg:
            for i, line in enumerate(wrap(f["s"], self.msg, 700)[:2]):
                text(screen, f["s"], line, (S.SCREEN_W // 2, 476 + i * 20), RED, True)
        self.draw_buttons(screen)


# ====================================================================== characters
class CharacterSelectScreen(Screen):
    def __init__(self, game):
        super().__init__(game)
        self.confirm = None
        self.chars = game.list_characters()
        self.rebuild()

    def rebuild(self):
        g = self.game
        self.buttons = []
        for i, c in enumerate(self.chars):
            y = 112 + i * 60
            self.buttons.append(Button((640, y, 130, 48), "Play", lambda cid=c["id"]: g.play_character(cid), color=GREEN))
            if self.confirm == c["id"]:
                self.buttons.append(Button((780, y, 150, 48), "Really delete?", lambda cid=c["id"]: self.delete(cid),
                                           color=RED))
            else:
                self.buttons.append(Button((780, y, 150, 48), "Delete", lambda cid=c["id"]: self.ask(cid)))
        self.buttons.append(Button((30, 484, 220, 44), "New Character", lambda: g.open_new_character(),
                                   enabled=len(self.chars) < 6, color=GOLD))
        self.buttons.append(Button((730, 484, 200, 44), "Log Out", g.logout))

    def ask(self, cid):
        self.confirm = cid
        self.rebuild()

    def delete(self, cid):
        self.game.delete_character(cid)
        self.confirm = None
        self.chars = self.game.list_characters()
        self.rebuild()

    def draw(self, screen):
        f = self.game.fonts
        screen.fill(BG)
        text(screen, f["t"], "Your Characters", (30, 26))
        text(screen, f["s"], f"Account: {self.game.username}    ({len(self.chars)}/6 slots)", (30, 76), DIM)
        if not self.chars:
            text(screen, f["m"], "You have no characters yet. Create one!", (S.SCREEN_W // 2, 250), DIM, True)
        for i, c in enumerate(self.chars):
            y = 112 + i * 60
            panel(screen, pygame.Rect(30, y, 600, 48))
            cd = next((k for k in CLASS_ORDER if k.name == c["class_name"]), CLASS_ORDER[0])
            text(screen, f["m"], c["name"], (46, y + 12), cd.color)
            g = grade_for_level(c["level"])
            text(screen, f["s"], f"{c['class_name']}   Lv {c['level']}", (260, y + 8))
            text(screen, f["xs"], g.label, (260, y + 28), g.color)
            text(screen, f["s"], f"{c['gold']} gold", (480, y + 15), GOLD)
        self.draw_buttons(screen)


class NewCharacterScreen(Screen):
    def __init__(self, game):
        super().__init__(game)
        self.selected = None
        self.msg = ""
        self.name = TextField((330, 58, 300, 36), "Character name", "", 16)
        self.name.focused = True
        self.fields = [self.name]
        self.cards = [(pygame.Rect(22 + i * 186, 108, 172, 340), c) for i, c in enumerate(CLASS_ORDER)]
        self._rebuild()

    def _rebuild(self):
        label = f"Create {self.selected.name}" if self.selected else "Pick a class"
        self.buttons = [Button((330, 466, 300, 52), label, self.create, enabled=self.selected is not None, color=GOLD),
                        Button((30, 484, 140, 44), "Back", self.game.go_character_select)]

    def create(self):
        ok, m = self.game.create_character(self.name.text, self.selected.name)
        self.msg = "" if ok else m

    def on_submit(self):
        if self.selected:
            self.create()

    def handle_event(self, e):
        super().handle_event(e)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for rect, c in self.cards:
                if rect.collidepoint(e.pos):
                    self.selected = c
                    self._rebuild()
                    return

    def draw(self, screen):
        f = self.game.fonts
        screen.fill(BG)
        text(screen, f["t"], "New Character", (30, 26))
        mouse = pygame.mouse.get_pos()
        for rect, c in self.cards:
            sel = c is self.selected
            panel(screen, rect, (52, 58, 84) if rect.collidepoint(mouse) else PANEL, GOLD if sel else (74, 80, 110))
            text(screen, f["m"], c.name, (rect.centerx, rect.y + 24), c.color, True)
            bx, by = rect.centerx, rect.y + 78
            pygame.draw.rect(screen, c.color, (bx - 14, by - 4, 28, 40), border_radius=5)
            pygame.draw.circle(screen, c.color, (bx, by - 12), 11)
            y = rect.y + 128
            for line in wrap(f["xs"], c.description, rect.w - 20):
                text(screen, f["xs"], line, (rect.x + 10, y), DIM)
                y += 17
            y = rect.y + 222
            for r in [f"HP {c.base_hp}   Speed {c.move_speed}", f"Scales: {STAT_LABELS[c.primary_stat]}",
                      f"Armor {round(c.base_reduction * 100)}%   Crit {round(c.base_crit * 100)}%",
                      f"Light: {c.light.name}", f"Heavy: {c.heavy.name}"]:
                text(screen, f["xs"], r, (rect.x + 10, y), TEXT)
                y += 20
        if self.msg:
            text(screen, f["s"], self.msg, (S.SCREEN_W // 2, 454), RED, True)
        self.draw_buttons(screen)


# ====================================================================== marketplace
class MarketScreen(Screen):
    """Player marketplace (browse/sell/my listings/history) and NPC vendors. Every trade is
    performed by the server in one database transaction; this screen only asks."""
    TABS = ("Browse", "Sell", "My Listings", "History", "Vendor")
    FILTERS = (("All", None), ("Gear", "item"), ("Materials", "material"), ("Potions", "potion"))
    SORTS = (("Price: low to high", lambda l: (l["price"], l["id"])),
             ("Price: high to low", lambda l: (-l["price"], l["id"])),
             ("Newest first", lambda l: -l["id"]),
             ("Name A-Z", lambda l: (l["name"].lower(), l["price"])))

    def __init__(self, game):
        super().__init__(game)
        self.tab, self.offset, self.bag_off = "Browse", 0, 0
        self.sel = None
        self.kind_filter, self.sort_i = None, 0
        self.search = TextField((30, 138, 230, 32), "Search", "", 24)
        self.qty = TextField((520, 270, 110, 36), "Quantity", "1", 4, digits=True)
        self.price = TextField((660, 270, 180, 36), "Total price (gold)", "", 9, digits=True)
        self.msg, self.msg_color = "", TEXT
        self.listings, self.mine, self.pending, self.fee = [], [], 0, economy.MARKET_FEE_PERCENT
        self.history = {"sales": [], "purchases": []}
        self.vendor, self.catalog, self.confirm = economy.VENDORS[0], [], None
        self.refresh()

    # ---- data ----
    def refresh(self):
        r = self.game.rpc("market_browse")
        if r.get("ok"):
            self.listings, self.mine = r["listings"], r["mine"]
            self.pending, self.fee = r["pending"], r["fee"]
        else:
            self.say(r.get("error", "Could not load the marketplace."), RED)
        if self.tab == "History":
            h = self.game.rpc("market_history")
            if h.get("ok"):
                self.history = h
        if self.tab == "Vendor":
            v = self.game.rpc("shop_list", vendor=self.vendor)
            self.catalog = v.get("catalog", []) if v.get("ok") else []
        self.rebuild()

    def say(self, m, color=TEXT):
        self.msg, self.msg_color = m, color

    def act(self, t, ok_msg=None, **fields):
        r = self.game.market_call(t, **fields)
        if r.get("ok"):
            self.say(ok_msg(r) if callable(ok_msg) else (ok_msg or "Done."), GREEN)
        else:
            self.say(r.get("error", "That didn't work."), RED)
        self.refresh()

    @staticmethod
    def describe(lst):
        if lst["kind"] == "item":
            try:
                it = item_from_dict(lst["payload"])
                return f"{it.label}   {it.describe()}", it.color
            except ValueError:
                return lst["name"], TEXT
        return f"{lst['quantity']}x {lst['name']}", (200, 220, 255)

    def sellable(self):
        ch = self.game.character
        out = [{"kind": "item", "name": it.name, "index": i, "item": it, "max": 1} for i, it in enumerate(ch.inventory)]
        out += [{"kind": "material", "name": m, "max": n} for m, n in ch.materials.items() if n > 0]
        out += [{"kind": "potion", "name": p, "max": n} for p, n in ch.consumables.items() if n > 0]
        return out

    def view(self):
        q = self.search.text.strip().lower()
        out = [l for l in self.listings
               if (self.kind_filter is None or l["kind"] == self.kind_filter)
               and (not q or q in (self.describe(l)[0] + " " + l["seller_name"]).lower())]
        return sorted(out, key=self.SORTS[self.sort_i][1])

    # ---- layout ----
    def rebuild(self):
        g, ch = self.game, self.game.character
        self.buttons = [Button((30, 484, 140, 44), "Back", g.go_home)]
        if self.confirm:
            self.fields = []
            self.buttons += [Button((330, 360, 300, 52), "Confirm Purchase", self.do_confirm, color=GOLD,
                                    enabled=ch.gold >= self.confirm["price"]),
                             Button((330, 424, 300, 46), "Cancel", self.cancel_confirm)]
            return
        for i, t in enumerate(self.TABS):
            self.buttons.append(Button((30 + i * 160, 72, 150, 38), t, lambda t=t: self.set_tab(t), selected=t == self.tab))
        self.fields = ([self.search] if self.tab == "Browse" else [self.qty, self.price] if self.tab == "Sell" and self.sel else [])
        rows, per = {"Browse": self._browse_rows, "Sell": self._sell_rows, "My Listings": self._mine_rows,
                     "History": lambda: [], "Vendor": self._vendor_rows}[self.tab](), 6
        if self.tab == "Browse":
            per = 5
            for i, (label, kind) in enumerate(self.FILTERS):
                self.buttons.append(Button((280 + i * 100, 138, 94, 32), label, lambda k=kind: self.set_filter(k),
                                           selected=self.kind_filter == kind))
            self.buttons.append(Button((690, 138, 240, 32), self.SORTS[self.sort_i][0], self.next_sort))
        if self.tab == "Vendor":
            per = 5
        self.per = per
        n = len(rows)
        self.offset = max(0, min(self.offset, max(0, n - per)))
        self.buttons += rows[self.offset:self.offset + per] if self.tab != "Vendor" else self._vendor_visible(rows)
        if n > per and self.tab in ("Browse", "Sell", "My Listings", "Vendor"):
            self.buttons.append(Button((200, 484, 110, 44), "< Prev", lambda: self.page(-1), enabled=self.offset > 0))
            self.buttons.append(Button((320, 484, 110, 44), "Next >", lambda: self.page(1), enabled=self.offset + per < n))
        if self.tab == "Sell" and self.sel:
            self.buttons.append(Button((520, 330, 320, 52), "List for Sale", self.do_list, color=GOLD))

    def set_tab(self, t):
        self.tab, self.offset, self.msg = t, 0, ""
        self.refresh()

    def set_filter(self, kind):
        self.kind_filter, self.offset = kind, 0
        self.rebuild()

    def next_sort(self):
        self.sort_i = (self.sort_i + 1) % len(self.SORTS)
        self.rebuild()

    def page(self, d):
        self.offset = max(0, self.offset + d * self.per)
        self.rebuild()

    def handle_event(self, e):
        if self.confirm:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.cancel_confirm()
            else:
                super().handle_event(e)
            return
        if e.type == pygame.MOUSEWHEEL:
            if self.tab == "Vendor" and pygame.mouse.get_pos()[0] > 600:
                self.bag_off = max(0, self.bag_off - e.y)
            else:
                self.offset = max(0, self.offset - e.y)
            self.rebuild()
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and not any(f.focused for f in self.fields):
            self.game.go_home()
        else:
            before = self.search.text
            super().handle_event(e)
            if self.tab == "Browse" and self.search.text != before:
                self.offset = 0
                self.rebuild()

    @staticmethod
    def _place(rows, base):
        for i, b in enumerate(rows):
            b.rect.y = base + (i % 6) * 56
        return rows

    def _browse_rows(self):
        gold, rows = self.game.character.gold, []
        for lst in self.view():
            label, color = self.describe(lst)
            unit = f"  ({lst['price'] // lst['quantity']}g each)" if lst["quantity"] > 1 else ""
            rows.append(Button((30, 0, 900, 50), label,
                               lambda lid=lst["id"], nm=lst["name"], p=lst["price"]: self.act(
                                   "market_buy", f"Bought {nm} for {p} gold!", listing_id=lid),
                               enabled=gold >= lst["price"], color=color,
                               sub=f"Seller {lst['seller_name']}   -   {lst['price']} gold{unit}"
                                   + ("" if gold >= lst["price"] else "   (not enough gold)")))
        for i, b in enumerate(rows):
            b.rect.y = 180 + (i % 5) * 56
        return rows

    def _mine_rows(self):
        rows = []
        for lst in self.mine:
            label, color = self.describe(lst)
            rows.append(Button((30, 0, 900, 50), label,
                               lambda lid=lst["id"]: self.act("market_cancel", "Listing cancelled. Goods returned.",
                                                              listing_id=lid),
                               color=color, sub=f"{lst['price']} gold   -   click to cancel and take it back"))
        return self._place(rows, 122)

    def _sell_rows(self):
        rows = []
        for ent in self.sellable():
            if ent["kind"] == "item":
                label, color = f"{ent['item'].label}   {ent['item'].describe()}", ent["item"].color
            else:
                label, color = f"{ent['name']}  x{ent['max']}", (200, 220, 255)
            key = (ent["kind"], ent["name"], ent.get("index"))
            rows.append(Button((30, 0, 470, 50), label, lambda e=ent: self.pick(e), color=color,
                               selected=self.sel == key, sub=ent["kind"]))
        return self._place(rows, 122)

    def pick(self, ent):
        self.sel = (ent["kind"], ent["name"], ent.get("index"))
        self.qty.text, self.price.text = "1", ""
        self.rebuild()

    def do_list(self):
        kind, name, idx = self.sel
        try:
            price, qty = int(self.price.text or 0), int(self.qty.text or 1)
        except ValueError:
            self.say("Enter whole numbers.", RED)
            return
        if price < 1:
            self.say("Set a price of at least 1 gold.", RED)
            return
        fields = dict(kind=kind, name=name, price=price, qty=1 if kind == "item" else qty)
        if kind == "item":
            fields["item_index"] = idx
        self.sel = None
        self.act("market_list", f"Listed {name} for {price} gold.", **fields)

    # ---- vendors ----
    def _vendor_rows(self):
        ch, rows = self.game.character, []
        for idx, entry in enumerate(self.catalog):
            if entry["kind"] == "item":
                it = item_from_dict(entry["item"])
                label, color, sub = f"{it.label}  {it.describe()}", it.color, f"{it.rarity}  -  {entry['price']} gold"
            else:
                label, color, sub = entry["name"], (200, 220, 255), f"{entry['kind']}  -  {entry['price']} gold"
            rows.append(Button((30, 0, 560, 50), label, lambda e=dict(entry, index=idx): self.ask(e),
                               enabled=ch.gold >= entry["price"], color=color, sub=sub))
        for i, b in enumerate(rows):
            b.rect.y = 176 + (i % 5) * 56
        return rows

    def _vendor_visible(self, rows):
        g, ch = self.game, self.game.character
        out = rows[self.offset:self.offset + 5]
        for i, v in enumerate(economy.VENDORS):
            out.append(Button((30 + i * 155, 114, 150, 32), v, lambda v=v: self.pick_vendor(v), selected=v == self.vendor))
        for i, it in enumerate(ch.inventory[self.bag_off:self.bag_off + 5]):
            price = economy.vendor_sell_price({"bonuses": [list(b) for b in it.bonuses]})
            idx = self.bag_off + i
            out.append(Button((610, 176 + i * 56, 320, 50), f"{it.label}  {it.describe()}",
                              lambda idx=idx, nm=it.name: self.act("vendor_sell", lambda r: f"Sold {nm} for {r['price']} gold.",
                                                                   item_index=idx),
                              color=it.color, sub=f"Vendor pays {price} gold"))
        return out

    def pick_vendor(self, v):
        self.vendor, self.offset = v, 0
        self.refresh()

    def ask(self, entry):
        self.confirm = entry
        self.rebuild()

    def cancel_confirm(self):
        self.confirm = None
        self.rebuild()

    def do_confirm(self):
        e, self.confirm = self.confirm, None
        self.act("shop_buy", lambda r: f"Bought {e['name']} for {r['cost']} gold.", vendor=self.vendor, index=e["index"], qty=1)

    # ---- drawing ----
    def draw(self, screen):
        f, ch = self.game.fonts, self.game.character
        screen.fill(BG)
        text(screen, f["t"], "MARKETPLACE", (30, 24))
        text(screen, f["m"], f"Gold: {ch.gold:,}", (760, 30), GOLD)
        if self.pending:
            text(screen, f["xs"], f"{self.pending} gold from sales waiting (collected when you return home)", (500, 58), GREEN)
        if self.tab == "Browse":
            v = self.view()
            if not v:
                text(screen, f["m"], "No matching listings." if self.listings else "No one is selling anything yet.",
                     (S.SCREEN_W // 2, 300), DIM, True)
            text(screen, f["xs"], f"{len(v)} of {len(self.listings)} listing(s) from other players. "
                 f"Click to buy. Sellers pay a {self.fee}% fee.", (30, 466), DIM)
        elif self.tab == "Sell":
            text(screen, f["xs"], "Pick something from your bag (equipped gear can't be sold; unequip it first).", (30, 112), DIM)
            if not self.sellable():
                text(screen, f["m"], "Nothing to sell yet.", (260, 260), DIM, True)
            if self.sel:
                kind, name, idx = self.sel
                panel(screen, pygame.Rect(510, 122, 420, 340))
                text(screen, f["m"], f"Selling: {name}", (526, 134), GOLD)
                if kind == "item":
                    it = ch.inventory[idx] if idx is not None and idx < len(ch.inventory) else None
                    if it:
                        vp = economy.vendor_sell_price({"bonuses": [list(b) for b in it.bonuses]})
                        text(screen, f["s"], it.describe(), (526, 166), it.color)
                        text(screen, f["xs"], f"An NPC vendor would pay {vp} gold instantly.", (526, 190), DIM)
                else:
                    text(screen, f["xs"], f"Set the TOTAL price for the whole quantity.", (526, 166), DIM)
                try:
                    p = int(self.price.text or 0)
                except ValueError:
                    p = 0
                text(screen, f["xs"], f"You receive {p - economy.market_fee(p)} gold after the {self.fee}% fee.",
                     (526, 390), GREEN if p else DIM)
            else:
                text(screen, f["s"], "Select an item on the left to set a price.", (700, 280), DIM, True)
        elif self.tab == "My Listings":
            text(screen, f["xs"], f"Your active listings ({len(self.mine)}/10). Click one to cancel it.", (30, 112), DIM)
            if not self.mine:
                text(screen, f["m"], "You have nothing listed.", (S.SCREEN_W // 2, 260), DIM, True)
        elif self.tab == "History":
            for col, (title, rows, sold) in enumerate((("Your sales", self.history["sales"], True),
                                                      ("Your purchases", self.history["purchases"], False))):
                x = 30 + col * 460
                panel(screen, pygame.Rect(x, 120, 440, 350))
                text(screen, f["m"], title, (x + 14, 128), GOLD)
                if not rows:
                    text(screen, f["s"], "Nothing yet.", (x + 14, 164), DIM)
                for i, l in enumerate(rows[:10]):
                    label = self.describe(l)[0]
                    who = f"to {l.get('other') or '?'}" if sold else f"from {l.get('other') or '?'}"
                    earned = l["price"] - economy.market_fee(l["price"])
                    text(screen, f["xs"], f"{label[:34]}", (x + 14, 160 + i * 30), self.describe(l)[1])
                    text(screen, f["xs"], f"{l['price']}g {who}" + (f" (you got {earned}g)" if sold else ""),
                         (x + 14, 175 + i * 30), DIM)
        else:
            text(screen, f["xs"], economy.VENDOR_BLURB[self.vendor] + ". Click to buy (you confirm first).", (30, 156), DIM)
            text(screen, f["xs"], "Sell to vendor (scroll):", (610, 156), DIM)
        if self.msg:
            for i, line in enumerate(wrap(f["s"], self.msg, 480)[:2]):
                text(screen, f["s"], line, (450, 486 + i * 20), self.msg_color)
        self.draw_buttons(screen)
        if self.confirm:
            self._draw_confirm(screen)

    def _draw_confirm(self, screen):
        f, ch, e = self.game.fonts, self.game.character, self.confirm
        shade = pygame.Surface((S.SCREEN_W, S.SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 200))
        screen.blit(shade, (0, 0))
        panel(screen, pygame.Rect(250, 120, 460, 360))
        text(screen, f["m"], "Confirm purchase", (480, 144), GOLD, True)
        if e["kind"] == "item":
            it = item_from_dict(e["item"])
            text(screen, f["m"], it.label, (480, 190), it.color, True)
            text(screen, f["s"], f"{it.rarity} {it.slot}", (480, 220), DIM, True)
            text(screen, f["m"], it.describe(), (480, 252), TEXT, True)
        else:
            text(screen, f["m"], e["name"], (480, 200), (200, 220, 255), True)
            text(screen, f["s"], f"1x {e['kind']}", (480, 232), DIM, True)
        text(screen, f["m"], f"Price: {e['price']:,} gold", (480, 300), GOLD, True)
        text(screen, f["s"], f"You have {ch.gold:,} gold  ->  {ch.gold - e['price']:,} after", (480, 332), DIM, True)
        self.draw_buttons(screen)


# ====================================================================== arena lobby
class LobbyScreen(Screen):
    def __init__(self, game):
        super().__init__(game)
        self.counts = {m: 0 for m in M.MODE_ORDER}
        self.need = {m: M.players_needed(m) for m in M.MODE_ORDER}
        self.you, self.online = None, []
        self.msg = ""
        r = game.rpc("lobby_info")
        if r.get("ok"):
            self.counts, self.you, self.online = r["counts"], r["you"], r["online"]
            self.need = {m["mode"]: m["need"] for m in r["modes"]}
        self.rebuild()

    def rebuild(self):
        self.buttons = [Button((30, 484, 140, 44), "Back", self.back)]
        for i, mode in enumerate(M.MODE_ORDER):
            queued = self.you == mode
            n = self.counts.get(mode, 0)
            if M.is_team_mode(mode):
                sub = f"{n}/{self.need[mode]} waiting   ({M.team_size(mode)} per team)"
            elif mode == "coop":
                sub = f"{n} waiting  ({self.need[mode]}-{M.max_players(mode)} players, fight AI enemies)"
            else:
                sub = f"{n} waiting  ({self.need[mode]}-{M.max_players(mode)} players)"
            if queued:
                sub = "Searching...  click to cancel   " + sub
            self.buttons.append(Button((30 + (i % 2) * 320, 124 + (i // 2) * 66, 308, 60), M.mode_label(mode),
                                       lambda m=mode: self.toggle(m), sub=sub, selected=queued,
                                       color=GOLD if queued else TEXT))

    def toggle(self, mode):
        if self.you == mode:
            r = self.game.rpc("queue_leave")
            self.you = None
        else:
            r = self.game.rpc("queue_join", mode=mode)
            if r.get("ok"):
                self.you, self.counts = r["you"], r["counts"]
        if not r.get("ok"):
            self.msg = r.get("error", "")
        self.rebuild()

    def back(self):
        if self.you:
            self.game.rpc("queue_leave")
        self.game.go_home()

    def on_net(self, msg):
        if msg["t"] == "queue":
            self.counts, self.you, self.online = msg["counts"], msg["you"], msg.get("online", self.online)
            self.rebuild()
        elif msg["t"] == "error":
            self.msg = msg.get("error", "")

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.back()
        else:
            super().handle_event(e)

    def draw(self, screen):
        f, ch = self.game.fonts, self.game.character
        screen.fill(BG)
        text(screen, f["t"], "ARENA", (30, 26))
        text(screen, f["s"], f"{ch.name}  -  {ch.class_def.name} Lv {ch.progression.level}", (30, 76), DIM)
        text(screen, f["xs"], "Pick a mode to queue. A match starts when enough players on your network are waiting.", (30, 100), DIM)
        panel(screen, pygame.Rect(680, 100, 250, 370))
        text(screen, f["m"], f"Online ({len(self.online)})", (694, 108), GOLD)
        for i, p in enumerate(self.online[:16]):
            state = "in match" if p["busy"] else (f"queued {p['mode']}" if p["mode"] else "lobby")
            text(screen, f["xs"], f"{p['name']}  Lv{p['level']}", (694, 142 + i * 20), TEXT)
            text(screen, f["xs"], state, (840, 142 + i * 20), DIM)
        notes = ["PvP is fair: everyone is scaled to level 30 (gear and skill ranks capped, no god skills).",
                 "Team modes: two teams, no friendly fire. First team to the kill target, or most kills at the time limit, wins.",
                 "Free For All: every player for themselves.   Co-op PvE: team up against shared enemies and a boss.",
                 "Winning gives XP and gold. Leaving a match early forfeits your rewards."]
        y = 394
        for line in notes:
            for part in wrap(f["xs"], line, 640):
                text(screen, f["xs"], part, (30, y), DIM)
                y += 17
        if self.msg:
            text(screen, f["s"], self.msg, (340, 494), RED)
        self.draw_buttons(screen)


# ====================================================================== the arena match
ACTION_KEYS = {pygame.K_w: "jump", pygame.K_UP: "jump", pygame.K_SPACE: "jump", pygame.K_j: "light",
               pygame.K_z: "light", pygame.K_k: "heavy", pygame.K_x: "heavy", pygame.K_LSHIFT: "dodge",
               pygame.K_RSHIFT: "dodge", pygame.K_l: "dodge", pygame.K_1: "skill1", pygame.K_2: "skill2",
               pygame.K_3: "skill3", pygame.K_4: "skill4", pygame.K_5: "skill5", pygame.K_6: "skill6"}


class ArenaScreen(Screen):
    def __init__(self, game, found):
        super().__init__(game)
        self.found = found
        self.you = found["you"]
        self.info = {p["id"]: p for p in found["players"]}
        self.team_mode = M.is_team_mode(found["mode"])
        self.coop = found["mode"] == "coop"
        self.buf = SnapshotBuffer()
        self.latest = None
        self.me_pos = None
        self.cam = 0.0
        self.pending = set()
        self.last_axis, self.last_send = None, 0.0
        self.texts = []            # floating damage numbers [text, x, y, life, color]
        self.feed = []             # kill feed [text, life, color]
        self.end = None
        self.confirm_leave = False
        self.sky_cam = 0.0
        self.buttons = [Button((190, 440, 280, 50), "Play Again", lambda: game.rematch(found["mode"]), color=GOLD),
                        Button((490, 440, 280, 50), "Return to Lobby", game.go_lobby)]

    # ---- networking ----
    def on_net(self, msg):
        t = msg["t"]
        if t == "snap":
            self.buf.push(msg)
            self.latest = msg
            for ev in msg["ev"]:
                self._event(ev, msg)
        elif t == "match_end":
            self.end = msg
            if msg.get("data"):
                self.game.apply_character(msg["data"], msg["rev"], self.game.character.id)

    def _name(self, pid):
        return self.info.get(pid, {}).get("name", "?")

    def _color(self, pid):
        info = self.info.get(pid, {"team": 0})
        return TEAM_COLORS[info["team"] % 2] if self.team_mode else FFA_COLORS[pid % 8]

    def _event(self, ev, snap):
        if ev["k"] == "hit":
            self.texts.append([("CRIT " if ev["c"] else "") + str(ev["d"]), ev["x"], ev["y"], 0.8,
                               GOLD if ev["c"] else (255, 255, 255)])
        elif ev["k"] == "kill":
            victim = ev.get("n") or self._name(ev["t"])
            self.feed.append([f"{self._name(ev['by'])} defeated {victim}", 5.0, self._color(ev["by"])])
            self.feed = self.feed[-5:]

    # ---- input ----
    def handle_event(self, e):
        if self.end:
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self.game.go_lobby()
            else:
                super().handle_event(e)
            return
        if e.type != pygame.KEYDOWN:
            return
        if self.confirm_leave:
            if e.key in (pygame.K_y, pygame.K_RETURN):
                self.game.leave_match()
            elif e.key in (pygame.K_n, pygame.K_ESCAPE):
                self.confirm_leave = False
        elif e.key == pygame.K_ESCAPE:
            self.confirm_leave = True
        elif e.key in ACTION_KEYS:
            self.pending.add(ACTION_KEYS[e.key])

    def update(self, dt):
        for t in self.texts:
            t[2] -= 40 * dt
            t[3] -= dt
        self.texts = [t for t in self.texts if t[3] > 0]
        for fd in self.feed:
            fd[1] -= dt
        self.feed = [fd for fd in self.feed if fd[1] > 0]
        if self.end or not self.game.net.connected:
            return
        k = pygame.key.get_pressed()
        axis = int(k[pygame.K_d] or k[pygame.K_RIGHT]) - int(k[pygame.K_a] or k[pygame.K_LEFT])
        if self.confirm_leave:
            axis, self.pending = 0, set()
        now = pygame.time.get_ticks() / 1000.0
        if axis != self.last_axis or self.pending or now - self.last_send > 0.1:
            try:
                self.game.net.send("input", axis=axis, actions=sorted(self.pending))
            except Exception:  # noqa: BLE001
                pass
            self.last_axis, self.last_send, self.pending = axis, now, set()

    # ---- drawing ----
    def draw(self, screen):
        f, g = self.game.fonts, self.game
        arena = self.found["arena"]
        snap = self.latest
        width = arena["width"]
        if snap is None:
            screen.fill(BG)
            text(screen, f["m"], "Waiting for the match to start...", (S.SCREEN_W // 2, S.SCREEN_H // 2), DIM, True)
            return
        positions = self.buf.positions()
        me = next((p for p in snap["players"] if p["id"] == self.you), None)
        if me:
            tgt = (me["x"], me["y"])
            self.me_pos = tgt if self.me_pos is None else (self.me_pos[0] + (tgt[0] - self.me_pos[0]) * 0.5,
                                                           self.me_pos[1] + (tgt[1] - self.me_pos[1]) * 0.5)
            positions[self.you] = self.me_pos
            self.cam = max(0, min(self.me_pos[0] - S.SCREEN_W / 2 + 17, width - S.SCREEN_W))
        cam = int(self.cam)
        g.renderer.draw_background(cam)
        gy = arena["ground_y"]
        pygame.draw.rect(screen, (70, 52, 38), (-cam, gy, width, S.SCREEN_H - gy))
        pygame.draw.rect(screen, (80, 150, 70), (-cam, gy, width, 8))
        for x, y, w in arena["platforms"]:
            pygame.draw.rect(screen, (120, 120, 135), (x - cam, y, w, S.PLATFORM_THICKNESS))
            pygame.draw.rect(screen, (170, 170, 185), (x - cam, y, w, 4))
        for eid, ex, ey, ef, ehp, emhp, kind, eal, etel, eboss in snap.get("en", []):
            cfg = S.ENEMY_TYPES.get(kind)
            if cfg is None or not eal:
                continue
            er = pygame.Rect(ex - cam, ey, cfg["width"], cfg["height"])
            col = tuple(min(255, c + 70) for c in cfg["color"]) if etel else cfg["color"]
            g.renderer._body(er, col, ef)
            if etel:
                text(screen, f["m"], "!", (er.centerx, er.top - 44), (255, 240, 120), True)
            text(screen, f["xs"], ("BOSS " if eboss else "") + cfg["name"], (er.centerx, er.top - 30), (255, 200, 120), True)
            bar(screen, pygame.Rect(er.centerx - 30, er.top - 14, 60, 7), ehp / max(1, emhp), (210, 60, 60))
        for p in snap["players"]:
            if not p["al"]:
                continue
            x, y = positions.get(p["id"], (p["x"], p["y"]))
            r = pygame.Rect(int(x) - cam, int(y), S.PLAYER["width"], S.PLAYER["height"])
            color = self._color(p["id"])
            alpha = 120 if (p["inv"] or p["dodge"]) else 255
            g.renderer._body(r, color, p["f"], alpha)
            if p["buff"]:
                pygame.draw.ellipse(screen, (255, 225, 100), r.inflate(16, 12), 2)
            if p["id"] == self.you:
                pygame.draw.polygon(screen, (255, 255, 255), [(r.centerx - 6, r.top - 26), (r.centerx + 6, r.top - 26),
                                                              (r.centerx, r.top - 16)])
            name = self._name(p["id"]) + (" (offline)" if p["dc"] else "")
            text(screen, f["xs"], name, (r.centerx, r.top - 34), color, True)
            bw = 48
            bar(screen, pygame.Rect(r.centerx - bw // 2, r.top - 12, bw, 6), p["hp"] / max(1, p["mhp"]), (210, 60, 60))
        for ax, ay, aw, ah, kind, col in snap["atks"]:
            rect = pygame.Rect(ax - cam, ay, aw, ah)
            c = tuple(int(col[i:i + 2], 16) for i in (0, 2, 4))
            if kind == 1:
                pygame.draw.ellipse(screen, c, rect)
            else:
                s = pygame.Surface(rect.size, pygame.SRCALPHA)
                s.fill((*c, 90))
                screen.blit(s, rect.topleft)
        for t in self.texts:
            text(screen, f["m"], t[0], (int(t[1]) - cam - 8, int(t[2])), t[4])
        self._hud(screen, snap, me)
        if self.end:
            self._end_overlay(screen)
        elif self.confirm_leave:
            shade = pygame.Surface((S.SCREEN_W, S.SCREEN_H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 170))
            screen.blit(shade, (0, 0))
            text(screen, f["t"], "Leave the match?", (S.SCREEN_W // 2, 210), TEXT, True)
            text(screen, f["m"], "You forfeit your rewards.   Y = leave    N = stay", (S.SCREEN_W // 2, 260), DIM, True)

    def _hud(self, screen, snap, me):
        f = self.game.fonts
        mode = self.found["mode"]
        if self.coop:
            left = sum(1 for e in snap.get("en", []) if e[7])
            text(screen, f["t"], f"Enemies left: {left}", (S.SCREEN_W // 2, 28), GOLD, True)
            text(screen, f["xs"], "defeat them all, including the boss, before time runs out", (S.SCREEN_W // 2, 54), DIM, True)
        elif self.team_mode:
            a, b = snap["ts"]
            text(screen, f["t"], str(a), (S.SCREEN_W // 2 - 60, 22), TEAM_COLORS[0], True)
            text(screen, f["t"], str(b), (S.SCREEN_W // 2 + 60, 22), TEAM_COLORS[1], True)
            text(screen, f["xs"], f"first to {self.found['target']}", (S.SCREEN_W // 2, 50), DIM, True)
            mine = self.info[self.you]["team"]
            text(screen, f["xs"], "You are on the " + ("BLUE" if mine == 0 else "RED") + " team", (S.SCREEN_W // 2, 66),
                 TEAM_COLORS[mine], True)
        else:
            rows = sorted(snap["players"], key=lambda p: -p["k"])[:5]
            for i, p in enumerate(rows):
                text(screen, f["xs"], f"{self._name(p['id'])}: {p['k']}", (S.SCREEN_W - 170, 12 + i * 16), self._color(p["id"]))
            text(screen, f["xs"], f"first to {self.found['target']} kills", (S.SCREEN_W // 2, 50), DIM, True)
        tl = int(snap["tl"])
        text(screen, f["m"], f"{tl // 60}:{tl % 60:02d}", (S.SCREEN_W // 2, 86), TEXT, True)
        text(screen, f["xs"], M.mode_label(mode), (14, 12), DIM)
        if me:
            bar(screen, pygame.Rect(14, 30, 220, 16), me["hp"] / max(1, me["mhp"]), (200, 50, 60))
            text(screen, f["xs"], f"HP {me['hp']}/{me['mhp']}", (20, 31))
            text(screen, f["xs"], f"Kills {me['k']}   Deaths {me['d']}", (14, 52), DIM)
            if not me["al"] and snap["state"] == "active":
                text(screen, f["l"], "DEFEATED", (S.SCREEN_W // 2, 200), (255, 200, 200), True)
                text(screen, f["m"], f"Respawning in {me['rt']:.0f}...", (S.SCREEN_W // 2, 250), TEXT, True)
        if snap["state"] == "countdown":
            text(screen, f["l"], str(max(1, int(snap["cd"]) + 1)), (S.SCREEN_W // 2, 200), GOLD, True)
            text(screen, f["m"], "Get ready!", (S.SCREEN_W // 2, 250), TEXT, True)
        you = (self.latest or {}).get("you", {}).get("skills", [])
        x = S.SCREEN_W - 10 - len(you) * 60
        for sk in you:
            rect = pygame.Rect(x, S.SCREEN_H - 62, 56, 50)
            pygame.draw.rect(screen, (30, 32, 46), rect, border_radius=6)
            if sk["cd"] > 0:
                sh = pygame.Surface((rect.w, int(rect.h * min(1, sk["cd"] / max(0.01, sk["max"])))), pygame.SRCALPHA)
                sh.fill((0, 0, 0, 170))
                screen.blit(sh, rect.topleft)
            pygame.draw.rect(screen, (120, 130, 170), rect, 2, border_radius=6)
            text(screen, f["m"], str(sk["key"]), (rect.x + 6, rect.y + 2))
            text(screen, f["xs"], sk["name"][:8], (rect.x + 4, rect.y + 30), (200, 205, 225))
            if sk["cd"] > 0:
                text(screen, f["s"], f"{sk['cd']:.0f}", (rect.right - 16, rect.y + 6), (255, 200, 120))
            x += 60
        energy = (self.latest or {}).get("you", {}).get("energy")
        if energy is not None:
            bar(screen, pygame.Rect(S.SCREEN_W - 250, S.SCREEN_H - 82, 230, 10), energy / 100.0, (90, 150, 240))
        for i, (msg, life, col) in enumerate(self.feed):
            text(screen, f["s"], msg, (14, S.SCREEN_H - 24 - i * 18 - 70), col)
        text(screen, f["xs"], "J/K/1-6 skills  Shift dodge  Esc leave", (S.SCREEN_W - 300, 118), DIM)

    def _end_overlay(self, screen):
        f = self.game.fonts
        res = self.end["results"]
        shade = pygame.Surface((S.SCREEN_W, S.SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 190))
        screen.blit(shade, (0, 0))
        mine = next((p for p in res["players"] if p["pid"] == self.you), None)
        title, col = {"win": ("VICTORY!", GREEN), "loss": ("DEFEAT", RED), "draw": ("DRAW", GOLD)}.get(
            mine["result"] if mine else "draw", ("MATCH OVER", TEXT))
        if res["aborted"]:
            title, col = "MATCH CANCELLED", DIM
        text(screen, f["l"], title, (S.SCREEN_W // 2, 64), col, True)
        rows = sorted(res["players"], key=lambda p: (-p["kills"], p["deaths"]))
        y = 120
        for p in rows:
            c = self._color(p["pid"])
            line = f"{p['name']}   K {p['kills']}  D {p['deaths']}   {p['result'].upper()}" + ("  (left)" if p["left"] else "")
            text(screen, f["m"], line, (S.SCREEN_W // 2, y), c, True)
            y += 28
        if mine and "xp" in mine:
            extra = f"   +{mine['loot']} item(s)" if mine.get("loot") else ""
            text(screen, f["m"], f"Rewards: +{mine['xp']} XP   +{mine['gold']} gold{extra}", (S.SCREEN_W // 2, 400), GOLD, True)
        self.draw_buttons(screen)
