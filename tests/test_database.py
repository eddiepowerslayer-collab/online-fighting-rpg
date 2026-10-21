"""Persistence layer: accounts, independent characters, restart survival, atomic marketplace."""
import json
import sqlite3

import pytest

from client.character import Character
from client.classes import MAGE, WARRIOR
from client.items import item_to_dict, make_item
from shared import economy
from storage.database import (Database, StorageError, ValidationError, hash_password, verify_password)


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "g.db"))
    yield d
    d.close()


def new_char(db, account, name, cls=WARRIOR, **edit):
    ch = Character(cls, name)
    for k, v in edit.items():
        setattr(ch, k, v)
    return db.create_character(account, name, ch.to_dict())


def give_item(db, acct, cid, item=None):
    item = item or make_item("Iron Sword", "Rare")
    db.update_character(acct, cid, lambda d: d["inventory"].append(item_to_dict(item)))


# ---------- accounts ----------
def test_passwords_are_hashed_salted_and_verified():
    h1, h2 = hash_password("hunter22"), hash_password("hunter22")
    assert "hunter22" not in h1 and h1 != h2            # salted, never plain text
    assert verify_password("hunter22", h1) and not verify_password("hunter23", h1)
    assert not verify_password("x", "garbage") and not verify_password("x", "scrypt$1$2")


def test_register_login_and_validation(db):
    a = db.create_account("Alice_1", "secret1")
    assert db.authenticate("alice_1", "secret1") == a               # usernames are case-insensitive
    assert db.authenticate("alice_1", "wrong") is None and db.authenticate("ghost", "secret1") is None
    for bad in ("ab", "has space", "x" * 21, "semi;colon", "o'brien"):
        with pytest.raises(ValidationError):
            db.create_account(bad, "secret1")
    with pytest.raises(ValidationError):
        db.create_account("short_pw", "123")
    with pytest.raises(ValidationError):
        db.create_account("ALICE_1", "secret1")                      # duplicate
    raw = db.conn.execute("SELECT password_hash FROM accounts").fetchone()[0]
    assert "secret1" not in raw


def test_sql_injection_strings_are_just_data(db):
    db.create_account("bob", "secret1")
    assert db.authenticate("bob' OR '1'='1", "x") is None
    assert db.authenticate("bob", "' OR '1'='1") is None
    assert db.conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


# ---------- multiple characters ----------
def test_multiple_characters_are_independent(db):
    a = db.create_account("alice", "secret1")
    c1, c2 = new_char(db, a, "Hero One"), new_char(db, a, "Mage Two", MAGE)
    db.update_character(a, c1, lambda d: d.update(gold=500))
    chars = db.list_characters(a)
    assert [c["name"] for c in chars] == ["Hero One", "Mage Two"]
    d1, _, _ = db.load_character(a, c1)
    d2, _, _ = db.load_character(a, c2)
    assert d1["gold"] == 500 and d2["gold"] == 0 and d2["class"] == "Mage"
    with pytest.raises(ValidationError):
        new_char(db, a, "hero one")                                  # unique name per account


def test_character_limit_and_ownership(db):
    a, b = db.create_account("alice", "secret1"), db.create_account("bobby", "secret1")
    ids = [new_char(db, a, f"Char {i}") for i in range(6)]
    with pytest.raises(ValidationError):
        new_char(db, a, "Seventh")
    with pytest.raises(ValidationError):
        db.load_character(b, ids[0])                                 # can't load someone else's
    with pytest.raises(ValidationError):
        db.delete_character(b, ids[0])
    db.delete_character(a, ids[0])
    assert len(db.list_characters(a)) == 5
    new_char(db, a, "Seventh")


def test_character_progress_survives_closing_and_reopening(tmp_path):
    path = str(tmp_path / "persist.db")
    db = Database(path)
    a = db.create_account("alice", "secret1")
    cid = new_char(db, a, "Keeper")

    def progress(d):
        ch = Character.from_dict(d)
        ch.add_levels(30)
        ch.spend_points("luck", 40)
        ch.buy_skill("war_whirlwind")
        ch.buy_skill("war_iron_skin")
        ch.set_binding("j", "war_whirlwind")
        ch.gold = 777
        ch.inventory.append(make_item("Hunting Bow", "Epic"))
        ch.equip(ch.inventory[0])
        return ch.to_dict()
    db.update_character(a, cid, progress)
    db.close()
    db2 = Database(path)                                              # "restart"
    assert db2.authenticate("alice", "secret1") == a
    data, rev, _ = db2.load_character(a, cid)
    ch = Character.from_dict(data)
    assert (ch.progression.level, ch.gold, ch.progression.allocated["luck"]) == (31, 777, 40)
    assert ch.skill_rank("war_whirlwind") == 1 and ch.bindings["j"] == "war_whirlwind"
    assert ch.equipment["weapon"].name == "Hunting Bow"


def test_database_errors_are_raised_never_swallowed(tmp_path):
    db = Database(str(tmp_path / "x.db"))
    a = db.create_account("alice", "secret1")
    cid = new_char(db, a, "Hero")
    data, rev, _ = db.load_character(a, cid)
    db.close()
    with pytest.raises(StorageError):
        db.save_character(a, cid, data, rev)


def test_stale_revision_is_rejected(db):
    a = db.create_account("alice", "secret1")
    cid = new_char(db, a, "Hero")
    data, rev, _ = db.load_character(a, cid)
    assert db.save_character(a, cid, data, rev) == rev + 1
    with pytest.raises(ValidationError, match="stale"):
        db.save_character(a, cid, data, rev)


