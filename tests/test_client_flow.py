"""The Pygame client driven end-to-end against a real server: login, characters, stats,
skills, bindings, marketplace, vendors, solo endeavors and a live arena match."""
import random
import time

import pygame
import pytest

from client.character import Character
from client.classes import CLASS_ORDER
from client.game import Game
from client.items import make_item
from client.networking.client import NetClient
from client.ui.net_screens import (ArenaScreen, CharacterSelectScreen, ConnectScreen, LobbyScreen, LoginScreen,
                                   MarketScreen, NewCharacterScreen)
from client.ui.screens import (BindingsScreen, DungeonScreen, EquipmentScreen, HomeScreen, ProfessionScreen,
                               ResultsScreen, RunScreen, SkillsScreen, StatsScreen)
from helpers import account_id_of, grant, login_client, start_server, wait_for
from shared import modes as M


@pytest.fixture
def app(tmp_path):
    st, port = start_server(str(tmp_path / "app.db"))
    game = Game(rng=random.Random(1))
    yield game, st, port
    game.net.close()
    pygame.quit()
    st.stop()


def type_into(scene, field, text):
    for f in scene.fields:                      # a real click/Tab moves focus: only one field is focused
        f.focused = False
    scene.fields[field].focused = True
    for ch in text:
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=ord(ch.lower()) if ch.isalpha() else 0, unicode=ch))


def enter_game(game, port, user="alice", cls="Warrior", name="Hero One"):
    assert game.connect("127.0.0.1", port)[0]
    ok, msg = game.register(user, "secret1")
    assert ok, msg
    ok, msg = game.create_character(name, cls)
    assert ok, msg
    assert isinstance(game.scene, HomeScreen)
    return account_id_of_game(game)


def account_id_of_game(game):
    return game.account_id


def boost(game, st, fn):
    grant(st, game.account_id, game.character.id, fn)
    game.reload_character()


# ---------------------------------------------------------------- connect / login / characters
def test_connect_screen_to_login_with_typed_input(app):
    game, st, port = app
    assert isinstance(game.scene, ConnectScreen)
    game.scene.host.text, game.scene.port.text = "", ""
    type_into(game.scene, 0, "127.0.0.1")
    type_into(game.scene, 1, str(port))
    assert game.scene.host.text == "127.0.0.1" and game.scene.port.text == str(port)
    game.scene.click("Join Game")
    assert isinstance(game.scene, LoginScreen)
    type_into(game.scene, 0, "Alice_1")
    game.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, unicode="\t"))
    type_into(game.scene, 1, "secret1")
    assert game.scene.pw.focused and game.scene.user.text == "Alice_1" and game.scene.pw.text == "secret1"
    game.scene.click("Register")
    assert isinstance(game.scene, CharacterSelectScreen) and game.username == "Alice_1"


def test_bad_server_address_and_bad_credentials_show_errors(app):
    game, st, port = app
    game.scene.host.text, game.scene.port.text = "127.0.0.1", "1"
    game.scene.click("Join Game")
    assert isinstance(game.scene, ConnectScreen) and "Could not connect" in game.scene.msg
    game.connect("127.0.0.1", port)
    game.scene.user.text, game.scene.pw.text = "nobody", "wrongwrong"
    game.scene.click("Log In")
    assert "Wrong username or password" in game.scene.msg
    game.scene.user.text, game.scene.pw.text = "x", "y"
    game.scene.click("Register")
    assert "Username must be" in game.scene.msg
    game.scene.draw(game.screen)


def test_create_select_switch_and_delete_characters(app):
    game, st, port = app
    enter_game(game, port, name="First One")
    game.switch_character()
    assert isinstance(game.scene, CharacterSelectScreen) and len(game.scene.chars) == 1
    game.open_new_character()
    assert isinstance(game.scene, NewCharacterScreen)
    assert game.scene.buttons[0].enabled is False                        # must pick a class
    type_into(game.scene, 0, "Second Mage")
    game.scene.selected = CLASS_ORDER[2]
    game.scene._rebuild()
    game.scene.click("Create Mage")
    assert game.character.name == "Second Mage" and game.character.class_def.name == "Mage"
    boost(game, st, lambda ch: setattr(ch, "gold", 123))
    game.switch_character()
    first = next(c for c in game.scene.chars if c["name"] == "First One")
    game.play_character(first["id"])
    assert game.character.name == "First One" and game.character.gold == 0          # not overwritten
    game.switch_character()
    second = next(c for c in game.scene.chars if c["name"] == "Second Mage")
    game.play_character(second["id"])
    assert game.character.gold == 123
    game.switch_character()
    game.scene.ask(second["id"])
    assert any(b.label == "Really delete?" for b in game.scene.buttons)             # confirmation first
    assert len(game.scene.chars) == 2
    game.scene.delete(second["id"])
    assert [c["name"] for c in game.scene.chars] == ["First One"]
    game.scene.draw(game.screen)


