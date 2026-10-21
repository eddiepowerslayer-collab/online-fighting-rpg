"""Genuine multi-process play: a real server process and separate client processes."""
import json
import os
import socket
import subprocess
import sys
import time

import pygame
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.3).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


@pytest.fixture
def server_process(tmp_path):
    port = free_port()
    log = open(tmp_path / "server.log", "w")
    p = subprocess.Popen([sys.executable, "-m", "server.main", "--host", "127.0.0.1", "--port", str(port),
                          "--db", str(tmp_path / "proc.db"), "--time-limit", "4"], cwd=ROOT, stdout=log, stderr=log)
    assert wait_port(port), "server process did not start"
    yield port, p
    p.terminate()
    p.wait(10)


def run_bots(port, specs, mode):
    procs = [subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "bot_client.py"), str(port), user, cls, mode],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT)
             for user, cls in specs]
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=90)
        assert p.returncode == 0, err
        outs.append(json.loads(out.strip().splitlines()[-1]))
    return outs


def test_two_separate_client_processes_play_a_1v1_on_a_separate_server_process(server_process):
    port, srv = server_process
    a, b = run_bots(port, [("procalice", "Warrior"), ("procbobby", "Mage")], "1v1")
    assert len({a["pid"], b["pid"], srv.pid, os.getpid()}) == 4            # four different OS processes
    assert a["found"] and b["found"] and a["match_id"] == b["match_id"]
    assert {a["you"], b["you"]} == {0, 1} and sorted(a["teams"]) == [0, 1]
    assert a["snaps"] > 20 and b["snaps"] > 20                                # real-time state streamed to both
    assert a["ended"] and b["ended"]
    assert {a["result"], b["result"]} in ({"draw"}, {"win", "loss"})         # a consistent outcome
    assert a["xp"] > 0 and b["gold"] > 0                                      # server awarded rewards


def test_four_client_processes_play_a_2v2(server_process):
    port, _ = server_process
    outs = run_bots(port, [("proc_p1", "Warrior"), ("proc_p2", "Mage"), ("proc_p3", "Tank"), ("proc_p4", "Archer")], "2v2")
    assert len({o["match_id"] for o in outs}) == 1 and len({o["pid"] for o in outs}) == 4
    assert sorted(outs[0]["teams"]) == [0, 0, 1, 1] and all(o["ended"] and o["snaps"] > 20 for o in outs)


def test_host_game_button_starts_a_real_server_process_and_joins_it(tmp_path, monkeypatch):
    from client.game import Game
    from client.ui.net_screens import LoginScreen
    port = free_port()
    g = Game()
    try:
        monkeypatch.setenv("RPG_DB_PATH", str(tmp_path / "host.db"))              # the hosted server saves here, not in saves/
        ok, msg = g.host_server(port)
        assert ok, msg
        assert isinstance(g.scene, LoginScreen) and g.server_proc.poll() is None and g.host_info.endswith(f":{port}")
        assert g.register("hostuser", "secret1")[0]
        assert g.create_character("Host Hero", "Warrior")[0]
        friend = __import__("client.networking.client", fromlist=["NetClient"]).NetClient()
        friend.connect("127.0.0.1", port)                                           # a second connection to the same host
        assert friend.request("register", username="friend01", password="secret1")["ok"]
        g.shutdown()
        assert g.server_proc.poll() is not None                                     # hosting stopped with the game
    finally:
        pygame.quit()
        if g.server_proc and g.server_proc.poll() is None:
            g.server_proc.terminate()
