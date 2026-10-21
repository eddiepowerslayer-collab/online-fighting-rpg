"""Real-network integration tests: a real GameServer on a TCP port and real NetClient
connections (separate sockets/threads). No fake players: every client is a real connection."""
import json
import socket
import threading
import time

import pytest

from client.character import Character
from client.networking.client import NetClient
from helpers import (account_id_of, drain, grant, login_client, start_server, wait_for)
from shared import modes as M
from shared.protocol import MAX_CLIENT_MSG


@pytest.fixture
def srv(tmp_path):
    st, port = start_server(str(tmp_path / "srv.db"))
    yield st, port
    st.stop()


def quick_modes(monkeypatch, time_limit=3.0):
    monkeypatch.setattr(M, "TIME_LIMIT", time_limit)
    monkeypatch.setattr(M, "COUNTDOWN", 0.3)
    monkeypatch.setattr(M, "FLEX_START_DELAY", 0.4)
    monkeypatch.setattr(M, "COOP_TIME_LIMIT", time_limit)


# ===================== 7. real clients connect to the same LAN server =====================
def test_two_real_clients_connect_and_see_each_other_in_the_lobby(srv):
    st, port = srv
    a, ia = login_client(port, "alice", "Warrior", "Alice Hero")
    b, ib = login_client(port, "bobby", "Mage", "Bobby Mage")
    for c in (a, b):
        r = c.request("lobby_info")
        names = {p["name"] for p in r["online"]}
        assert {"Alice Hero", "Bobby Mage"} <= names and r["ok"]
    assert a.sock.getsockname() != b.sock.getsockname()          # two genuinely separate connections
    for c in (a, b):
        c.close()


def test_one_live_session_per_account_newest_wins(srv):
    st, port = srv
    a, _ = login_client(port, "alice")
    b = NetClient()
    b.connect("127.0.0.1", port)
    assert b.request("login", username="alice", password="secret1")["ok"]
    kicked = wait_for(a, "kicked")
    assert kicked and "another location" in kicked["reason"]


# ===================== 1. multiple characters, independent =====================
def test_multiple_characters_are_created_and_saved_independently(srv):
    st, port = srv
    c, info = login_client(port, "alice", "Warrior", "Char One")
    ids = [info["char_id"]]
    for name, cls in (("Char Two", "Mage"), ("Char Three", "Tank")):
        r = c.request("create_char", name=name, **{"class": cls})
        assert r["ok"]
        ids.append(r["char_id"])
    acct = info["account_id"]
    grant(st, acct, ids[0], lambda ch: ch.add_levels(20))
    grant(st, acct, ids[1], lambda ch: setattr(ch, "gold", 4242))
    got = {}
    for cid in ids:
        got[cid] = Character.from_dict(c.request("select_char", char_id=cid)["data"])
    assert got[ids[0]].progression.level == 21 and got[ids[0]].gold == 0
    assert got[ids[1]].gold == 4242 and got[ids[1]].progression.level == 1 and got[ids[1]].class_def.name == "Mage"
    assert got[ids[2]].progression.level == 1 and got[ids[2]].gold == 0
    assert [x["name"] for x in c.request("list_chars")["characters"]] == ["Char One", "Char Two", "Char Three"]


def test_delete_character_removes_only_that_one(srv):
    st, port = srv
    c, info = login_client(port, "alice", name="Keep Me")
    other = c.request("create_char", name="Drop Me", **{"class": "Mage"})["char_id"]
    assert c.request("delete_char", char_id=other)["ok"]
    assert [x["name"] for x in c.request("list_chars")["characters"]] == ["Keep Me"]
    assert not c.request("select_char", char_id=other)["ok"]