def test_duplicate_character_name_and_slot_limit_are_reported(app):
    game, st, port = app
    enter_game(game, port, name="Dupe Name")
    ok, msg = game.create_character("dupe name", "Mage")
    assert not ok and "already have" in msg
    for i in range(5):
        assert game.create_character(f"Extra {i}", "Tank")[0]
    ok, msg = game.create_character("One Too Many", "Mage")
    assert not ok and "at most 6" in msg


# ---------------------------------------------------------------- home + every screen
def test_home_buttons_navigation_and_every_screen_draws(app):
    game, st, port = app
    enter_game(game, port)
    labels = {b.label for b in game.scene.buttons}
    assert {"Stats", "Skills", "Equipment", "Profession", "Marketplace", "Arena", "Go on Endeavor",
            "Dungeon Level", "Characters"} <= labels
    game.draw()
    for label, cls in (("Stats", StatsScreen), ("Skills", SkillsScreen), ("Equipment", EquipmentScreen),
                       ("Marketplace", MarketScreen), ("Dungeon Level", DungeonScreen), ("Arena", LobbyScreen)):
        assert game.scene.click(label), label
        assert isinstance(game.scene, cls)
        game.draw()
        game.scene.click("Back")
        assert isinstance(game.scene, HomeScreen)
    assert not game.scene.click("Profession")                                       # locked below level 10
    boost(game, st, lambda ch: ch.add_levels(9))
    game.go_home()
    game.scene.click("Profession")
    assert isinstance(game.scene, ProfessionScreen)
    game.scene.selected = "Smithing"
    game.scene.rebuild()
    game.scene.click("Learn Smithing")
    assert game.character.profession == "Smithing"
    game.draw()
    game.open(BindingsScreen)
    game.draw()


# ---------------------------------------------------------------- stats: +1 / +10 / +100 / +MAX
def test_stat_buttons_allocate_through_the_server(app):
    game, st, port = app
    enter_game(game, port)
    game.open(StatsScreen)
    assert not any(b.enabled for b in game.scene.buttons if hasattr(b, "tag"))      # no points yet
    boost(game, st, lambda ch: ch.add_levels(100))                                  # 300 points
    game.open(StatsScreen)
    by = {b.tag: b for b in game.scene.buttons if hasattr(b, "tag")}
    assert len(by) == 28 and all(b.enabled for b in by.values())
    for amt in (1, 10, 100):
        by[("strength", amt)].on_click()
        by = {b.tag: b for b in game.scene.buttons if hasattr(b, "tag")}
    ch = game.character
    assert ch.progression.allocated["strength"] == 111 and ch.progression.stat_points == 189
    by[("luck", "max")].on_click()
    assert game.character.progression.allocated["luck"] == 189 and game.character.progression.stat_points == 0
    assert not any(b.enabled for b in game.scene.buttons if hasattr(b, "tag"))      # nothing left to spend
    fresh = Character.from_dict(game.rpc("select_char", char_id=game.character.id)["data"])
    assert fresh.progression.allocated["strength"] == 111 and fresh.progression.allocated["luck"] == 189
    game.draw()


# ---------------------------------------------------------------- skills + J/K bindings
def test_skills_bindings_screens_change_and_persist_keybinds(app):
    game, st, port = app
    enter_game(game, port)
    boost(game, st, lambda ch: ch.add_levels(29))
    game.open(SkillsScreen)
    for sid in ("war_whirlwind", "war_battle_cry", "war_earthshatter", "war_iron_skin", "war_hardened"):
        assert game.scene.skill_buttons[sid].enabled and game.scene.skill_buttons[sid].label == "Learn (1)"
        game.scene.skill_buttons[sid].on_click()
    assert len(game.character.skills) == 5
    assert game.scene.skill_buttons["war_g_cleave"].label == "Locked"
    game.scene.click("Key Bindings (J / K)")
    assert isinstance(game.scene, BindingsScreen)
    game.scene.pick("j")
    assert game.scene.click("Earthshatter")
    assert game.character.bindings["j"] == "war_earthshatter" and game.character.bindings["3"] is None
    game.scene.pick("k")
    game.scene.click("Whirlwind")
    assert game.character.bindings["k"] == "war_whirlwind"
    game.scene.click("Swap J / K")
    assert game.character.bindings["j"] == "war_whirlwind" and game.character.bindings["k"] == "war_earthshatter"
    game.scene.pick("k")
    game.scene.click("Unequip this key")
    assert game.character.bindings["k"] is None and game.character.skill_rank("war_earthshatter") == 1
    game.draw()
    game.switch_character()
    game.play_character(game.scene.chars[0]["id"])                                   # reload from the server
    assert game.character.bindings["j"] == "war_whirlwind" and game.character.bindings["k"] is None
    game.open(BindingsScreen)
    game.scene.click("Restore Defaults")
    assert game.character.bindings["j"] == "basic_light" and game.character.bindings["k"] == "basic_heavy"


