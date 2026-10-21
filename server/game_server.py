"""LAN game server: accounts, characters, marketplace, matchmaking and arena matches.

Authoritative: the server owns the database and runs all PvP combat. It validates every
field of every message, limits message size and rate, and never trusts client-reported
damage, XP, gold or inventory for anything it can compute itself.
"""
import asyncio
import logging
import threading
import time

from client import settings as S
from client.character import Character, CharacterDataError
from client.classes import CLASSES
from client.progression import xp_to_next
from server.arena import ARENA_WIDTH, PLATFORMS, Arena
from shared import economy
from shared import modes as M
from shared.protocol import (MAX_CLIENT_MSG, PROTOCOL_VERSION, ProtocolError, decode, encode, field)
from storage.database import Database, StorageError, ValidationError

log = logging.getLogger("server")
TICK_RATE = 30
SNAPSHOT_EVERY = 2          # 15 snapshots/second
IDLE_TIMEOUT = 90.0
MAX_SEND_BUFFER = 1_000_000


class Session:
    def __init__(self, server, reader, writer):
        self.server, self.reader, self.writer = server, reader, writer
        self.account_id = self.username = None
        self.char_id = self.char_name = None
        self.queue_mode = None
        self.char_class = ""
        self.char_level = 1
        self.arena = None
        self.pid = None
        self.hello = False
        self.tokens, self.last_refill = 150.0, time.monotonic()
        self.violations = self.failed_logins = 0
        self.closed = False

    @property
    def in_lobby(self):
        return self.char_id is not None and self.arena is None

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(150.0, self.tokens + (now - self.last_refill) * 100.0)
        self.last_refill = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True

    def send(self, msg: dict):
        if self.closed:
            return
        try:
            self.writer.write(encode(msg))
            if self.writer.transport.get_write_buffer_size() > MAX_SEND_BUFFER:
                log.warning("dropping slow client %s", self.username)
                self.close()
        except (ConnectionError, RuntimeError):
            self.closed = True

    def close(self):
        self.closed = True
        try:
            self.writer.close()
        except Exception:  # noqa: BLE001
            pass