# ===================== 2 + 13. persistence across a server restart =====================
def test_characters_and_marketplace_survive_a_server_restart(tmp_path):
    path = str(tmp_path / "restart.db")
    st, port = start_server(path)
    seller, si = login_client(port, "seller1", "Warrior", "Seller One")
    buyer, bi = login_client(port, "buyer01", "Mage", "Buyer One")
    grant(st, si["account_id"], si["char_id"], lambda ch: (ch.add_levels(15), ch.inventory.append(
        __import__("client.items", fromlist=["x"]).make_item("Iron Sword", "Rare")), ch.materials.update(Gem=9)))
    grant(st, bi["account_id"], bi["char_id"], lambda ch: setattr(ch, "gold", 900))
    seller.request("select_char", char_id=si["char_id"])
    assert seller.request("spend_stat", stat="strength", amount=10)["ok"]
    assert seller.request("buy_skill", skill_id="war_whirlwind")["ok"]
    assert seller.request("set_binding", key="j", skill_id="war_whirlwind")["ok"]
    r = seller.request("market_list", kind="item", name="Iron Sword", price=300, item_index=0)
    assert r["ok"]
    sold_id = r["listing_id"]
    assert seller.request("market_list", kind="material", name="Gem", qty=5, price=50)["ok"]
    buyer.request("select_char", char_id=bi["char_id"])
    assert buyer.request("market_buy", listing_id=sold_id)["ok"]
    for c in (seller, buyer):
        c.close()
    st.stop()                                                      # ----- server "crashes" / restarts -----

    st2, port2 = start_server(path)
    try:
        s2 = NetClient()
        s2.connect("127.0.0.1", port2)
        assert s2.request("login", username="seller1", password="secret1")["ok"]
        sel = s2.request("select_char", char_id=si["char_id"])
        ch = Character.from_dict(sel["data"])
        assert ch.progression.level == 16 and ch.progression.allocated["strength"] == 10
        assert ch.skill_rank("war_whirlwind") == 1 and ch.bindings["j"] == "war_whirlwind"
        assert sel["collected"] == 285 and ch.gold == 285            # 300 sale minus 5% fee, credited once
        mine = s2.request("market_browse")["mine"]
        assert [(l["name"], l["quantity"], l["price"]) for l in mine] == [("Gem", 5, 50)]
        b2 = NetClient()
        b2.connect("127.0.0.1", port2)
        b2.request("login", username="buyer01", password="secret1")
        bch = Character.from_dict(b2.request("select_char", char_id=bi["char_id"])["data"])
        assert bch.gold == 600 and [i.name for i in bch.inventory] == ["Iron Sword"]
        assert [l["name"] for l in b2.request("market_browse")["listings"]] == ["Gem"]
        assert b2.request("market_history")["purchases"][0]["name"] == "Iron Sword"
    finally:
        st2.stop()


# ===================== 3. +1 / +10 / +100 / +MAX through the server =====================
def test_stat_allocation_buttons_are_validated_and_saved_by_the_server(srv):
    st, port = srv
    c, info = login_client(port, "alice")
    grant(st, info["account_id"], info["char_id"], lambda ch: ch.add_levels(100))          # 300 points
    c.request("select_char", char_id=info["char_id"])
    spent = []
    for amount in (1, 10, 100):
        r = c.request("spend_stat", stat="dexterity", amount=amount)
        assert r["ok"]
        spent.append(r["result"])
    assert spent == [1, 10, 100]
    assert c.request("spend_stat", stat="luck", amount="max")["result"] == 189
    ch = Character.from_dict(c.request("select_char", char_id=info["char_id"])["data"])
    assert ch.progression.allocated["dexterity"] == 111 and ch.progression.allocated["luck"] == 189
    assert ch.progression.stat_points == 0
    assert not c.request("spend_stat", stat="luck", amount=1)["ok"]                      # nothing left
    # fewer points than asked: spends only what exists
    grant(st, info["account_id"], info["char_id"], lambda ch: ch.add_levels(2))          # +6 points
    c.request("select_char", char_id=info["char_id"])
    r = c.request("spend_stat", stat="agility", amount=100)
    assert r["ok"] and r["result"] == 6 and Character.from_dict(r["data"]).progression.stat_points == 0


# ===================== 4 + 5. skills (more than five) and J/K bindings =====================
def test_more_than_five_skills_and_jk_bindings_persist(srv):
    st, port = srv
    c, info = login_client(port, "alice", "Warrior")
    grant(st, info["account_id"], info["char_id"], lambda ch: ch.add_levels(29))
    c.request("select_char", char_id=info["char_id"])
    for sid in ("war_iron_skin", "war_whirlwind", "war_battle_cry", "war_hardened", "war_earthshatter"):
        assert c.request("buy_skill", skill_id=sid)["ok"], sid
    assert c.request("buy_skill", skill_id="war_whirlwind")["ok"]                          # upgrade
    grant(st, info["account_id"], info["char_id"], lambda ch: ch.add_levels(1000))       # god skill arrives
    ch = Character.from_dict(c.request("select_char", char_id=info["char_id"])["data"])
    assert len(ch.skills) == 6 and ch.skill_rank("war_whirlwind") == 2                    # > 5 skills kept
    assert c.request("set_binding", key="j", skill_id="war_earthshatter")["ok"]
    assert c.request("set_binding", key="k", skill_id="war_g_cleave")["ok"]
    assert not c.request("set_binding", key="k", skill_id="war_iron_skin")["ok"]          # passive: refused
    r = c.request("swap_bindings")
    b = Character.from_dict(r["data"]).bindings
    assert b["j"] == "war_g_cleave" and b["k"] == "war_earthshatter"
    c.close()
    c2 = NetClient()                                                                       # new connection: still saved
    c2.connect("127.0.0.1", port)
    c2.request("login", username="alice", password="secret1")
    ch2 = Character.from_dict(c2.request("select_char", char_id=info["char_id"])["data"])
    assert ch2.bindings["j"] == "war_g_cleave" and ch2.bindings["k"] == "war_earthshatter" and len(ch2.skills) == 6
    assert Character.from_dict(c2.request("reset_bindings")["data"]).bindings["j"] == "basic_light"


