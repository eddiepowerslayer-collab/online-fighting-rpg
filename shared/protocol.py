"""Versioned wire protocol: newline-delimited JSON over TCP (reliable; fine for a LAN).
Every client request carries an "id"; the server answers {"t":"reply","re":id,"ok":bool,...}.
Anything else from the server is an unsolicited push (queue updates, match snapshots...)."""
import json

PROTOCOL_VERSION = 1
MAX_CLIENT_MSG = 64 * 1024        # server rejects bigger messages
MAX_SERVER_MSG = 2 * 1024 * 1024  # client-side read limit
DEFAULT_PORT = 5555
ARENA_ACTIONS = frozenset({"jump", "light", "heavy", "dodge", "skill1", "skill2", "skill3",
                           "skill4", "skill5", "skill6"})


class ProtocolError(Exception):
    pass


def encode(msg: dict) -> bytes:
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")


def decode(line: bytes) -> dict:
    try:
        msg = json.loads(line.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ProtocolError("invalid JSON") from e
    if not isinstance(msg, dict) or not isinstance(msg.get("t"), str) or len(msg["t"]) > 32:
        raise ProtocolError("message needs a string type 't'")
    return msg


def field(msg: dict, name: str, typ, *, lo=None, hi=None, maxlen=None, default=...):
    """Fetch and validate one field of an untrusted message."""
    if name not in msg:
        if default is ...:
            raise ProtocolError(f"missing field '{name}'")
        return default
    v = msg[name]
    if typ is int and isinstance(v, bool):
        raise ProtocolError(f"bad field '{name}'")
    if not isinstance(v, typ):
        raise ProtocolError(f"bad field '{name}'")
    if lo is not None and v < lo or hi is not None and v > hi:
        raise ProtocolError(f"field '{name}' out of range")
    if maxlen is not None and len(v) > maxlen:
        raise ProtocolError(f"field '{name}' too long")
    return v
