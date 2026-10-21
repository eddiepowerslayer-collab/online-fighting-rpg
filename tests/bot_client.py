"""A headless game client run as its OWN PROCESS (used by test_processes.py).
Registers, creates a character, queues for a mode, plays the match by sending real inputs,
and prints one JSON line summarising what it saw."""
import json
import sys
import time

sys.path.insert(0, __file__.rsplit("tests", 1)[0])
from client.networking.client import NetClient  # noqa: E402


def main(port, user, cls, mode):
    c = NetClient()
    c.connect("127.0.0.1", int(port))
    assert c.request("register", username=user, password="secret1")["ok"]
    cid = c.request("create_char", name=f"{user}_hero", **{"class": cls})["char_id"]
    c.request("select_char", char_id=cid)
    assert c.request("queue_join", mode=mode)["ok"]
    found = end = None
    snaps, t0 = 0, time.time()
    while time.time() - t0 < 40 and end is None:
        if found:
            c.send("input", axis=1 if found["you"] % 2 == 0 else -1, actions=["light", "skill1"])
        for m in c.poll():
            if m["t"] == "match_found":
                found = m
            elif m["t"] == "snap":
                snaps += 1
            elif m["t"] == "match_end":
                end = m
        time.sleep(0.03)
    out = {"user": user, "found": bool(found), "match_id": found and found["match_id"], "you": found and found["you"],
           "teams": found and [p["team"] for p in found["players"]], "snaps": snaps, "ended": bool(end),
           "pid": os_pid()}
    if end:
        me = next(p for p in end["results"]["players"] if p["pid"] == found["you"])
        out.update(result=me["result"], xp=me.get("xp"), gold=me.get("gold"), level=end["data"]["level"])
    print(json.dumps(out), flush=True)


def os_pid():
    import os
    return os.getpid()


if __name__ == "__main__":
    main(*sys.argv[1:5])
