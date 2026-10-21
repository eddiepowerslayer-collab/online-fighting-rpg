"""Snapshot interpolation: remote players are drawn slightly in the past, blended between
the two server snapshots around that moment, so 15 snapshots/sec looks smooth."""
import time


class SnapshotBuffer:
    def __init__(self, delay=0.12, max_len=40):
        self.delay, self.max_len = delay, max_len
        self.snaps = []            # (arrival_time, snapshot)

    def push(self, snap, t=None):
        self.snaps.append((time.monotonic() if t is None else t, snap))
        if len(self.snaps) > self.max_len:
            self.snaps.pop(0)

    @property
    def latest(self):
        return self.snaps[-1][1] if self.snaps else None

    def positions(self, now=None):
        """{player id: (x, y)} interpolated at (now - delay)."""
        if not self.snaps:
            return {}
        now = time.monotonic() if now is None else now
        target = now - self.delay
        older = newer = None
        for t, snap in self.snaps:
            if t <= target:
                older = (t, snap)
            else:
                newer = (t, snap)
                break
        if older is None:                       # buffer too new: show the earliest we have
            return {p["id"]: (p["x"], p["y"]) for p in self.snaps[0][1]["players"]}
        if newer is None:                       # buffer too old: show the latest
            return {p["id"]: (p["x"], p["y"]) for p in older[1]["players"]}
        (t0, s0), (t1, s1) = older, newer
        a = (target - t0) / max(1e-6, t1 - t0)
        prev = {p["id"]: p for p in s0["players"]}
        out = {}
        for p in s1["players"]:
            q = prev.get(p["id"], p)
            out[p["id"]] = (q["x"] + (p["x"] - q["x"]) * a, q["y"] + (p["y"] - q["y"]) * a)
        return out