class GameServer:
    def __init__(self, db_path, host="0.0.0.0", port=5555, allow_small=False):
        self.db = Database(db_path)
        self.allow_small = allow_small        # TESTING option: smaller matches
        self.flex_timers = {}
        self.host, self.port = host, port
        self.sessions = set()
        self.by_account = {}
        self.queues = {m: [] for m in M.MODE_ORDER}
        self.char_match = {}          # character id -> Arena (for reconnects)
        self.match_tasks = set()
        self.next_match_id = 1
        self.server = None
        self.handlers = {
            "ping": self.h_ping, "hello": self.h_hello, "register": self.h_register, "login": self.h_login,
            "list_chars": self.h_list_chars, "create_char": self.h_create_char,
            "delete_char": self.h_delete_char, "select_char": self.h_select_char,
            "save_char": self.h_save_char, "market_browse": self.h_market_browse,
            "market_list": self.h_market_list, "market_buy": self.h_market_buy,
            "market_cancel": self.h_market_cancel, "vendor_sell": self.h_vendor_sell,
            "lobby_info": self.h_lobby_info,
            "queue_join": self.h_queue_join, "queue_leave": self.h_queue_leave,
            "input": self.h_input, "leave_match": self.h_leave_match, "logout": self.h_logout,
            "collect": self.h_collect, "market_history": self.h_market_history, "shop_list": self.h_shop_list,
            "shop_buy": self.h_shop_buy, "spend_stat": self.h_spend_stat, "buy_skill": self.h_buy_skill,
            "set_binding": self.h_set_binding, "swap_bindings": self.h_swap_bindings,
            "reset_bindings": self.h_reset_bindings, "equip": self.h_equip, "unequip": self.h_unequip,
            "choose_profession": self.h_choose_profession,
        }
        self.pre_auth = {"ping", "hello", "register", "login"}
        self.needs_char = {"market_browse", "market_list", "market_buy", "market_cancel", "vendor_sell",
                           "shop_buy", "shop_list", "lobby_info", "queue_join", "queue_leave", "save_char", "collect",
                           "market_history", "spend_stat", "buy_skill", "set_binding", "swap_bindings",
                           "reset_bindings", "equip", "unequip", "choose_profession"}

    # ------------------------------------------------------------ lifecycle
    async def start(self):
        self.server = await asyncio.start_server(self._handle, self.host, self.port, limit=MAX_CLIENT_MSG)
        self.port = self.server.sockets[0].getsockname()[1]
        log.info("Game server listening on %s:%s", self.host, self.port)

    async def stop(self):
        for t in list(self.match_tasks):
            t.cancel()
        for h in self.flex_timers.values():
            h.cancel()
        for s in list(self.sessions):
            s.close()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        self.db.close()

    # ------------------------------------------------------------ connection loop
    async def _handle(self, reader, writer):
        s = Session(self, reader, writer)
        self.sessions.add(s)
        try:
            while not s.closed:
                try:
                    line = await asyncio.wait_for(reader.readuntil(b"\n"), IDLE_TIMEOUT)
                except (asyncio.LimitOverrunError, ValueError):
                    s.send({"t": "error", "error": "message too large"})
                    break
                if not s.allow():
                    s.violations += 1
                    if s.violations > 300:
                        break
                    continue
                msg = None
                try:
                    msg = decode(line)
                    reply = self._dispatch(s, msg)
                except ProtocolError as e:
                    s.violations += 1
                    self._reply(s, msg, {"ok": False, "error": f"bad request: {e}"})
                    if s.violations > 30:
                        break
                    continue
                except ValidationError as e:
                    reply = {"ok": False, "error": str(e), "stale": str(e) == "stale"}
                except StorageError as e:
                    log.error("storage error: %s", e)
                    reply = {"ok": False, "error": "Server database error. Try again."}
                except CharacterDataError as e:
                    reply = {"ok": False, "error": f"Invalid character data: {e}"}
                if reply is not None:
                    self._reply(s, msg, reply)
                if msg["t"] == "login" and reply and not reply.get("ok"):
                    s.failed_logins += 1
                    if s.failed_logins > 8:
                        break
                    await asyncio.sleep(min(2.0, 0.3 * s.failed_logins))   # slow brute-forcing
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            self._cleanup(s)
            s.close()

    @staticmethod
    def _reply(s, msg, body):
        if msg is not None and "id" in msg:
            s.send(dict(body, t="reply", re=msg["id"]))

    def _dispatch(self, s, msg):
        t = msg["t"]
        h = self.handlers.get(t)
        if h is None:
            raise ProtocolError("unknown message type")
        if t != "hello" and not s.hello:
            raise ProtocolError("send hello first")
        if t not in self.pre_auth and s.account_id is None:
            raise ValidationError("Please log in first.")
        if t in self.needs_char and s.char_id is None:
            raise ValidationError("Select a character first.")
        return h(s, msg)

    def _cleanup(self, s):
        self.sessions.discard(s)
        if s.account_id is not None and self.by_account.get(s.account_id) is s:
            del self.by_account[s.account_id]
        self._leave_queue(s)
        if s.arena is not None:
            s.arena.set_connected(s.pid, False)
            s.arena.sessions.pop(s.pid, None)
            s.arena = None
        self._broadcast_queue()

    # ------------------------------------------------------------ account handlers
    def h_ping(self, s, msg):
        return {"ok": True}

    def h_hello(self, s, msg):
        if field(msg, "v", int) != PROTOCOL_VERSION:
            return {"ok": False, "error": f"Protocol mismatch: server speaks v{PROTOCOL_VERSION}."}
        s.hello = True
        return {"ok": True, "v": PROTOCOL_VERSION, "modes": list(M.MODE_ORDER)}

    def _login_ok(self, s, account_id, username):
        old = self.by_account.get(account_id)
        if old is not None and old is not s:            # one live session per account
            old.send({"t": "kicked", "reason": "You logged in from another location."})
            old.close()
        s.account_id, s.username = account_id, username
        self.by_account[account_id] = s
        return {"ok": True, "account": {"id": account_id, "username": username}}

    def h_register(self, s, msg):
        user = field(msg, "username", str, maxlen=32)
        pw = field(msg, "password", str, maxlen=128)
        aid = self.db.create_account(user, pw)
        return self._login_ok(s, aid, user.strip())

    def h_login(self, s, msg):
        user = field(msg, "username", str, maxlen=32)
        pw = field(msg, "password", str, maxlen=128)
        aid = self.db.authenticate(user, pw)
        if aid is None:
            return {"ok": False, "error": "Wrong username or password."}
        return self._login_ok(s, aid, self.db.account_username(aid))

    def h_logout(self, s, msg):
        self._leave_queue(s)
        if s.arena is not None:
            self.h_leave_match(s, msg)
        if s.account_id is not None and self.by_account.get(s.account_id) is s:
            del self.by_account[s.account_id]
        s.account_id = s.username = s.char_id = s.char_name = None
        self._broadcast_queue()
        return {"ok": True}

    def h_collect(self, s, msg):
        """Move marketplace sale earnings into the character's gold (atomic)."""
        if s.arena is not None:
            raise ValidationError("Not during a match.")
        data, rev, collected = self.db.load_character(s.account_id, s.char_id)
        return {"ok": True, "data": data, "rev": rev, "collected": collected}

    # ------------------------------------------------------------ character handlers
    def h_list_chars(self, s, msg):
        return {"ok": True, "characters": self.db.list_characters(s.account_id)}

    def h_create_char(self, s, msg):
        name = field(msg, "name", str, maxlen=32)
        cls = field(msg, "class", str, maxlen=16)
        if cls not in CLASSES:
            raise ValidationError("Unknown class.")
        cid = self.db.create_character(s.account_id, name, Character(CLASSES[cls], name.strip()).to_dict())
        return {"ok": True, "char_id": cid}

    def h_delete_char(self, s, msg):
        cid = field(msg, "char_id", int)
        if cid in self.char_match or cid == s.char_id and s.arena:
            raise ValidationError("That character is in a match.")
        self.db.delete_character(s.account_id, cid)
        if s.char_id == cid:
            self._leave_queue(s)
            s.char_id = None
        return {"ok": True}

    def h_select_char(self, s, msg):
        cid = field(msg, "char_id", int)
        self._leave_queue(s)
        data, rev, collected = self.db.load_character(s.account_id, cid)
        s.char_id, s.char_name = cid, data["name"]
        s.char_class, s.char_level = data["class"], data["level"]
        reply = {"ok": True, "data": data, "rev": rev, "collected": collected, "char_id": cid}
        arena = self.char_match.get(cid)
        if arena is not None and arena.state != "ended":     # reconnect into a running match
            pid = next(p.pid for p in arena.players if p.char_id == cid)
            if not arena.players[pid].left:
                s.arena, s.pid = arena, pid
                arena.sessions[pid] = s
                arena.set_connected(pid, True)
                reply["rejoin"] = self._match_found_msg(arena, pid)
        self._broadcast_queue()
        return reply

    def h_save_char(self, s, msg):
        if s.arena is not None or s.char_id in self.char_match:
            raise ValidationError("You can't save during a match.")
        data = field(msg, "data", dict)
        rev = field(msg, "rev", int)
        ch = Character.from_dict(data)
        ch.check_progress_consistency()
        old, _, _ = self.db.load_character(s.account_id, s.char_id)
        if ch.class_def.name != old["class"] or ch.name != old["name"]:
            raise ValidationError("Class and name can't change.")
        # Stats, skills, bindings, equipment and profession change only through server actions
        # (spend_stat, buy_skill, equip...). A snapshot may not alter them.
        expect = Character.from_dict(old)
        expect.progression.level = ch.progression.level
        expect.grant_god_skills()
        if (ch.progression.allocated != expect.progression.allocated or ch.skills != expect.skills
                or ch.bindings != expect.bindings or ch.profession != expect.profession
                or ch.to_dict()["equipment"] != expect.to_dict()["equipment"]):
            raise ValidationError("Stats, skills, bindings and equipment can only be changed through the server.")
        clean = ch.to_dict()
        new_rev = self.db.save_character(s.account_id, s.char_id, clean, rev)
        return {"ok": True, "rev": new_rev}

    # ------------------------------------------------------------ marketplace
    def _char_reply(self, res, **extra):
        return dict({"ok": True, "data": res["data"], "rev": res["rev"]}, **extra)

    def h_market_browse(self, s, msg):
        return {"ok": True, "listings": self.db.active_listings(exclude_seller_id=s.char_id),
                "mine": self.db.seller_listings(s.char_id), "pending": self.db.pending_earnings(s.char_id),
                "fee": economy.MARKET_FEE_PERCENT}

    def h_market_list(self, s, msg):
        kind = field(msg, "kind", str, maxlen=10)
        name = field(msg, "name", str, maxlen=40)
        price = field(msg, "price", int, lo=1, hi=economy.MAX_PRICE)
        qty = field(msg, "qty", int, lo=1, hi=economy.MAX_QTY, default=1)
        idx = field(msg, "item_index", int, lo=0, hi=10_000, default=None)
        res = self.db.create_listing(s.account_id, s.char_id, kind, name, qty, price, idx)
        return self._char_reply(res, listing_id=res["listing_id"])

    def h_market_buy(self, s, msg):
        res = self.db.buy_listing(s.account_id, s.char_id, field(msg, "listing_id", int))
        lst = res["listing"]
        seller = next((x for x in self.sessions if x.char_id == lst["seller_id"]), None)
        if seller is not None:
            seller.send({"t": "sold", "name": lst["name"], "price": lst["price"],
                         "earned": lst["price"] - economy.market_fee(lst["price"])})
        return self._char_reply(res, bought=lst["name"], price=lst["price"])

    def h_market_cancel(self, s, msg):
        res = self.db.cancel_listing(s.account_id, s.char_id, field(msg, "listing_id", int))
        return self._char_reply(res)

    def h_vendor_sell(self, s, msg):
        idx = field(msg, "item_index", int, lo=0, hi=10_000)
        got = {}
        data, rev = self.db.update_character(s.account_id, s.char_id,
                                             lambda d: got.setdefault("p", economy.vendor_sell(d, idx)) and d)
        return {"ok": True, "data": data, "rev": rev, "price": got["p"]}

    def h_market_history(self, s, msg):
        return dict(self.db.market_history(s.char_id), ok=True)

    def h_shop_list(self, s, msg):
        vendor = field(msg, "vendor", str, maxlen=20)
        data, _, _ = self.db.load_character(s.account_id, s.char_id)
        try:
            return {"ok": True, "vendor": vendor, "catalog": economy.vendor_catalog(vendor, data["level"])}
        except economy.EconomyError as e:
            raise ValidationError(str(e)) from e

    def h_shop_buy(self, s, msg):
        vendor = field(msg, "vendor", str, maxlen=20)
        index = field(msg, "index", int)
        qty = field(msg, "qty", int, lo=1, hi=999, default=1)
        got = {}
        data, rev = self.db.update_character(
            s.account_id, s.char_id, lambda d: got.setdefault("c", economy.shop_buy(d, vendor, index, qty)) and d)
        return {"ok": True, "data": data, "rev": rev, "cost": got["c"]}

    # ------------------------------------------------------------ server-authoritative character actions
    def _char_op(self, s, fn):
        """Run fn(Character) inside one transaction on the server's copy of the character."""
        if s.arena is not None or s.char_id in self.char_match:
            raise ValidationError("Not during a match.")
        out = {}

        def mutate(data):
            ch = Character.from_dict(data)
            out["r"] = fn(ch)
            return ch.to_dict()
        data, rev = self.db.update_character(s.account_id, s.char_id, mutate)
        return {"ok": True, "data": data, "rev": rev, "result": out.get("r")}

    def h_spend_stat(self, s, msg):
        stat = field(msg, "stat", str, maxlen=16)
        amount = msg.get("amount")
        if amount != "max" and (not isinstance(amount, int) or isinstance(amount, bool) or amount < 1):
            raise ProtocolError("amount must be a positive integer or 'max'")

        def op(ch):
            n = ch.spend_points(stat, amount)
            if n == 0:
                raise ValidationError("No points could be spent on that stat.")
            return n
        return self._char_op(s, op)

    def h_buy_skill(self, s, msg):
        sid = field(msg, "skill_id", str, maxlen=40)

        def op(ch):
            if not ch.buy_skill(sid):
                raise ValidationError("You can't learn or upgrade that skill right now.")
        return self._char_op(s, op)

    def h_set_binding(self, s, msg):
        key = field(msg, "key", str, maxlen=2)
        sid = msg.get("skill_id")
        if sid is not None and (not isinstance(sid, str) or len(sid) > 40):
            raise ProtocolError("bad skill_id")

        def op(ch):
            if not ch.set_binding(key, sid):
                raise ValidationError("That skill can't be assigned to that key.")
        return self._char_op(s, op)

    def h_swap_bindings(self, s, msg):
        return self._char_op(s, lambda ch: ch.swap_bindings("j", "k"))

    def h_reset_bindings(self, s, msg):
        return self._char_op(s, lambda ch: ch.reset_bindings())

    def h_equip(self, s, msg):
        idx = field(msg, "item_index", int, lo=0, hi=10_000)

        def op(ch):
            if idx >= len(ch.inventory) or not ch.equip(ch.inventory[idx]):
                raise ValidationError("That item isn't in your bag.")
        return self._char_op(s, op)

    def h_unequip(self, s, msg):
        slot = field(msg, "slot", str, maxlen=12)

        def op(ch):
            if not ch.unequip(slot):
                raise ValidationError("Nothing equipped there.")
        return self._char_op(s, op)

    def h_choose_profession(self, s, msg):
        name = field(msg, "name", str, maxlen=20)

        def op(ch):
            if not ch.choose_profession(name):
                raise ValidationError("You can't choose a profession right now.")
        return self._char_op(s, op)

    # ------------------------------------------------------------ lobby / matchmaking
    def _counts(self):
        return {m: len(q) for m, q in self.queues.items()}

    def _leave_queue(self, s):
        if s.queue_mode:
            q = self.queues[s.queue_mode]
            if s in q:
                q.remove(s)
            s.queue_mode = None

    def _broadcast_queue(self):
        counts = self._counts()
        for s in self.sessions:
            if s.in_lobby:
                s.send({"t": "queue", "counts": counts, "you": s.queue_mode, "online": self._online()})

    def _online(self):
        return [{"name": x.char_name, "class": x.char_class, "level": x.char_level,
                 "mode": x.queue_mode, "busy": x.arena is not None}
                for x in self.sessions if x.char_id is not None][:40]

    def h_lobby_info(self, s, msg):
        return {"ok": True, "counts": self._counts(), "you": s.queue_mode, "online": self._online(),
                "modes": [{"mode": m, "label": M.mode_label(m), "need": M.players_needed(m, self.allow_small)}
                          for m in M.MODE_ORDER]}

    def h_queue_join(self, s, msg):
        mode = field(msg, "mode", str, maxlen=8)
        if mode not in M.MODE_ORDER:
            raise ValidationError("Unknown mode.")
        if s.arena is not None or s.char_id in self.char_match:
            raise ValidationError("You are already in a match.")
        self._leave_queue(s)
        self.queues[mode].append(s)
        s.queue_mode = mode
        self._try_start(mode)
        self._broadcast_queue()
        return {"ok": True, "counts": self._counts(), "you": s.queue_mode}

    def h_queue_leave(self, s, msg):
        self._leave_queue(s)
        self._broadcast_queue()
        return {"ok": True}

    def _try_start(self, mode):
        q = self.queues[mode]
        need = M.players_needed(mode, self.allow_small)
        if M.is_team_mode(mode):
            while len(q) >= need:                      # exactly the mode's team size, never fewer
                group, q[:] = q[:need], q[need:]
                self._start_match(mode, group)
            return
        top = M.max_players(mode)
        if len(q) >= top:
            group, q[:] = q[:top], q[top:]
            self._start_match(mode, group)
        elif len(q) >= need and mode not in self.flex_timers:
            self.flex_timers[mode] = asyncio.get_running_loop().call_later(
                M.FLEX_START_DELAY, lambda m=mode: self._flex_timeout(m))

    def _flex_timeout(self, mode):
        self.flex_timers.pop(mode, None)
        q = self.queues[mode]
        if len(q) >= M.players_needed(mode, self.allow_small):
            group, q[:] = q[:M.max_players(mode)], q[M.max_players(mode):]
            self._start_match(mode, group)
        self._try_start(mode)
        self._broadcast_queue()

    def _start_match(self, mode, group):
        entries, ok_sessions = [], []
        for s in group:
            s.queue_mode = None
            try:
                data, _, _ = self.db.load_character(s.account_id, s.char_id)
                entries.append({"char_id": s.char_id, "account_id": s.account_id, "name": data["name"],
                                "level": data["level"], "data": data})
                ok_sessions.append(s)
            except StorageError as e:
                s.send({"t": "error", "error": f"Could not load your character: {e}"})
        if len(ok_sessions) < (1 if (self.allow_small and mode == "coop") else 2):
            for s in ok_sessions:
                s.send({"t": "error", "error": "Match cancelled (not enough players)."})
            return
        arena = Arena(self.next_match_id, mode, entries)
        arena.sessions = {}
        self.next_match_id += 1
        for pid, s in enumerate(ok_sessions):
            s.arena, s.pid = arena, pid
            arena.sessions[pid] = s
            self.char_match[s.char_id] = arena
        for pid, s in enumerate(ok_sessions):
            s.send(self._match_found_msg(arena, pid))
        log.info("match %s started: %s with %d players", arena.match_id, mode, len(ok_sessions))
        task = asyncio.get_running_loop().create_task(self._run_match(arena))
        self.match_tasks.add(task)
        task.add_done_callback(self.match_tasks.discard)

    @staticmethod
    def _match_found_msg(arena, pid):
        return {"t": "match_found", "match_id": arena.match_id, "mode": arena.mode, "you": pid,
                "ruleset": arena.ruleset, "target": arena.target, "time_limit": M.TIME_LIMIT,
                "arena": {"width": ARENA_WIDTH, "ground_y": S.GROUND_Y, "platforms": [list(p) for p in PLATFORMS]},
                "players": [{"id": p.pid, "name": p.name, "team": p.team, "class": p.character.class_def.name,
                             "level": p.character.progression.level} for p in arena.players]}

    # ------------------------------------------------------------ in-match
    def h_input(self, s, msg):
        if s.arena is None:
            return None
        axis = field(msg, "axis", int, lo=-1, hi=1, default=0)
        acts = field(msg, "actions", list, maxlen=12, default=[])
        s.arena.set_input(s.pid, axis, [a for a in acts if isinstance(a, str)])
        return None

    def h_leave_match(self, s, msg):
        if s.arena is None:
            return {"ok": True}
        arena, pid = s.arena, s.pid
        arena.leave(pid)
        arena.sessions.pop(pid, None)
        s.arena = s.pid = None
        self.char_match.pop(s.char_id, None)
        self._broadcast_queue()
        return {"ok": True}

    async def _run_match(self, arena):
        loop = asyncio.get_running_loop()
        dt = 1.0 / TICK_RATE
        next_t = loop.time()
        try:
            while True:
                arena.step(dt)
                if arena.tick % SNAPSHOT_EVERY == 0 or arena.state == "ended":
                    snap = arena.snapshot()
                    for pid, s in list(arena.sessions.items()):
                        s.send(dict(snap, you=arena.you(pid)))
                if arena.state == "ended":
                    break
                next_t += dt
                await asyncio.sleep(max(0.0, next_t - loop.time()))
            self._finish_match(arena)
        except Exception:  # noqa: BLE001
            log.exception("match %s crashed", arena.match_id)
            self._abort(arena)

    def _abort(self, arena):
        for pid, s in list(arena.sessions.items()):
            s.send({"t": "error", "error": "The match ended unexpectedly."})
            s.arena = s.pid = None
        for p in arena.players:
            self.char_match.pop(p.char_id, None)
        self._broadcast_queue()

    def _reward(self, row):
        """Authoritative PvP rewards, scaled to the character's level."""
        def mutate(data):
            ch = Character.from_dict(data)
            lvl = ch.progression.level
            need = xp_to_next(lvl) or 1
            res = row["result"]
            xp = need // {"win": 4, "draw": 8, "loss": 10}[res] + row["kills"] * need // 40
            gold = ({"win": 60, "draw": 30, "loss": 20}[res] + 15 * row["kills"]) * (1 + lvl // 5)
            ch.add_xp(max(1, xp))
            ch.gold += gold
            row["xp"], row["gold"] = max(1, xp), gold
            return ch.to_dict()
        self.db.update_character(row["account_id"], row["char_id"], mutate)

    def _reward_coop(self, arena, row):
        ap = arena.players[row["pid"]]
        from client.items import item_from_dict

        def mutate(data):
            ch = Character.from_dict(data)
            bonus = 100 * (1 + ch.progression.level // 5) if row["result"] == "win" else 0
            ch.add_xp(ap.coop_xp)
            ch.gold += ap.coop_gold + bonus
            for it in ap.coop_loot[:20]:
                ch.inventory.append(item_from_dict(it))
            for m, q in ap.coop_mats.items():
                ch.materials[m] = ch.materials.get(m, 0) + q
            row["xp"], row["gold"], row["loot"] = ap.coop_xp, ap.coop_gold + bonus, len(ap.coop_loot)
            return ch.to_dict()
        self.db.update_character(row["account_id"], row["char_id"], mutate)

    def _finish_match(self, arena):
        res = arena.results()
        if not res["aborted"]:
            for row in res["players"]:
                if not row["left"]:
                    try:
                        (self._reward_coop(arena, row) if arena.mode == "coop" else self._reward(row))
                    except (StorageError, CharacterDataError) as e:
                        log.error("reward failed for %s: %s", row["name"], e)
        for p in arena.players:
            self.char_match.pop(p.char_id, None)
        for pid, s in list(arena.sessions.items()):
            payload = {"t": "match_end", "results": res}
            try:
                data, rev, _ = self.db.load_character(s.account_id, s.char_id)
                payload.update(data=data, rev=rev)
            except StorageError:
                pass
            s.send(payload)
            s.arena = s.pid = None
        log.info("match %s finished", arena.match_id)
        self._broadcast_queue()


# ---------------------------------------------------------------- embedding helpers
class ServerThread:
    """Run a GameServer on its own event loop in a background thread (tests, embedding)."""

    def __init__(self, db_path, host="127.0.0.1", port=0, **options):
        self.server = GameServer(db_path, host, port, **options)
        self.loop = asyncio.new_event_loop()
        self._started = threading.Event()
        self._error = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.server.start())
        except Exception as e:  # noqa: BLE001
            self._error = e
            self._started.set()
            return
        self._started.set()
        self.loop.run_forever()

    def start(self):
        self.thread.start()
        self._started.wait(10)
        if self._error:
            raise self._error
        return self.server.port

    def stop(self):
        if getattr(self, "_stopped", False):
            return
        self._stopped = True

        async def _shutdown():
            await self.server.stop()
        try:
            asyncio.run_coroutine_threadsafe(_shutdown(), self.loop).result(5)
        except Exception:  # noqa: BLE001
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
