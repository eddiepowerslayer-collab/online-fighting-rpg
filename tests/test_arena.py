"""Authoritative arena simulation (no sockets): modes, teams, scoring, fairness, co-op."""
import random

import pytest

from client.character import Character
from client.classes import CLASS_ORDER
from server.arena import ARENA_WIDTH, Arena, balance_teams, normalized_character
from shared import modes as M

DT = 1 / 30


def entries(n, levels=None, classes=None):
    out = []
    for i in range(n):
        ch = Character(classes[i] if classes else CLASS_ORDER[i % 5], f"P{i}")
        ch.add_levels((levels[i] if levels else 1) - 1)
        out.append(dict(char_id=i + 1, account_id=i + 1, name=f"P{i}", level=ch.progression.level, data=ch.to_dict()))
    return out


def start(arena):
    for _ in range(int(M.COUNTDOWN * 30) + 3):
        arena.step(DT)
    assert arena.state == "active"


@pytest.mark.parametrize("mode,size", [("1v1", 1), ("2v2", 2), ("3v3", 3), ("4v4", 4), ("5v5", 5)])
def test_team_modes_make_two_teams_of_the_right_size(mode, size):
    a = Arena(1, mode, entries(2 * size), random.Random(1))
    teams = [p.team for p in a.players]
    assert sorted(set(teams)) == [0, 1] and teams.count(0) == teams.count(1) == size
    assert M.players_needed(mode) == 2 * size == M.max_players(mode)


def test_team_balance_splits_strong_players_between_teams():
    es = entries(4, levels=[100, 90, 10, 5])
    t = balance_teams(es)
    assert t[0] != t[1] and t[2] != t[3]
    s0 = sum(es[i]["level"] for i in range(4) if t[i] == 0)
    s1 = sum(es[i]["level"] for i in range(4) if t[i] == 1)
    assert abs(s0 - s1) <= 10                              # teams are about equally strong


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        Arena(1, "6v6", entries(12))


def test_free_for_all_has_no_teams_and_everyone_can_hurt_everyone():
    a = Arena(1, "ffa", entries(3), random.Random(1))
    assert len({p.team for p in a.players}) == 3
    assert M.players_needed("ffa") == 2 and M.max_players("ffa") == 8 and not M.is_team_mode("ffa")
    start(a)
    x, y = a.players[0], a.players[1]
    y.body.px, y.body.rect.x = x.body.px + 40, int(x.body.px + 40)
    y.body.py = x.body.py
    for _ in range(40):
        a.set_input(0, 0, {"light"})
        a.step(DT)
    assert y.body.hp < y.body.max_hp                      # no friendly fire rule in FFA


def put_next_to(a, i, j):
    p, q = a.players[i].body, a.players[j].body
    q.px = p.px + 40
    q.rect.x, q.py = int(q.px), p.py
    q.rect.y = int(q.py)


def test_no_friendly_fire_in_team_modes_but_enemies_take_damage():
    a = Arena(1, "2v2", entries(4, classes=[CLASS_ORDER[0]] * 4), random.Random(1))
    start(a)
    mate = next(p for p in a.players if p.team == a.players[0].team and p is not a.players[0])
    foe = next(p for p in a.players if p.team != a.players[0].team)
    for tgt in (mate, foe):
        put_next_to(a, 0, tgt.pid)
        for _ in range(40):
            a.set_input(0, 0, {"light"})
            a.step(DT)
    assert mate.body.hp == mate.body.max_hp and foe.body.hp < foe.body.max_hp


def test_kills_score_and_the_kill_target_ends_the_match():
    a = Arena(1, "1v1", entries(2, classes=[CLASS_ORDER[0]] * 2), random.Random(1))
    start(a)
    a.target = 2
    for _ in range(2):
        victim = a.players[1]
        put_next_to(a, 0, 1)
        victim.body.hp = 1
        victim.body.invuln = 0
        for _ in range(60):
            a.set_input(0, 0, {"light"})
            a.step(DT)
            if not victim.body.alive:
                break
        victim.respawn_t = 0
        a.step(DT)
    assert a.team_scores[a.players[0].team] == 2 and a.state == "ended"
    r = a.results()
    assert {p["pid"]: p["result"] for p in r["players"]} == {0: "win", 1: "loss"}


