"""SQLite persistence: accounts, characters and the marketplace.

Pure storage layer: it knows nothing about the game or pygame, and stores characters as
JSON dicts. Identity is the account/character database ID; NEVER an IP address.
All writes that must succeed together (e.g. a purchase) happen in one transaction.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager

from shared.economy import (MARKET_FEE_PERCENT, MAX_PRICE, EconomyError, give_goods,  # noqa: F401
                            market_fee, take_goods)

SCHEMA_VERSION = 1
MAX_CHARACTERS = 6
MAX_ACTIVE_LISTINGS = 10
MIN_PASSWORD_LEN = 6
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
CHAR_NAME_RE = re.compile(r"^[A-Za-z0-9_ ]{3,16}$")


class StorageError(Exception):
    """A database fault (disk, locked, closed...). Never swallowed: callers must show it."""


class ValidationError(StorageError):
    """A user-fixable problem (bad name, wrong state). Message is safe to show."""


# ---------------------------------------------------------------- passwords
def hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or secrets.token_bytes(16)
    pw = password.encode("utf-8")
    try:
        dk = hashlib.scrypt(pw, salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
        return f"scrypt${2 ** 14}${8}${1}${salt.hex()}${dk.hex()}"
    except (AttributeError, ValueError):  # OpenSSL without scrypt
        dk = hashlib.pbkdf2_hmac("sha256", pw, salt, 200_000, dklen=32)
        return f"pbkdf2$200000${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        pw = password.encode("utf-8")
        if parts[0] == "scrypt":
            _, n, r, p, salt, good = parts
            dk = hashlib.scrypt(pw, salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        elif parts[0] == "pbkdf2":
            _, iters, salt, good = parts
            dk = hashlib.pbkdf2_hmac("sha256", pw, bytes.fromhex(salt), int(iters), dklen=32)
        else:
            return False
        return hmac.compare_digest(dk.hex(), good)
    except (ValueError, TypeError, AttributeError):
        return False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS characters(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    class_name TEXT NOT NULL,
    level INTEGER NOT NULL,
    xp INTEGER NOT NULL,
    gold INTEGER NOT NULL,
    data TEXT NOT NULL,
    pending_gold INTEGER NOT NULL DEFAULT 0,
    rev INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(account_id, name));
CREATE TABLE IF NOT EXISTS market_listings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    seller_name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('item','material','potion')),
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    price INTEGER NOT NULL CHECK(price > 0),
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','sold','cancelled')),
    buyer_id INTEGER,
    sold_at REAL,
    created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_listings_status ON market_listings(status, price);
CREATE INDEX IF NOT EXISTS idx_characters_account ON characters(account_id);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        try:
            if path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            self.conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)  # we manage txns; the server uses it from one thread
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.executescript(_SCHEMA)
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except (sqlite3.Error, OSError) as e:
            raise StorageError(f"Cannot open save database: {e}") from e

    def close(self):
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    # ----------------------------------------------------------- plumbing
    @contextmanager
    def _tx(self):
        try:
            self.conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as e:
            raise StorageError(f"Database error: {e}") from e
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except sqlite3.Error as e:
            self._rollback()
            raise StorageError(f"Database error: {e}") from e
        except BaseException:
            self._rollback()
            raise

    def _rollback(self):
        try:
            self.conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    def _query(self, sql, args=()):
        try:
            return self.conn.execute(sql, args).fetchall()
        except sqlite3.Error as e:
            raise StorageError(f"Database error: {e}") from e

    # ----------------------------------------------------------- accounts
    def create_account(self, username: str, password: str) -> int:
        username = (username or "").strip()
        if not USERNAME_RE.match(username):
            raise ValidationError("Username must be 3-20 letters, numbers or underscores.")
        if len(password or "") < MIN_PASSWORD_LEN:
            raise ValidationError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
        pw_hash = hash_password(password)
        try:
            with self._tx() as c:
                cur = c.execute("INSERT INTO accounts(username, password_hash, created_at) VALUES(?,?,?)",
                                (username, pw_hash, time.time()))
                return cur.lastrowid
        except StorageError as e:
            if "UNIQUE" in str(e):
                raise ValidationError("That username is already taken.") from e
            raise

    def authenticate(self, username: str, password: str):
        """Returns the account id, or None for a wrong username/password."""
        rows = self._query("SELECT id, password_hash FROM accounts WHERE username = ?",
                           ((username or "").strip(),))
        if not rows:
            verify_password(password or "", hash_password("dummy-password"))  # equalise timing
            return None
        return rows[0]["id"] if verify_password(password or "", rows[0]["password_hash"]) else None

    def account_username(self, account_id: int):
        rows = self._query("SELECT username FROM accounts WHERE id = ?", (account_id,))
        return rows[0]["username"] if rows else None

    # ----------------------------------------------------------- characters
    def list_characters(self, account_id: int):
        rows = self._query("SELECT id, name, class_name, level, gold FROM characters "
                           "WHERE account_id = ? ORDER BY id", (account_id,))
        return [dict(r) for r in rows]

    def create_character(self, account_id: int, name: str, data: dict) -> int:
        name = (name or "").strip()
        if not CHAR_NAME_RE.match(name):
            raise ValidationError("Character name must be 3-16 letters, numbers, spaces or underscores.")
        data = dict(data, name=name)
        now = time.time()
        try:
            with self._tx() as c:
                n = c.execute("SELECT COUNT(*) FROM characters WHERE account_id = ?", (account_id,)).fetchone()[0]
                if n >= MAX_CHARACTERS:
                    raise ValidationError(f"You can have at most {MAX_CHARACTERS} characters.")
                cur = c.execute(
                    "INSERT INTO characters(account_id, name, class_name, level, xp, gold, data, created_at, updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (account_id, name, data["class"], data["level"], data["xp"], data["gold"],
                     json.dumps(data), now, now))
                return cur.lastrowid
        except StorageError as e:
            if "UNIQUE" in str(e):
                raise ValidationError("You already have a character with that name.") from e
            raise

    def load_character(self, account_id: int, character_id: int):
        """Returns (data dict, rev, gold collected from marketplace sales). Atomically moves
        pending sale earnings into the character's gold."""
        with self._tx() as c:
            row = self._get_char(c, account_id, character_id)
            data = self._parse(row)
            collected = row["pending_gold"]
            rev = row["rev"]
            if collected:
                data["gold"] = data.get("gold", 0) + collected
                rev = self._write(c, character_id, data, rev + 1, pending_zero=True)
            return data, rev, collected

    @staticmethod
    def _parse(row):
        try:
            return json.loads(row["data"])
        except ValueError as e:
            raise StorageError("Saved character data is corrupted.") from e

    @staticmethod
    def _get_char(c, account_id, character_id):
        row = c.execute("SELECT * FROM characters WHERE id = ? AND account_id = ?",
                        (character_id, account_id)).fetchone()
        if row is None:
            raise ValidationError("Character not found.")
        return row

    @staticmethod
    def _write(c, character_id, data, new_rev, pending_zero=False):
        c.execute("UPDATE characters SET class_name=?, level=?, xp=?, gold=?, data=?, rev=?, updated_at=?"
                  + (", pending_gold=0" if pending_zero else "") + " WHERE id = ?",
                  (data["class"], data["level"], data["xp"], data["gold"], json.dumps(data),
                   new_rev, time.time(), character_id))
        return new_rev

    def save_character(self, account_id: int, character_id: int, data: dict, expected_rev: int) -> int:
        """Save a snapshot. Rejected if the character changed on the server since the client
        loaded it (e.g. a marketplace sale/purchase): the client must reload."""
        with self._tx() as c:
            row = self._get_char(c, account_id, character_id)
            if row["rev"] != expected_rev:
                raise ValidationError("stale")
            return self._write(c, character_id, data, row["rev"] + 1)

    def update_character(self, account_id: int, character_id: int, mutate):
        """Atomic read-modify-write. `mutate(data)` edits the dict in place (or returns a new
        one) and may raise to abort. Returns (data, rev)."""
        with self._tx() as c:
            row = self._get_char(c, account_id, character_id)
            data = self._parse(row)
            try:
                result = mutate(data)
            except EconomyError as e:
                raise ValidationError(str(e)) from e
            data = result if isinstance(result, dict) else data
            return data, self._write(c, character_id, data, row["rev"] + 1)

    def delete_character(self, account_id: int, character_id: int):
        """Also removes the character's marketplace listings (their goods are lost)."""
        with self._tx() as c:
            cur = c.execute("DELETE FROM characters WHERE id = ? AND account_id = ?", (character_id, account_id))
            if cur.rowcount != 1:
                raise ValidationError("Character not found.")

    def pending_earnings(self, character_id: int) -> int:
        rows = self._query("SELECT pending_gold FROM characters WHERE id = ?", (character_id,))
        return rows[0]["pending_gold"] if rows else 0

    # ----------------------------------------------------------- marketplace
    @staticmethod
    def _listing(row) -> dict:
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        return d

    def active_listings(self, exclude_seller_id: int = None, limit: int = 300):
        rows = self._query("SELECT * FROM market_listings WHERE status = 'active' AND seller_id != ? "
                           "ORDER BY price ASC, id ASC LIMIT ?", (exclude_seller_id or -1, limit))
        return [self._listing(r) for r in rows]

    def seller_listings(self, seller_id: int):
        rows = self._query("SELECT * FROM market_listings WHERE status = 'active' AND seller_id = ? "
                           "ORDER BY id DESC", (seller_id,))
        return [self._listing(r) for r in rows]

    def create_listing(self, account_id, seller_id, kind, name, quantity, price, item_index=None):
        """Remove the goods from the seller, save the seller and insert the listing: one txn."""
        if not (isinstance(price, int) and not isinstance(price, bool) and 1 <= price <= MAX_PRICE):
            raise ValidationError("Price must be a whole number of at least 1 gold.")
        quantity = 1 if kind == "item" else quantity
        with self._tx() as c:
            row = self._get_char(c, account_id, seller_id)
            n = c.execute("SELECT COUNT(*) FROM market_listings WHERE seller_id = ? AND status = 'active'",
                          (seller_id,)).fetchone()[0]
            if n >= MAX_ACTIVE_LISTINGS:
                raise ValidationError(f"You can have at most {MAX_ACTIVE_LISTINGS} active listings.")
            data = self._parse(row)
            try:
                payload = take_goods(data, kind, name, quantity, item_index)
            except EconomyError as e:
                raise ValidationError(str(e)) from e
            rev = self._write(c, seller_id, data, row["rev"] + 1)
            cur = c.execute("INSERT INTO market_listings(seller_id, seller_name, kind, name, quantity, price,"
                            " payload, created_at) VALUES(?,?,?,?,?,?,?,?)",
                            (seller_id, row["name"], kind, name, quantity, price, json.dumps(payload), time.time()))
            return {"listing_id": cur.lastrowid, "data": data, "rev": rev}

    def cancel_listing(self, account_id, seller_id, listing_id):
        """Return the goods to the seller and mark the listing cancelled: one txn."""
        with self._tx() as c:
            row = self._get_char(c, account_id, seller_id)
            lst = c.execute("SELECT * FROM market_listings WHERE id = ? AND seller_id = ? AND status = 'active'",
                            (listing_id, seller_id)).fetchone()
            if lst is None:
                raise ValidationError("That listing is no longer active.")
            data = self._parse(row)
            give_goods(data, lst["kind"], lst["name"], lst["quantity"], json.loads(lst["payload"]))
            c.execute("UPDATE market_listings SET status='cancelled' WHERE id = ?", (listing_id,))
            return {"data": data, "rev": self._write(c, seller_id, data, row["rev"] + 1)}

    def buy_listing(self, account_id, buyer_id, listing_id):
        """Deduct gold + add goods to the buyer, credit the seller (minus fee) and mark the
        listing sold, all in ONE transaction (no duplication, no lost gold)."""
        with self._tx() as c:
            lst = c.execute("SELECT * FROM market_listings WHERE id = ?", (listing_id,)).fetchone()
            if lst is None or lst["status"] != "active":
                raise ValidationError("That listing was already sold or cancelled.")
            if lst["seller_id"] == buyer_id:
                raise ValidationError("You can't buy your own listing.")
            row = self._get_char(c, account_id, buyer_id)
            data = self._parse(row)
            if data["gold"] < lst["price"]:
                raise ValidationError(f"Not enough gold (need {lst['price']}).")
            data["gold"] -= lst["price"]
            give_goods(data, lst["kind"], lst["name"], lst["quantity"], json.loads(lst["payload"]))
            rev = self._write(c, buyer_id, data, row["rev"] + 1)
            c.execute("UPDATE characters SET pending_gold = pending_gold + ? WHERE id = ?",
                      (lst["price"] - market_fee(lst["price"]), lst["seller_id"]))
            c.execute("UPDATE market_listings SET status='sold', buyer_id=?, sold_at=? WHERE id = ?",
                      (buyer_id, time.time(), listing_id))
            return {"data": data, "rev": rev, "listing": self._listing(lst)}

    def market_history(self, character_id: int, limit: int = 30) -> dict:
        """Completed sales and purchases for a character (newest first)."""
        sales = self._query("SELECT l.*, c.name AS other FROM market_listings l LEFT JOIN characters c "
                            "ON c.id = l.buyer_id WHERE l.seller_id = ? AND l.status = 'sold' "
                            "ORDER BY l.sold_at DESC LIMIT ?", (character_id, limit))
        buys = self._query("SELECT l.*, l.seller_name AS other FROM market_listings l "
                           "WHERE l.buyer_id = ? AND l.status = 'sold' ORDER BY l.sold_at DESC LIMIT ?",
                           (character_id, limit))
        return {"sales": [self._listing(r) for r in sales], "purchases": [self._listing(r) for r in buys]}