# ---------------------------------------------------------------- marketplace through the UI
def test_marketplace_search_filter_sort_buy_sell_and_history(app):
    game, st, port = app
    enter_game(game, port, "alice", "Mage", "Buyer Mage")
    seller, si = login_client(port, "seller1", "Warrior", "Seller One")
    grant(st, si["account_id"], si["char_id"], lambda ch: (
        ch.inventory.extend([make_item("Iron Sword", "Rare"), make_item("Leather Vest", "Epic"), make_item("Lucky Charm")]),
        ch.materials.update(Gem=20)))
    seller.request("select_char", char_id=si["char_id"])
    for idx, price in ((2, 90), (1, 500), (0, 300)):                                  # list from the back so indices stay valid
        assert seller.request("market_list", kind="item", name=["Iron Sword", "Leather Vest", "Lucky Charm"][idx],
                              price=price, item_index=idx)["ok"]
    assert seller.request("market_list", kind="material", name="Gem", qty=5, price=40)["ok"]
    boost(game, st, lambda ch: setattr(ch, "gold", 450))
    game.open(MarketScreen)
    ms = game.scene
    assert [l["name"] for l in ms.view()] == ["Gem", "Lucky Charm", "Iron Sword", "Leather Vest"]       # cheapest first
    ms.next_sort()
    assert [l["price"] for l in ms.view()] == [500, 300, 90, 40]
    ms.next_sort(); ms.next_sort()
    assert [l["name"] for l in ms.view()] == ["Gem", "Iron Sword", "Leather Vest", "Lucky Charm"]       # name A-Z
    ms.set_filter("item")
    assert {l["kind"] for l in ms.view()} == {"item"} and len(ms.view()) == 3
    ms.set_filter("material")
    assert [l["name"] for l in ms.view()] == ["Gem"]
    ms.set_filter(None)
    ms.search.text = "vest"
    assert [l["name"] for l in ms.view()] == ["Leather Vest"]
    ms.search.text = "seller"
    assert len(ms.view()) == 4                                                          # searches seller names too
    ms.search.text = ""
    ms.rebuild()
    game.draw()
    leather = next(b for b in ms.buttons if "Leather Vest" in b.label)
    assert leather.enabled is False and "not enough gold" in leather.sub                 # 500 > 450 gold
    sword = next(b for b in ms.buttons if "Iron Sword" in b.label)
    sword.on_click()
    assert game.scene.msg.startswith("Bought Iron Sword") and game.character.gold == 150
    assert [i.name for i in game.character.inventory] == ["Iron Sword"]
    # sell: list the sword back through the Sell tab
    ms = game.scene
    ms.set_tab("Sell")
    ms.pick(ms.sellable()[0])
    ms.price.text = "250"
    ms.do_list()
    assert game.character.inventory == [] and [l["price"] for l in ms.mine] == [250]
    ms.set_tab("My Listings")
    next(b for b in ms.buttons if "Iron Sword" in b.label).on_click()                      # cancel it
    assert [i.name for i in game.character.inventory] == ["Iron Sword"] and ms.mine == []
    ms.set_tab("History")
    assert [p["name"] for p in ms.history["purchases"]] == ["Iron Sword"]
    game.draw()
    # the seller's gold arrives (95% of 300) and shows up when they next load the character
    got = seller.request("collect")
    assert got["collected"] == 285


def test_npc_vendor_screen_confirms_before_buying(app):
    game, st, port = app
    enter_game(game, port)
    boost(game, st, lambda ch: setattr(ch, "gold", 2000))
    game.open(MarketScreen)
    ms = game.scene
    ms.set_tab("Vendor")
    assert len(ms.catalog) > 0 and ms.vendor == "Blacksmith"
    game.draw()
    entry_btn = next(b for b in ms.buttons if b.rect.x == 30 and b.rect.y == 176)
    entry_btn.on_click()
    assert ms.confirm is not None and game.character.gold == 2000                          # nothing bought yet
    game.draw()
    price = ms.confirm["price"]
    ms.click("Cancel")
    assert ms.confirm is None and game.character.gold == 2000 and game.character.inventory == []
    entry_btn = next(b for b in ms.buttons if b.rect.x == 30 and b.rect.y == 176)
    entry_btn.on_click()
    ms.click("Confirm Purchase")
    assert game.character.gold == 2000 - price and len(game.character.inventory) == 1
    ms.pick_vendor("Alchemist")
    assert {e["kind"] for e in ms.catalog} == {"potion"}
    for v in ("Armorer", "Jeweler", "General Store", "Rare Dealer"):
        ms.pick_vendor(v)
        game.draw()
    ms.pick_vendor("Blacksmith")
    sell_btn = next(b for b in ms.buttons if b.rect.x == 610 and b.rect.y == 176)
    before = game.character.gold
    sell_btn.on_click()
    assert game.character.inventory == [] and game.character.gold > before