# ===================== 6. NPC purchases and sales =====================
def test_npc_vendor_trades_update_gold_and_inventory(srv):
    st, port = srv
    c, info = login_client(port, "alice")
    grant(st, info["account_id"], info["char_id"], lambda ch: setattr(ch, "gold", 5000))
    c.request("select_char", char_id=info["char_id"])
    cat = c.request("shop_list", vendor="Blacksmith")["catalog"]
    r = c.request("shop_buy", vendor="Blacksmith", index=0, qty=1)
    ch = Character.from_dict(r["data"])
    assert r["ok"] and ch.gold == 5000 - cat[0]["price"] and len(ch.inventory) == 1
    gold_before = ch.gold
    sell = c.request("vendor_sell", item_index=0)
    ch = Character.from_dict(sell["data"])
    assert sell["ok"] and ch.inventory == [] and ch.gold == gold_before + sell["price"] and sell["price"] < cat[0]["price"]
    idx = [e["name"] for e in c.request("shop_list", vendor="General Store")["catalog"]].index("Herb")
    r = c.request("shop_buy", vendor="General Store", index=idx, qty=4)
    assert Character.from_dict(r["data"]).materials["Herb"] == 4
    grant(st, info["account_id"], info["char_id"], lambda ch: setattr(ch, "gold", 3))
    c.request("select_char", char_id=info["char_id"])
    r = c.request("shop_buy", vendor="Rare Dealer", index=0, qty=1)
    assert not r["ok"] and "Not enough gold" in r["error"]


# ===================== 11 + 12. marketplace exactly-once and cancel =====================
def trading_pair(st, port, gold=1000):
    seller, si = login_client(port, "seller1", "Warrior", "Seller One")
    grant(st, si["account_id"], si["char_id"], lambda ch: ch.inventory.append(
        __import__("client.items", fromlist=["x"]).make_item("Iron Sword", "Rare")))
    seller.request("select_char", char_id=si["char_id"])
    return seller, si


def test_two_buyers_racing_for_one_listing_only_one_wins_and_money_moves_once(srv):
    st, port = srv
    seller, si = trading_pair(st, port)
    lid = seller.request("market_list", kind="item", name="Iron Sword", price=400, item_index=0)["listing_id"]
    buyers = []
    for i in range(2):
        b, bi = login_client(port, f"buyer0{i}", "Mage", f"Buyer {i}")
        grant(st, bi["account_id"], bi["char_id"], lambda ch: setattr(ch, "gold", 1000))
        b.request("select_char", char_id=bi["char_id"])
        buyers.append((b, bi))
    results, barrier = [None, None], threading.Barrier(2)

    def go(i):
        barrier.wait()
        results[i] = buyers[i][0].request("market_buy", listing_id=lid)
    threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r["ok"] for r in results) == [False, True]
    winner = next(i for i, r in enumerate(results) if r["ok"])
    wch = Character.from_dict(results[winner]["data"])
    assert wch.gold == 600 and [i.name for i in wch.inventory] == ["Iron Sword"]
    loser = 1 - winner
    lch = Character.from_dict(buyers[loser][0].request("select_char", char_id=buyers[loser][1]["char_id"])["data"])
    assert lch.gold == 1000 and lch.inventory == []                               # loser charged nothing
    sch = Character.from_dict(seller.request("select_char", char_id=si["char_id"])["data"])
    assert sch.gold == 380 and sch.inventory == []                                # credited exactly once
    total_swords = len(wch.inventory) + len(lch.inventory) + len(sch.inventory)
    assert total_swords == 1                                                      # no duplication
    assert not buyers[winner][0].request("market_buy", listing_id=lid)["ok"]    # can't buy it again