def test_time_limit_ends_match_and_tie_is_a_draw(monkeypatch):
    monkeypatch.setattr(M, "TIME_LIMIT", 1.0)
    a = Arena(1, "1v1", entries(2), random.Random(1))
    start(a)
    for _ in range(40):
        a.step(DT)
    assert a.state == "ended"
    assert {p["result"] for p in a.results()["players"]} == {"draw"}


def test_forfeit_gives_the_win_to_the_other_team():
    a = Arena(1, "2v2", entries(4), random.Random(1))
    start(a)
    for p in a.players:
        if p.team == 1:
            a.leave(p.pid)
    a.step(DT)
    assert a.state == "ended"
    res = {p["pid"]: p["result"] for p in a.results()["players"]}
    assert all(res[p.pid] == ("win" if p.team == 0 else "loss") for p in a.players)


def test_all_players_leaving_aborts_the_match():
    a = Arena(1, "1v1", entries(2), random.Random(1))
    start(a)
    for p in a.players:
        a.leave(p.pid)
    a.step(DT)
    assert a.state == "ended" and a.results()["aborted"]


def test_disconnected_player_has_a_grace_period_then_forfeits(monkeypatch):
    from server import arena as arena_mod
    monkeypatch.setattr(arena_mod, "DISCONNECT_GRACE", 0.5)
    a = Arena(1, "2v2", entries(4), random.Random(1))
    start(a)
    a.set_connected(0, False)
    a.step(DT)
    assert not a.players[0].left
    a.set_connected(0, True)                               # reconnect in time
    for _ in range(30):
        a.step(DT)
    assert not a.players[0].left
    a.set_connected(0, False)
    for _ in range(30):
        a.step(DT)
    assert a.players[0].left


def test_respawn_after_death_with_spawn_protection():
    a = Arena(1, "1v1", entries(2), random.Random(1))
    start(a)
    v = a.players[1]
    v.body.hp = 0
    v.respawn_t = M.RESPAWN_TIME
    for _ in range(int(M.RESPAWN_TIME * 30) + 3):
        a.step(DT)
    assert v.body.alive and v.body.hp == v.body.max_hp and v.body.invuln > 0


def test_server_enforces_cooldowns_and_ignores_unknown_actions():
    a = Arena(1, "1v1", entries(2, classes=[CLASS_ORDER[0]] * 2), random.Random(1))
    start(a)
    swings, prev = 0, 0.0
    for _ in range(30):                                    # one second of key mashing every tick
        a.set_input(0, 1, {"light", "hack", "skill99", "use:Health Potion"})
        a.step(DT)
        cd = a.players[0].body.light_cd
        swings += cd > prev + 0.1                          # light_cd jumps up each time a swing starts
        prev = cd
    assert 1 <= swings <= 3                                # 0.35s cooldown => at most 3 swings in 1s
    assert a.players[0].body.character.consumables["Health Potion"] == 0   # potions unavailable in the arena
    a.set_input(0, 99, {"light"})                          # absurd axis is clamped to "no movement"
    assert a.players[0].axis == 0


def test_players_cannot_leave_the_arena():
    a = Arena(1, "1v1", entries(2), random.Random(1))
    start(a)
    for _ in range(400):
        a.set_input(0, -1, set())
        a.step(DT)
    assert a.players[0].body.rect.left >= 0
    for _ in range(900):
        a.set_input(0, 1, set())
        a.step(DT)
    assert a.players[0].body.rect.right <= ARENA_WIDTH


