"""Headless integration tests: real Game object, dummy video driver."""
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from client import settings as S
from client.enemy import Enemy
from client.game import Game

DT = 1 / 60


@pytest.fixture
def game():
    g = Game(rng=random.Random(1))
    yield g
    import pygame
    pygame.quit()


def test_player_kills_enemy_and_gains_xp(game):
    S.ENEMY_TYPES["grunt"]["drop_chance"]  # config exists
    game.enemies = [Enemy("grunt", game.player.rect.centerx + 70)]
    for _ in range(1500):
        game.step(DT, 0, {"light"})
        if game.player.progression.xp:
            break
    assert game.player.progression.xp == 20
    assert game.player.alive


def test_enemy_damages_player(game):
    game.enemies = [Enemy("grunt", game.player.rect.centerx + 60)]
    for _ in range(180):
        game.step(DT, 0, set())
    assert game.player.hp < game.player.max_hp


def test_level_up_through_game_flow(game):
    game.player.progression.add_xp(95)
    game.enemies = [Enemy("grunt", game.player.rect.centerx + 70)]
    for _ in range(1500):
        game.step(DT, 0, {"light"})
        if game.player.progression.level == 2:
            break
    p = game.player
    assert p.progression.level == 2 and p.max_hp == 132 and p.hp == p.max_hp


def test_player_death_and_respawn(game):
    p = game.player
    p.hp = 1
    game.enemies = [Enemy("brute", p.rect.centerx + 70)]
    died = False
    for _ in range(600):
        game.step(DT, 0, set())
        if not p.alive:
            died = True
            break
    assert died
    for _ in range(200):
        game.step(DT, 0, set())
    assert p.alive and p.hp == p.max_hp


def test_defeated_enemy_respawns(game):
    game.enemies = [Enemy("grunt", 2000)]
    e = game.enemies[0]
    e.take_damage(10_000, 1, 0)
    game._reward(e)
    game.player.px = 100
    for _ in range(int((S.ENEMY_RESPAWN_TIME + 3) * 60)):
        game.step(DT, 0, set())
    assert len(game.enemies) == 1 and game.enemies[0].alive


def test_draw_and_pause_menu_do_not_crash(game):
    game.draw()
    game.paused = True
    game.draw()
    game.reset()
    assert game.player.progression.level == 1