# ---------------------------------------------------------------- saving, honestly
def test_failed_save_is_reported_never_hidden(app):
    game, st, port = app
    enter_game(game, port)
    assert game.autosave() is True and game.dirty is False
    game.character.progression.allocated["strength"] += 50                           # an illegal local change
    assert game.autosave() is False
    assert "SAVE FAILED" in game.notice[0] and game.dirty is True
    st.stop()                                                                         # server goes away
    assert game.autosave() is False and "SAVE FAILED" in game.notice[0]


def test_solo_endeavor_progress_is_saved_to_the_server(app):
    game, st, port = app
    enter_game(game, port)
    game.start_run()
    assert isinstance(game.scene, RunScreen)
    game.character.add_xp(250)                                                        # as if enemies were defeated
    game.character.gold += 77
    for _ in range(5):
        game.scene.update(1 / 60)
        game.draw()
    game.scene.run.retreat()
    game.scene.update(1 / 60)
    assert isinstance(game.scene, ResultsScreen)
    game.draw()
    saved = Character.from_dict(game.rpc("select_char", char_id=game.character.id)["data"])
    assert saved.progression.level == 3 and saved.gold == 77
    assert saved.progression.stat_points == 6 and saved.progression.skill_points == 2


def test_disconnect_returns_to_the_connect_screen_without_crashing(app):
    game, st, port = app
    enter_game(game, port)
    st.stop()
    for _ in range(100):
        game.pump(0.01)
        if isinstance(game.scene, ConnectScreen):
            break
        time.sleep(0.02)
    assert isinstance(game.scene, ConnectScreen) and "Disconnected" in game.scene.msg
    game.draw()


# ---------------------------------------------------------------- lobby and live arena
def test_lobby_queue_toggle_and_online_list(app):
    game, st, port = app
    enter_game(game, port)
    other, _ = login_client(port, "bobby", "Mage", "Other Mage")
    game.go_lobby()
    lob = game.scene
    assert isinstance(lob, LobbyScreen) and len(lob.buttons) == 1 + len(M.MODE_ORDER)
    assert {p["name"] for p in lob.online} == {"Hero One", "Other Mage"}
    lob.click("2v2")
    assert lob.you == "2v2" and lob.counts["2v2"] == 1
    assert other.request("lobby_info")["counts"]["2v2"] == 1
    lob.click("2v2")
    assert lob.you is None
    game.draw()


def test_a_real_match_runs_in_the_pygame_client_to_the_results_screen(app, monkeypatch):
    monkeypatch.setattr(M, "TIME_LIMIT", 2.5)
    monkeypatch.setattr(M, "COUNTDOWN", 0.3)
    game, st, port = app
    enter_game(game, port, "alice", "Warrior", "Gui Player")
    foe, fi = login_client(port, "bobby", "Mage", "Remote Foe")
    game.go_lobby()
    game.scene.click("1v1")
    foe.request("queue_join", mode="1v1")
    t0 = time.time()
    while not isinstance(game.scene, ArenaScreen) and time.time() - t0 < 5:
        game.pump(0.02)
        game.scene.update(0.02)
        time.sleep(0.02)
    arena = game.scene
    assert isinstance(arena, ArenaScreen) and arena.found["mode"] == "1v1"
    foe_snaps = 0
    t0 = time.time()
    while arena.end is None and time.time() - t0 < 12:
        arena.pending.add("light")
        foe.send("input", axis=-1, actions=["light"])
        game.pump(0.03)
        arena.update(0.03)
        game.draw()
        foe_snaps += sum(1 for m in foe.poll() if m["t"] == "snap")
        time.sleep(0.03)
    assert arena.latest is not None and foe_snaps > 10                                # both real clients got snapshots
    assert len(arena.latest["players"]) == 2
    assert arena.end is not None and arena.end["results"]["mode"] == "1v1"
    game.draw()
    assert game.character.gold > 0 and game.character.progression.xp > 0           # server rewards applied locally
    arena.buttons[1].on_click()                                                       # "Return to Lobby"
    assert isinstance(game.scene, LobbyScreen)