def test_cancelled_listing_returns_the_item_and_cannot_be_bought(srv):
    st, port = srv
    seller, si = trading_pair(st, port)
    lid = seller.request("market_list", kind="item", name="Iron Sword", price=400, item_index=0)["listing_id"]
    browse = seller.request("market_browse")
    assert [l["id"] for l in browse["mine"]] == [lid] and browse["listings"] == []   # hidden from own browse
    assert Character.from_dict(seller.request("select_char", char_id=si["char_id"])["data"]).inventory == []
    back = seller.request("market_cancel", listing_id=lid)
    assert back["ok"] and [i["name"] for i in back["data"]["inventory"]] == ["Iron Sword"]
    assert not seller.request("market_cancel", listing_id=lid)["ok"]               # no second return
    b, bi = login_client(port, "buyer00", "Mage")
    grant(st, bi["account_id"], bi["char_id"], lambda ch: setattr(ch, "gold", 999))
    b.request("select_char", char_id=bi["char_id"])
    assert not b.request("market_buy", listing_id=lid)["ok"]


def test_listed_item_cannot_be_sold_listed_or_equipped_twice(srv):
    st, port = srv
    seller, si = trading_pair(st, port)
    assert seller.request("market_list", kind="item", name="Iron Sword", price=10, item_index=0)["ok"]
    assert not seller.request("market_list", kind="item", name="Iron Sword", price=10, item_index=0)["ok"]
    assert not seller.request("equip", item_index=0)["ok"]
    assert not seller.request("vendor_sell", item_index=0)["ok"]


def test_seller_is_told_about_the_sale_live(srv):
    st, port = srv
    seller, si = trading_pair(st, port)
    lid = seller.request("market_list", kind="item", name="Iron Sword", price=200, item_index=0)["listing_id"]
    b, bi = login_client(port, "buyer00", "Mage")
    grant(st, bi["account_id"], bi["char_id"], lambda ch: setattr(ch, "gold", 500))
    b.request("select_char", char_id=bi["char_id"])
    assert b.request("market_buy", listing_id=lid)["ok"]
    sold = wait_for(seller, "sold")
    assert sold and sold["price"] == 200 and sold["earned"] == 190
    got = seller.request("collect")
    assert got["collected"] == 190 and Character.from_dict(got["data"]).gold == 190


# ===================== 8. every PvP mode enforces its team size =====================
@pytest.mark.parametrize("mode,size", [("1v1", 1), ("2v2", 2), ("3v3", 3), ("4v4", 4), ("5v5", 5)])
def test_team_mode_waits_for_exact_player_count_then_makes_equal_teams(srv, monkeypatch, mode, size):
    quick_modes(monkeypatch, 30)
    st, port = srv
    need = 2 * size
    clients = [login_client(port, f"user{i:02d}", ["Warrior", "Mage", "Tank", "Archer", "Assassin"][i % 5])[0]
               for i in range(need)]
    for c in clients[:-1]:
        assert c.request("queue_join", mode=mode)["ok"]
    got = drain(clients, 0.5)
    assert not any(m["t"] == "match_found" for msgs in got.values() for m in msgs)    # not started: one short
    counts = clients[0].request("lobby_info")["counts"]
    assert counts[mode] == need - 1
    assert clients[-1].request("queue_join", mode=mode)["ok"]
    found = [wait_for(c, "match_found") for c in clients]
    assert all(found)
    teams = [p["team"] for p in found[0]["players"]]
    assert len(teams) == need and teams.count(0) == teams.count(1) == size
    assert {f["you"] for f in found} == set(range(need)) and len({f["match_id"] for f in found}) == 1
    for c in clients:
        c.send("input", axis=0, actions=[])
        c.request("leave_match")


def test_extra_players_beyond_the_mode_size_wait_for_the_next_match(srv, monkeypatch):
    quick_modes(monkeypatch, 30)
    st, port = srv
    clients = [login_client(port, f"user{i:02d}")[0] for i in range(3)]
    for c in clients:
        c.request("queue_join", mode="1v1")
    started = [wait_for(c, "match_found", 1.0) for c in clients]
    assert sum(1 for s in started if s) == 2 and started.count(None) == 1       # exactly two in a 1v1
    assert clients[0].request("lobby_info")["counts"]["1v1"] == 1


