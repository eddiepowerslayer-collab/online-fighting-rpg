"""In-run HUD, death overlay and pause menu."""
import pygame
from .. import settings as S
from ..professions import CONSUMABLES
from ..skills import SKILLS_BY_ID
from .widgets import bar, text

PAUSE_ITEMS = ["Resume", "Retreat to Home", "Quit Game"]


def draw_hud(screen, run, f):
    p = run.player
    prog = p.progression
    panel = pygame.Surface((300, 118), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 130))
    screen.blit(panel, (10, 10))
    text(screen, f["m"], f"{p.class_name}  Lv {prog.level}", (20, 16))
    g = p.character.grade
    text(screen, f["xs"], g.label, (172, 20), g.color)
    text(screen, f["s"], f"Gold {p.character.gold}", (232, 20), (250, 210, 60))
    bar(screen, pygame.Rect(20, 42, 280, 20), p.hp / p.max_hp, (200, 50, 60))
    text(screen, f["s"], f"HP {p.hp}/{p.max_hp}", (26, 45))
    needed = prog.xp_needed
    bar(screen, pygame.Rect(20, 70, 280, 14), prog.xp / needed if needed else 1.0, (90, 170, 250))
    text(screen, f["s"], f"XP {prog.xp}/{needed}" if needed else "XP MAX", (24, 88))
    text(screen, f["s"], f"Stat pts {prog.stat_points}   Skill pts {prog.skill_points}", (20, 106), (200, 230, 200))
    text(screen, f["m"], f"Dungeon Level {run.level}", (S.SCREEN_W // 2, 22), (255, 255, 255), True)
    text(screen, f["xs"], "J/K/1-6 skills  Shift dodge  Q/E/R potions  Esc pause",
         (S.SCREEN_W - 470, 46), (230, 230, 230))
    _draw_buffs_and_skills(screen, run, f)
    y = S.SCREEN_H - 22
    for msg, color, ttl in reversed(list(run.messages)):
        fade = min(1.0, ttl)
        c = tuple(int(v * fade + 20 * (1 - fade)) for v in color)
        text(screen, f["s"], msg, (14, y), c)
        y -= 18
    for t in run.texts:
        pos = run.camera.apply(pygame.Rect(int(t.x), int(t.y), 1, 1))
        text(screen, f["m"], t.text, (pos.x - 8, pos.y), t.color)
    if run.level_up_flash > 0:
        text(screen, f["l"], "LEVEL UP!", (S.SCREEN_W // 2, 130), (255, 230, 90), True)


def draw_death(screen, f):
    shade = pygame.Surface((S.SCREEN_W, S.SCREEN_H), pygame.SRCALPHA)
    shade.fill((80, 0, 0, 120))
    screen.blit(shade, (0, 0))
    text(screen, f["l"], "YOU DIED", (S.SCREEN_W // 2, S.SCREEN_H // 2 - 10), (255, 220, 220), True)
    text(screen, f["m"], "Returning home...", (S.SCREEN_W // 2, S.SCREEN_H // 2 + 40), (255, 255, 255), True)


def draw_pause(screen, f, index):
    shade = pygame.Surface((S.SCREEN_W, S.SCREEN_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 170))
    screen.blit(shade, (0, 0))
    text(screen, f["l"], "PAUSED", (S.SCREEN_W // 2, 140), (255, 255, 255), True)
    for i, item in enumerate(PAUSE_ITEMS):
        sel = i == index
        text(screen, f["m"], ("> " if sel else "  ") + item, (S.SCREEN_W // 2, 230 + i * 44),
             (255, 230, 90) if sel else (210, 210, 210), True)
    text(screen, f["s"], "Up/Down + Enter   |   Esc resume", (S.SCREEN_W // 2, 410), (170, 170, 170), True)


def _draw_buffs_and_skills(screen, run, f):
    p, ch = run.player, run.character
    y = 134
    for name, b in p.buffs.items():
        text(screen, f["xs"], f"{name}  {b['time']:.0f}s", (14, y), (255, 230, 120))
        y += 16
    # hotbar (bottom right): whatever is bound to J, K and 1-6
    bar_items = p.hotbar()
    x = S.SCREEN_W - 10 - len(bar_items) * 60
    for it in bar_items:
        rect = pygame.Rect(x, S.SCREEN_H - 62, 56, 50)
        pygame.draw.rect(screen, (30, 32, 46), rect, border_radius=6)
        if it["cd"] > 0:
            h_ = int(rect.h * min(1.0, it["cd"] / max(0.01, it["max"])))
            shade = pygame.Surface((rect.w, h_), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 170))
            screen.blit(shade, rect.topleft)
        pygame.draw.rect(screen, (255, 225, 100) if it["god"] else (120, 130, 170), rect, 2, border_radius=6)
        text(screen, f["m"], it["key"], (rect.x + 6, rect.y + 2), (255, 255, 255))
        text(screen, f["xs"], it["name"][:8], (rect.x + 4, rect.y + 30), (200, 205, 225))
        if it["cd"] > 0:
            text(screen, f["s"], f"{it['cd']:.0f}", (rect.right - 16, rect.y + 6), (255, 200, 120))
        x += 60
    bar(screen, pygame.Rect(S.SCREEN_W - 250, S.SCREEN_H - 82, 230, 10), p.energy / p.max_energy, (90, 150, 240))
    parts = [f"{k}:{ch.consumables.get(n, 0)}" for k, n in zip("QER", CONSUMABLES)]
    text(screen, f["xs"], "Energy   Potions " + "  ".join(parts), (S.SCREEN_W - 250, S.SCREEN_H - 98), (200, 230, 200))