def test_normalized_ruleset_makes_a_level_3000_player_comparable_to_a_level_30_one():
    big = Character(CLASS_ORDER[0], "Big")
    big.add_levels(2999)
    big.progression.skill_points = 10**6
    big.spend_points("strength", "max") if big.progression.stat_points else None
    for sk in ("war_whirlwind", "war_iron_skin"):
        big.buy_skill(sk)
    small = Character(CLASS_ORDER[0], "Small")
    small.add_levels(29)
    nb, ns = normalized_character(big.to_dict()), normalized_character(small.to_dict())
    assert nb.progression.level == ns.progression.level == M.ARENA_LEVEL
    assert nb.max_hp < ns.max_hp * 2.5 and not any(k.endswith(("cleave", "unbreakable", "wrath")) for k in nb.skills)
    assert all(rank <= 3 for rank in nb.skills.values())
    assert normalized_character(big.to_dict(), "open").progression.level == 3000


def test_snapshot_contains_only_authoritative_state():
    a = Arena(1, "1v1", entries(2), random.Random(1))
    start(a)
    s = a.snapshot()
    assert {"tick", "state", "players", "atks", "ev", "ts", "tl"} <= set(s)
    assert {"id", "x", "y", "hp", "mhp", "al"} <= set(s["players"][0])
    assert "en" not in s
    assert "skills" in a.you(0) and "energy" in a.you(0)


# ---------- co-op PvE ----------
def coop(n=2, levels=None):
    return Arena(1, "coop", entries(n, levels), random.Random(3))


def test_coop_everyone_is_on_one_team_with_shared_enemies_and_a_boss():
    a = coop(3)
    assert {p.team for p in a.players} == {0} and len(a.enemies) == 8
    assert a.enemies[-1].boss and not any(e.boss for e in a.enemies[:-1])
    assert len({e.eid for e in a.enemies}) == 8
    snap = a.snapshot()
    assert len(snap["en"]) == 8                            # one shared list for every client


def test_coop_enemies_scale_with_party_size():
    solo, quad = coop(1), coop(4)
    assert quad.enemies[0].max_hp == round(solo.enemies[0].max_hp * 2.5)


def test_coop_players_damage_enemies_but_not_each_other():
    a = coop(2)
    start(a)
    e = a.enemies[0]
    for i in (0, 1):
        a.players[i].body.px = e.px - 40 + i * 5
        a.players[i].body.rect.x = int(a.players[i].body.px)
    e.cooldown = 99
    for _ in range(60):
        a.set_input(0, 0, {"light"})
        a.set_input(1, 0, {"light"})
        a.step(DT)
    assert e.hp < e.max_hp
    assert all(p.body.hp == p.body.max_hp for p in a.players)


def test_coop_kill_rewards_every_participant_and_victory_ends_match():
    a = coop(2)
    start(a)
    for i, e in enumerate(a.enemies):
        e.take_damage(10 ** 9, 1, 0)
        a._coop_enemy_down(e, a.players[i % 2])
    a.step(DT)
    assert a.state == "ended" and a.results()["players"][0]["result"] == "win"
    assert a.players[0].coop_xp == a.players[1].coop_xp > 0     # shared XP
    assert a.players[0].coop_gold > 0
    assert a.players[0].kills + a.players[1].kills == 8


def test_coop_xp_is_diminished_for_much_higher_level_players():
    a = coop(2, levels=[1, 500])
    start(a)
    e = a.enemies[0]
    e.take_damage(10 ** 9, 1, 0)
    a._coop_enemy_down(e, a.players[0])
    assert a.players[1].coop_xp < a.players[0].coop_xp / 10


def test_coop_time_limit_means_defeat(monkeypatch):
    monkeypatch.setattr(M, "COOP_TIME_LIMIT", 0.5)
    a = coop(2)
    start(a)
    for _ in range(30):
        a.step(DT)
    assert a.state == "ended" and a.results()["players"][0]["result"] == "loss"