# ===================== 9. free-for-all has no teams =====================
def test_free_for_all_starts_with_two_or_more_and_has_no_teams(srv, monkeypatch):
    quick_modes(monkeypatch, 30)
    st, port = srv
    clients = [login_client(port, f"user{i:02d}")[0] for i in range(3)]
    for c in clients:
        assert c.request("queue_join", mode="ffa")["ok"]
    found = [wait_for(c, "match_found", 3.0) for c in clients]
    assert all(found) and found[0]["mode"] == "ffa"
    assert len({p["team"] for p in found[0]["players"]}) == 3                    # every player alone
    snaps = [wait_for(c, "snap") for c in clients]
    assert all(s["state"] in ("countdown", "active") for s in snaps)
    assert snaps[0]["ts"] == [0, 0]


def test_a_lone_player_is_not_matched_in_free_for_all(srv, monkeypatch):
    quick_modes(monkeypatch, 30)
    st, port = srv
    c, _ = login_client(port, "alice")
    c.request("queue_join", mode="ffa")
    assert wait_for(c, "match_found", 1.2) is None


# ===================== 10. cooperative PvE with shared enemies =====================
def test_cooperative_players_fight_the_same_enemies(srv, monkeypatch):
    quick_modes(monkeypatch, 6)
    st, port = srv
    a, _ = login_client(port, "alice", "Warrior", "Alice Hero")
    b, _ = login_client(port, "bobby", "Warrior", "Bobby Hero")
    for c in (a, b):
        assert c.request("queue_join", mode="coop")["ok"]
    fa, fb = wait_for(a, "match_found", 3.0), wait_for(b, "match_found", 3.0)
    assert fa and fb and fa["mode"] == "coop" and fa["match_id"] == fb["match_id"]
    seen = {id(a): [], id(b): []}
    end = {}
    t0 = time.time()
    while time.time() - t0 < 12 and len(end) < 2:
        for c in (a, b):
            c.send("input", axis=1, actions=["light", "heavy", "skill1"])
            for m in c.poll():
                if m["t"] == "snap":
                    seen[id(c)].append(m)
                elif m["t"] == "match_end":
                    end[id(c)] = m
        time.sleep(0.03)
    sa, sb = seen[id(a)], seen[id(b)]
    assert sa and sb and all(len(s["en"]) == 8 for s in sa[:3] + sb[:3])
    assert {e[0] for e in sa[0]["en"]} == {e[0] for e in sb[0]["en"]}              # the very same enemies
    common = {s["tick"]: s for s in sa}
    ticks = [s for s in sb if s["tick"] in common]
    assert ticks and all(common[s["tick"]]["en"] == s["en"] for s in ticks)         # identical shared state
    damaged = {e[0] for s in sa for e in s["en"] if e[4] < e[5]}
    assert damaged, "players never hurt a shared enemy"
    assert len(end) == 2
    res = next(iter(end.values()))["results"]
    assert res["mode"] == "coop" and len(res["players"]) == 2 and all("xp" in p for p in res["players"])


# ===================== match results, rewards, reconnect =====================
def test_match_end_rewards_are_applied_by_the_server_and_saved(srv, monkeypatch):
    quick_modes(monkeypatch, 2.0)
    st, port = srv
    a, ia = login_client(port, "alice", "Warrior", "Alice Hero")
    b, ib = login_client(port, "bobby", "Mage", "Bobby Hero")
    for c in (a, b):
        c.request("queue_join", mode="1v1")
    ends = [wait_for(c, "match_end", 10.0) for c in (a, b)]
    assert all(ends)
    for end, c, info in zip(ends, (a, b), (ia, ib)):
        mine = next(p for p in end["results"]["players"] if p["char_id"] == info["char_id"])
        assert mine["result"] == "draw" and mine["xp"] > 0 and mine["gold"] > 0
        ch = Character.from_dict(end["data"])
        assert ch.gold == mine["gold"] and ch.progression.xp == mine["xp"]
        fresh = Character.from_dict(c.request("select_char", char_id=info["char_id"])["data"])
        assert fresh.gold == ch.gold                                                # saved in the database
    # the match is over: the lobby works again
    assert a.request("queue_join", mode="1v1")["ok"]


def test_a_dropped_client_can_reconnect_into_the_running_match(srv, monkeypatch):
    quick_modes(monkeypatch, 30)
    st, port = srv
    a, ia = login_client(port, "alice", "Warrior", "Alice Hero")
    b, ib = login_client(port, "bobby", "Mage", "Bobby Hero")
    for c in (a, b):
        c.request("queue_join", mode="1v1")
    found = wait_for(a, "match_found")
    wait_for(b, "match_found")
    a.close()                                                   # a's network drops
    time.sleep(0.4)
    a2 = NetClient()
    a2.connect("127.0.0.1", port)
    assert a2.request("login", username="alice", password="secret1")["ok"]
    sel = a2.request("select_char", char_id=ia["char_id"])
    assert sel["ok"] and sel["rejoin"]["match_id"] == found["match_id"] and sel["rejoin"]["you"] == found["you"]
    snap = wait_for(a2, "snap")
    assert snap and snap["players"][found["you"]]["dc"] == 0
    assert not a2.request("save_char", data=sel["data"], rev=sel["rev"])["ok"]        # no saving mid-match