# ---------- marketplace ----------
def setup_market(db):
    a, b = db.create_account("seller", "secret1"), db.create_account("buyer", "secret1")
    s, t = new_char(db, a, "Sellerchar"), new_char(db, b, "Buyerchar")
    db.update_character(b, t, lambda d: d.update(gold=1000))
    give_item(db, a, s)
    return a, b, s, t


def test_listing_removes_item_from_seller_and_purchase_transfers_exactly_once(db):
    a, b, s, t = setup_market(db)
    res = db.create_listing(a, s, "item", "Iron Sword", 1, 400, 0)
    assert res["data"]["inventory"] == []                             # reserved: no longer in the bag
    assert db.load_character(a, s)[0]["inventory"] == []
    bought = db.buy_listing(b, t, res["listing_id"])
    assert bought["data"]["gold"] == 600 and len(bought["data"]["inventory"]) == 1
    assert db.pending_earnings(s) == 400 - economy.market_fee(400) == 380
    with pytest.raises(ValidationError):
        db.buy_listing(b, t, res["listing_id"])                       # second purchase fails
    assert db.load_character(b, t)[0]["gold"] == 600                  # still charged only once
    data, _, collected = db.load_character(a, s)
    assert collected == 380 and data["gold"] == 380                   # seller credited exactly once
    assert db.pending_earnings(s) == 0


def test_cancel_returns_goods_and_blocks_later_sale(db):
    a, b, s, t = setup_market(db)
    lid = db.create_listing(a, s, "item", "Iron Sword", 1, 400, 0)["listing_id"]
    back = db.cancel_listing(a, s, lid)
    assert len(back["data"]["inventory"]) == 1
    with pytest.raises(ValidationError):
        db.buy_listing(b, t, lid)
    with pytest.raises(ValidationError):
        db.cancel_listing(a, s, lid)                                   # can't cancel twice (no duplication)


def test_stackable_listing_and_failed_purchase_changes_nothing(db):
    a, b, s, t = setup_market(db)
    db.update_character(a, s, lambda d: d["materials"].update(Gem=10))
    lid = db.create_listing(a, s, "material", "Gem", 6, 5000, None)["listing_id"]
    assert db.load_character(a, s)[0]["materials"]["Gem"] == 4
    with pytest.raises(ValidationError, match="Not enough gold"):
        db.buy_listing(b, t, lid)                                      # buyer has 1000 < 5000
    assert db.load_character(b, t)[0]["gold"] == 1000
    assert db.pending_earnings(s) == 0
    assert [l["id"] for l in db.active_listings(exclude_seller_id=t)] == [lid]


@pytest.mark.parametrize("kind,name,qty,price", [
    ("item", "Iron Sword", 1, 0), ("item", "Iron Sword", 1, -5), ("item", "Iron Sword", 1, 10 ** 12),
    ("item", "Iron Sword", 1, 1.5), ("item", "Iron Sword", 1, "100"), ("material", "Gem", 0, 10),
    ("material", "Gem", -3, 10), ("material", "Gem", 99, 10), ("material", "Unobtainium", 1, 10),
    ("weapon", "Iron Sword", 1, 10), ("item", "Wrong Name", 1, 10)])
def test_invalid_listings_are_rejected_without_changes(db, kind, name, qty, price):
    a, b, s, t = setup_market(db)
    db.update_character(a, s, lambda d: d["materials"].update(Gem=10))
    before = db.load_character(a, s)[0]
    with pytest.raises(StorageError):
        db.create_listing(a, s, kind, name, qty, price, 0 if kind == "item" else None)
    assert db.load_character(a, s)[0] == before and db.active_listings() == []


def test_cannot_buy_own_listing_and_listing_limit(db):
    a, b, s, t = setup_market(db)
    db.update_character(a, s, lambda d: d["materials"].update(Gem=100))
    lid = db.create_listing(a, s, "material", "Gem", 1, 5, None)["listing_id"]
    with pytest.raises(ValidationError):
        db.buy_listing(a, s, lid)
    for _ in range(9):
        db.create_listing(a, s, "material", "Gem", 1, 5, None)
    with pytest.raises(ValidationError, match="at most"):
        db.create_listing(a, s, "material", "Gem", 1, 5, None)


def test_history_and_listings_survive_restart(tmp_path):
    path = str(tmp_path / "m.db")
    db = Database(path)
    a, b, s, t = setup_market(db)
    sold = db.create_listing(a, s, "item", "Iron Sword", 1, 100, 0)["listing_id"]
    db.buy_listing(b, t, sold)
    give_item(db, a, s)
    open_listing = db.create_listing(a, s, "item", "Iron Sword", 1, 250, 0)["listing_id"]
    db.close()
    db2 = Database(path)
    assert [l["id"] for l in db2.active_listings()] == [open_listing]
    h = db2.market_history(s)
    assert len(h["sales"]) == 1 and h["sales"][0]["other"] == "Buyerchar" and h["sales"][0]["price"] == 100
    assert db2.market_history(t)["purchases"][0]["seller_name"] == "Sellerchar"


def test_deleting_a_character_removes_its_listings(db):
    a, b, s, t = setup_market(db)
    db.create_listing(a, s, "item", "Iron Sword", 1, 100, 0)
    db.delete_character(a, s)
    assert db.active_listings() == []
