"""Shared helpers: start a real server, connect real clients over TCP."""
import threading
import time

from client.character import Character
from client.networking.client import NetClient
from server.game_server import ServerThread


def start_server(path, **kw):
    st = ServerThread(path, **kw)
    return st, st.start()


def login_client(port, username, cls="Warrior", name=None, password="secret1"):
    """A fresh real client: register, create a character, select it. Returns (client, info)."""
    c = NetClient()
    c.connect("127.0.0.1", port)
    reg = c.request("register", username=username, password=password)
    assert reg["ok"], reg
    name = name or f"{username}_hero"[:16]
    r = c.request("create_char", name=name, **{"class": cls})
    assert r["ok"], r
    sel = c.request("select_char", char_id=r["char_id"])
    assert sel["ok"], sel
    return c, {"account_id": reg["account"]["id"], "char_id": r["char_id"], "data": sel["data"], "rev": sel["rev"]}


def grant(st, account_id, char_id, fn):
    """Edit a character directly in the server's database (test setup only)."""
    def mutate(data):
        ch = Character.from_dict(data)
        fn(ch)
        return ch.to_dict()
    return st.server.db.update_character(account_id, char_id, mutate)


def account_id_of(st, username):
    return st.server.db._query("SELECT id FROM accounts WHERE username = ?", (username,))[0]["id"]


def wait_for(client, kind, timeout=5.0, keep=None):
    """Collect pushes until one of type `kind` arrives; returns it (others go to `keep`)."""
    end = time.time() + timeout
    while time.time() < end:
        for m in client.poll():
            if m["t"] == kind:
                return m
            if keep is not None:
                keep.append(m)
        time.sleep(0.01)
    return None


def drain(clients, seconds):
    out = {id(c): [] for c in clients}
    end = time.time() + seconds
    while time.time() < end:
        for c in clients:
            out[id(c)].extend(c.poll())
        time.sleep(0.01)
    return out