def test_leaving_early_forfeits_rewards_and_other_player_wins(srv, monkeypatch):
    quick_modes(monkeypatch, 30)
    st, port = srv
    a, ia = login_client(port, "alice")
    b, ib = login_client(port, "bobby")
    for c in (a, b):
        c.request("queue_join", mode="1v1")
    wait_for(a, "match_found")
    wait_for(b, "match_found")
    time.sleep(0.5)
    assert a.request("leave_match")["ok"]
    end = wait_for(b, "match_end", 5.0)
    rows = {p["name"]: p for p in end["results"]["players"]}
    assert rows["bobby_hero"]["result"] == "win" and rows["bobby_hero"]["xp"] > 0
    assert rows["alice_hero"]["left"] and "xp" not in rows["alice_hero"]


# ===================== testing option for smaller matches =====================
def test_small_match_option_is_off_by_default_and_works_when_enabled(tmp_path, monkeypatch):
    quick_modes(monkeypatch, 30)
    st, port = start_server(str(tmp_path / "small.db"), allow_small=True)
    try:
        a, _ = login_client(port, "alice")
        b, _ = login_client(port, "bobby")
        for c in (a, b):
            c.request("queue_join", mode="5v5")
        found = wait_for(a, "match_found", 2.0)
        assert found and len(found["players"]) == 2                                  # testing option: 1 per team
        assert {p["team"] for p in found["players"]} == {0, 1}
        solo, _ = login_client(port, "carol")
        solo.request("queue_join", mode="coop")
        assert wait_for(solo, "match_found", 2.0)["mode"] == "coop"
    finally:
        st.stop()
    st2, port2 = start_server(str(tmp_path / "strict.db"))
    try:
        a, _ = login_client(port2, "alice")
        b, _ = login_client(port2, "bobby")
        for c in (a, b):
            c.request("queue_join", mode="5v5")
        assert wait_for(a, "match_found", 1.0) is None
    finally:
        st2.stop()


# ===================== 14. invalid requests cannot create gold, items, XP or stats =====================
def raw_lines(port, payloads, read=True, timeout=2.0):
    s = socket.create_connection(("127.0.0.1", port), timeout)
    s.settimeout(timeout)
    out = []
    for p in payloads:
        s.sendall(p if isinstance(p, bytes) else (json.dumps(p) + "\n").encode())
    buf = b""
    try:
        while read:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            if buf.count(b"\n") >= len(payloads):
                break
    except socket.timeout:
        pass
    s.close()
    return [json.loads(x) for x in buf.split(b"\n") if x]


def snapshot_of(c, info):
    d = c.request("select_char", char_id=info["char_id"])["data"]
    return json.dumps(d, sort_keys=True)


def test_unauthenticated_and_malformed_requests_are_refused(srv):
    st, port = srv
    out = raw_lines(port, [{"t": "list_chars", "id": 1}, {"t": "hello", "v": 1, "id": 2},
                           {"t": "list_chars", "id": 3}, {"t": "market_list", "id": 4, "kind": "item"},
                           {"t": "hello", "v": 99, "id": 5}, b"{not json}\n", {"t": "bogus", "id": 6}])
    by_id = {m.get("re"): m for m in out}
    assert not by_id[1]["ok"] and "hello" in by_id[1]["error"]
    assert by_id[2]["ok"]
    assert not by_id[3]["ok"] and "log in" in by_id[3]["error"]
    assert not by_id[4]["ok"] and not by_id[5]["ok"] and not by_id[6]["ok"]


def test_oversized_message_is_rejected_and_the_server_survives(srv):
    st, port = srv
    s = socket.create_connection(("127.0.0.1", port), 3)
    s.settimeout(3)
    try:
        s.sendall(b'{"t":"hello","v":1,"pad":"' + b"x" * (MAX_CLIENT_MSG + 5000) + b'"}\n')
    except OSError:
        pass
    data = b""
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    except (socket.timeout, OSError):
        pass
    s.close()
    assert b"too large" in data or data == b""                    # error sent or connection dropped
    c, _ = login_client(port, "alice")                              # server is still healthy
    assert c.request("lobby_info")["ok"]


