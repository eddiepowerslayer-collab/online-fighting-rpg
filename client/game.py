import atexit
import os
import random
import socket
import subprocess
import sys
import time

import pygame

from . import settings as S
from .character import Character, CharacterDataError
from .networking.client import NetClient, NetError
from .renderer import Renderer
from .run import Run
from .ui.net_screens import (ArenaScreen, CharacterSelectScreen, ConnectScreen, LobbyScreen, LoginScreen,
                             NewCharacterScreen)
from .ui.screens import HomeScreen, ResultsScreen, RunScreen
from shared.protocol import DEFAULT_PORT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RED, GREEN, WHITE = (240, 110, 110), (120, 230, 120), (235, 235, 242)


def lan_ip() -> str:
    """Best-guess LAN address of this computer (no packets are sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def port_open(host, port, timeout=0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


class Game:
    """Top-level app: window, server connection, the loaded Character, and the active scene.
    The server owns all permanent data; this class only caches the selected character."""

    def __init__(self, rng=None):
        pygame.init()
        pygame.display.set_caption(S.TITLE)
        self.screen = pygame.display.set_mode((S.SCREEN_W, S.SCREEN_H))
        self.clock = pygame.time.Clock()
        self.rng = rng or random.Random()
        self.fonts = {"xs": pygame.font.Font(None, 19), "s": pygame.font.Font(None, 23),
                      "m": pygame.font.Font(None, 30), "t": pygame.font.Font(None, 46),
                      "l": pygame.font.Font(None, 72)}
        self.renderer = Renderer(self.screen)
        self.running = True
        self.net = NetClient()
        self.account_id, self.username = None, ""
        self.character = None
        self.dirty = False
        self.last_host, self.last_port, self.last_user = "127.0.0.1", DEFAULT_PORT, ""
        self.host_info = ""
        self.server_proc = None
        self.notice = ["", WHITE, 0.0]
        self.saved_flash = 0.0
        self.scene = ConnectScreen(self)

    # ------------------------------------------------------------ notices
    def say(self, text, color=WHITE, secs=4.0):
        self.notice = [text, color, secs]

    # ------------------------------------------------------------ networking helpers
    def rpc(self, t, **fields) -> dict:
        """Ask the server something. Never raises: returns {"ok": False, "error": ...} on failure."""
        try:
            return self.net.request(t, **fields)
        except NetError as e:
            if not self.net.connected:
                self._lost(str(e))
            return {"ok": False, "error": str(e)}

    def _lost(self, reason):
        if isinstance(self.scene, ConnectScreen):
            return
        self.character, self.account_id = None, None
        self.scene = ConnectScreen(self, f"Disconnected: {reason}")

    def connect(self, host, port):
        try:
            self.net.connect(host, port)
        except NetError as e:
            return False, str(e)
        self.last_host, self.last_port = host, port
        self.scene = LoginScreen(self)
        return True, ""

    def disconnect(self):
        self.net.close()
        self.account_id = self.character = None
        self.scene = ConnectScreen(self)

    def host_server(self, port):
        """Start the game server on this computer (as a separate process) and join it."""
        if not port_open("127.0.0.1", port):
            os.makedirs(os.path.join(ROOT, "saves"), exist_ok=True)
            log = open(os.path.join(ROOT, "saves", "server.log"), "a")
            try:
                self.server_proc = subprocess.Popen(
                    [sys.executable, "-m", "server.main", "--host", "0.0.0.0", "--port", str(port)],
                    cwd=ROOT, stdout=log, stderr=log)
            except OSError as e:
                return False, f"Could not start the server: {e}"
            atexit.register(self._stop_server)
            for _ in range(50):
                if port_open("127.0.0.1", port):
                    break
                if self.server_proc.poll() is not None:
                    return False, "The server stopped immediately. See saves/server.log."
                time.sleep(0.15)
            else:
                return False, "The server didn't start in time. See saves/server.log."
        ok, msg = self.connect("127.0.0.1", port)
        if ok:
            self.host_info = f"{lan_ip()}:{port}"
            self.say(f"Hosting! Friends on your network join with  {self.host_info}", GREEN, 10.0)
        return ok, msg

    def _stop_server(self):
        p = self.server_proc
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(5)

    # ------------------------------------------------------------ account / characters
    def register(self, username, password):
        r = self.rpc("register", username=username, password=password)
        return self._logged_in(r, username)

    def login(self, username, password):
        r = self.rpc("login", username=username, password=password)
        return self._logged_in(r, username)

    def _logged_in(self, r, username):
        if not r.get("ok"):
            return False, r.get("error", "Login failed.")
        self.account_id, self.username = r["account"]["id"], r["account"]["username"]
        self.last_user = self.username
        self.go_character_select()
        return True, ""

    def logout(self):
        self.autosave()
        self.rpc("logout")
        self.character, self.account_id = None, None
        self.scene = LoginScreen(self)

    def go_character_select(self):
        self.character = None
        self.scene = CharacterSelectScreen(self)

    def list_characters(self):
        r = self.rpc("list_chars")
        return r.get("characters", []) if r.get("ok") else []

    def open_new_character(self):
        self.scene = NewCharacterScreen(self)

    def create_character(self, name, class_name):
        r = self.rpc("create_char", name=name, **{"class": class_name})
        if not r.get("ok"):
            return False, r.get("error", "Could not create the character.")
        self.play_character(r["char_id"])
        return True, ""

    def delete_character(self, char_id):
        r = self.rpc("delete_char", char_id=char_id)
        if not r.get("ok"):
            self.say(r.get("error", "Could not delete."), RED)
        return r.get("ok", False)

    def play_character(self, char_id):
        r = self.rpc("select_char", char_id=char_id)
        if not r.get("ok"):
            self.say(r.get("error", "Could not load that character."), RED)
            return False
        if not self.apply_character(r["data"], r["rev"], char_id):
            return False
        if r.get("collected"):
            self.say(f"Collected {r['collected']} gold from your marketplace sales!", GREEN, 6.0)
        if r.get("rejoin"):
            self.start_arena(r["rejoin"])
        else:
            self.go_home()
        return True

    def apply_character(self, data, rev, char_id) -> bool:
        """Replace the cached character with the server's copy (validated)."""
        try:
            ch = Character.from_dict(data)
        except CharacterDataError as e:
            self.say(f"Server sent invalid character data: {e}", RED)
            return False
        ch.id, ch.rev = char_id, rev
        if self.character is not None and self.character.id == char_id:
            ch.dungeon_selected = min(self.character.dungeon_selected, ch.dungeon_unlocked)
        self.character = ch
        self.dirty = False
        return True

    def char_call(self, t, **fields) -> dict:
        """A server-authoritative action on the current character (stats, skills, trades...).
        The reply carries the new authoritative character, which replaces our copy."""
        r = self.rpc(t, **fields)
        if r.get("ok") and "data" in r:
            self.apply_character(r["data"], r["rev"], self.character.id)
        return r

    market_call = char_call

    def autosave(self) -> bool:
        """Save the character on the server. Failures are shown loudly and never hidden."""
        ch = self.character
        if ch is None:
            return True
        self.dirty = True
        if not self.net.connected:
            self.say("SAVE FAILED, progress not saved: not connected to the server", RED, 8.0)
            return False
        r = self.rpc("save_char", data=ch.to_dict(), rev=ch.rev)
        if r.get("ok"):
            ch.rev, self.dirty = r["rev"], False
            self.saved_flash = 1.2
            return True
        if r.get("stale"):
            self.say("Your character changed on the server (e.g. a sale). Reloading it.", RED, 6.0)
            self.reload_character()
        else:
            self.say("SAVE FAILED, progress not saved: " + r.get("error", "unknown error"), RED, 8.0)
        return False

    def reload_character(self):
        r = self.rpc("select_char", char_id=self.character.id)
        if r.get("ok"):
            self.apply_character(r["data"], r["rev"], self.character.id)

    def collect_earnings(self):
        if self.character is None or (self.dirty and not self.autosave()):
            return
        r = self.rpc("collect")
        if r.get("ok") and r.get("collected"):
            self.apply_character(r["data"], r["rev"], self.character.id)
            self.say(f"Collected {r['collected']} gold from marketplace sales!", GREEN, 6.0)

    # ------------------------------------------------------------ scene changes
    def go_home(self):
        if self.character is None:
            return self.go_character_select()
        self.collect_earnings()
        self.scene = HomeScreen(self)

    def open(self, screen_cls):
        self.scene = screen_cls(self)

    def go_lobby(self):
        self.scene = LobbyScreen(self)

    def rematch(self, mode):
        self.scene = LobbyScreen(self)
        if self.scene.you != mode:
            self.scene.toggle(mode)

    def leave_match(self):
        self.rpc("leave_match")
        self.go_lobby()

    def switch_character(self):
        self.autosave()
        self.go_character_select()

    def start_arena(self, found):
        self.scene = ArenaScreen(self, found)

    def start_run(self):
        run = Run(self.character, self.character.dungeon_selected, self.rng)
        self.scene = RunScreen(self, run)

    def show_results(self, run):
        self.autosave()
        self.scene = ResultsScreen(self, run)

    # ------------------------------------------------------------ main loop
    def pump(self, dt):
        self.net.keepalive()
        for msg in self.net.poll():
            t = msg["t"]
            if t == "_disconnected":
                self._lost(msg["reason"])
            elif t == "kicked":
                self.net.close()
                self._lost(msg["reason"])
            elif t == "match_found":
                self.start_arena(msg)
            elif t == "sold":
                self.say(f"Sold {msg['name']} for {msg['price']} gold! You get {msg['earned']} after the fee.", GREEN, 6.0)
            else:
                if t == "error":
                    self.say(msg.get("error", ""), RED)
                handler = getattr(self.scene, "on_net", None)
                if handler:
                    handler(msg)
        self.notice[2] = max(0.0, self.notice[2] - dt)
        self.saved_flash = max(0.0, self.saved_flash - dt)

    def draw(self):
        self.scene.draw(self.screen)
        text, color, ttl = self.notice
        if ttl > 0 and text:
            img = self.fonts["s"].render(text, True, color)
            box = img.get_rect(center=(S.SCREEN_W // 2, 14)).inflate(24, 10)
            pygame.draw.rect(self.screen, (10, 10, 18), box, border_radius=8)
            pygame.draw.rect(self.screen, color, box, 1, border_radius=8)
            self.screen.blit(img, img.get_rect(center=box.center))
        if self.saved_flash > 0:
            self.screen.blit(self.fonts["xs"].render("saved", True, (110, 160, 110)), (S.SCREEN_W - 50, 4))
        pygame.display.flip()

    def shutdown(self):
        if self.character is not None and self.net.connected:
            self.autosave()
        self.net.close()
        self._stop_server()
        self.running = False

    def run(self):
        while self.running:
            dt = min(self.clock.tick(S.FPS) / 1000.0, 1 / 30)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.shutdown()
                else:
                    self.scene.handle_event(e)
            if not self.running:
                break
            self.pump(dt)
            self.scene.update(dt)
            self.draw()
        pygame.quit()