def test_flooding_the_server_does_not_break_it(srv):
    st, port = srv
    s = socket.create_connection(("127.0.0.1", port), 3)
    s.sendall((json.dumps({"t": "hello", "v": 1}) + "\n").encode())
    try:
        s.sendall(((json.dumps({"t": "ping"}) + "\n") * 5000).encode())
    except OSError:
        pass
    s.close()
    c, _ = login_client(port, "alice")
    assert c.request("lobby_info")["ok"]


def test_login_throttle_and_wrong_password(srv):
    st, port = srv
    c, _ = login_client(port, "alice")
    d = NetClient()
    d.connect("127.0.0.1", port)
    t0 = time.time()
    for _ in range(3):
        r = d.request("login", username="alice", password="wrongwrong")
        assert not r["ok"] and r["error"] == "Wrong username or password."
    assert time.time() - t0 > 0.5                                    # failures are slowed down


def test_forged_market_and_shop_requests_never_create_or_destroy_value(srv):
    st, port = srv
    seller, si = trading_pair(st, port)
    grant(st, si["account_id"], si["char_id"], lambda ch: (setattr(ch, "gold", 50), ch.materials.update(Gem=3)))
    seller.request("select_char", char_id=si["char_id"])
    before = snapshot_of(seller, si)
    bad = [("market_list", dict(kind="item", name="Iron Sword", price=-100, item_index=0)),
           ("market_list", dict(kind="item", name="Iron Sword", price=0, item_index=0)),
           ("market_list", dict(kind="item", name="Iron Sword", price=1.5, item_index=0)),
           ("market_list", dict(kind="item", name="Iron Sword", price="10", item_index=0)),
           ("market_list", dict(kind="item", name="Iron Sword", price=10 ** 12, item_index=0)),
           ("market_list", dict(kind="item", name="Iron Sword", price=10, item_index=5)),
           ("market_list", dict(kind="item", name="Iron Sword", price=10, item_index=-1)),
           ("market_list", dict(kind="item", name="Diamond Sword", price=10, item_index=0)),
           ("market_list", dict(kind="material", name="Gem", qty=-5, price=10)),
           ("market_list", dict(kind="material", name="Gem", qty=0, price=10)),
           ("market_list", dict(kind="material", name="Gem", qty=4, price=10)),
           ("market_list", dict(kind="material", name="Gem", qty=10 ** 6, price=10)),
           ("market_list", dict(kind="gold", name="Gem", qty=1, price=10)),
           ("market_list", dict(kind="potion", name="Elixir of Doom", qty=1, price=10)),
           ("market_buy", dict(listing_id=99999)), ("market_buy", dict(listing_id=-1)), ("market_buy", dict(listing_id="1")),
           ("market_cancel", dict(listing_id=99999)),
           ("vendor_sell", dict(item_index=9)), ("vendor_sell", dict(item_index=-1)), ("vendor_sell", dict(item_index="0")),
           ("shop_buy", dict(vendor="Rare Dealer", index=0, qty=1)),                     # can't afford (50 gold)
           ("shop_buy", dict(vendor="General Store", index=0, qty=-10)),
           ("shop_buy", dict(vendor="General Store", index=0, qty=0)),
           ("shop_buy", dict(vendor="General Store", index=0, qty=100000)),
           ("shop_buy", dict(vendor="General Store", index=77, qty=1)),
           ("shop_buy", dict(vendor="Nobody", index=0, qty=1)),
           ("shop_buy", dict(vendor="Blacksmith", index=0, qty=1, price=1)),             # a client-supplied price is ignored
           ]
    for t, fields in bad:
        r = seller.request(t, **fields)
        if t == "shop_buy" and fields.get("price") == 1:
            assert not r["ok"]                                                          # 50 gold < real price
        else:
            assert not r["ok"], (t, fields, r)
    assert snapshot_of(seller, si) == before                                             # nothing changed at all
    assert seller.request("market_browse")["mine"] == []


def test_cannot_buy_with_insufficient_gold_or_own_listing(srv):
    st, port = srv
    seller, si = trading_pair(st, port)
    lid = seller.request("market_list", kind="item", name="Iron Sword", price=400, item_index=0)["listing_id"]
    assert "own listing" in seller.request("market_buy", listing_id=lid)["error"]
    poor, pi = login_client(port, "pauper1", "Mage")
    r = poor.request("market_buy", listing_id=lid)
    assert not r["ok"] and "Not enough gold" in r["error"]
    assert Character.from_dict(poor.request("select_char", char_id=pi["char_id"])["data"]).gold == 0
    assert [l["id"] for l in seller.request("market_browse")["mine"]] == [lid]            # still listed


def test_forged_stat_skill_binding_and_equipment_requests_are_refused(srv):
    st, port = srv
    c, info = login_client(port, "alice", "Warrior")
    before = snapshot_of(c, info)
    bad = [("spend_stat", dict(stat="strength", amount=1)),                        # no points yet
           ("spend_stat", dict(stat="strength", amount=-5)), ("spend_stat", dict(stat="strength", amount=0)),
           ("spend_stat", dict(stat="strength", amount="MAX")), ("spend_stat", dict(stat="strength", amount=1.5)),
           ("spend_stat", dict(stat="strength", amount=True)), ("spend_stat", dict(stat="hax", amount=1)),
           ("spend_stat", dict(stat="strength")), ("spend_stat", dict(amount=1)),
           ("buy_skill", dict(skill_id="war_whirlwind")),                           # no skill points
           ("buy_skill", dict(skill_id="mag_fireball")), ("buy_skill", dict(skill_id="war_g_cleave")),
           ("buy_skill", dict(skill_id="nope")), ("buy_skill", dict(skill_id=5)),
           ("set_binding", dict(key="j", skill_id="war_whirlwind")),                # not unlocked
           ("set_binding", dict(key="x", skill_id="basic_light")), ("set_binding", dict(key="j", skill_id="mag_fireball")),
           ("equip", dict(item_index=0)), ("equip", dict(item_index=-1)), ("unequip", dict(slot="armor")),
           ("unequip", dict(slot="head")), ("choose_profession", dict(name="Smithing")),    # below level 10
           ("choose_profession", dict(name="Wizardry")), ("queue_join", dict(mode="9v9")), ("queue_join", dict(mode=5))]
    for t, fields in bad:
        assert not c.request(t, **fields)["ok"], (t, fields)
    assert snapshot_of(c, info) == before


def test_tampered_save_snapshots_are_rejected(srv):
    st, port = srv
    c, info = login_client(port, "alice", "Warrior")
    grant(st, info["account_id"], info["char_id"], lambda ch: ch.add_levels(20))
    sel = c.request("select_char", char_id=info["char_id"])
    good, rev = sel["data"], sel["rev"]

    def mutated(**changes):
        d = json.loads(json.dumps(good))
        for k, v in changes.items():
            if k == "allocated":
                d["allocated"].update(v)
            else:
                d[k] = v
        return d
    forged = {
        "extra stat points": mutated(allocated={"strength": 500}),
        "more stat points owed": mutated(stat_points=10 ** 6),
        "fake level up": mutated(level=400),
        "negative gold": mutated(gold=-5),
        "xp beyond the level": mutated(xp=10 ** 12),
        "unlocked skills": mutated(skills={"war_whirlwind": 5, "war_iron_skin": 5}),
        "god skill": mutated(skills={"war_g_cleave": 1}),
        "changed bindings": mutated(bindings=dict(good["bindings"], j="war_whirlwind")),
        "changed class": mutated(**{"class": "Mage"}),
        "changed name": mutated(name="Hacker"),
        "forged equipment": mutated(equipment={"weapon": {"name": "God Blade", "slot": "weapon", "rarity": "Epic",
                                                          "bonuses": [["strength", 10 ** 8]], "grade": "God"}}),
        "bogus item rarity": mutated(inventory=[{"name": "X", "slot": "weapon", "rarity": "Mythic", "bonuses": [], "grade": "F"}]),
        "wrong types": mutated(level="999", gold=1.5),
        "bad profession": mutated(profession="Wizardry"),
    }
    for label, data in forged.items():
        r = c.request("save_char", data=data, rev=rev)
        assert not r["ok"], label
    assert not c.request("save_char", data=good, rev=rev - 1)["ok"]                      # stale revision
    assert not c.request("save_char", data="not a dict", rev=rev)["ok"]
    assert c.request("save_char", data=good, rev=rev)["ok"]                               # an honest save still works
    after = Character.from_dict(c.request("select_char", char_id=info["char_id"])["data"])
    assert after.progression.level == 21 and after.progression.allocated["strength"] == 0
    assert after.skills == {} and after.gold == 0


def test_players_cannot_touch_other_players_characters(srv):
    st, port = srv
    a, ia = login_client(port, "alice")
    b, ib = login_client(port, "bobby")
    assert not b.request("select_char", char_id=ia["char_id"])["ok"]
    assert not b.request("delete_char", char_id=ia["char_id"])["ok"]
    assert a.request("list_chars")["characters"][0]["id"] == ia["char_id"]
