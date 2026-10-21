"""World rendering. Everything is drawn with shapes: no external assets needed."""
import math
import pygame
from . import settings as S
from .combat import Projectile
from .enemy import DEFEATED


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.Font(None, 22)
        self.font_big = pygame.font.Font(None, 30)
        self.sky = pygame.Surface((S.SCREEN_W, S.SCREEN_H))
        for y in range(S.SCREEN_H):
            t = y / S.SCREEN_H
            pygame.draw.line(self.sky, (int(40 + 90 * t), int(70 + 110 * t), int(130 + 90 * t)),
                             (0, y), (S.SCREEN_W, y))

    def draw_background(self, cam_x):
        self.screen.blit(self.sky, (0, 0))
        layers = [(0.15, (88, 110, 150), 300, 60, 180), (0.35, (60, 90, 110), 360, 45, 120)]
        for factor, color, base, amp, wave in layers:
            pts = [(0, S.SCREEN_H)]
            for x in range(0, S.SCREEN_W + 41, 40):
                wx = x + cam_x * factor
                pts.append((x, base - amp * (0.5 + 0.5 * math.sin(wx / wave))))
            pts.append((S.SCREEN_W, S.SCREEN_H))
            pygame.draw.polygon(self.screen, color, pts)

    def draw_world(self, game):
        cam, scr = game.camera, self.screen
        self._draw_exit(game.exit_rect, cam)
        ground = cam.apply(pygame.Rect(0, S.GROUND_Y, S.LEVEL_WIDTH, S.SCREEN_H - S.GROUND_Y))
        pygame.draw.rect(scr, (70, 52, 38), ground)
        pygame.draw.rect(scr, (80, 150, 70), (ground.x, ground.y, ground.w, 8))
        for p in game.platforms[1:]:
            r = cam.apply(p)
            if r.right < 0 or r.left > S.SCREEN_W:
                continue
            pygame.draw.rect(scr, (120, 120, 135), r)
            pygame.draw.rect(scr, (170, 170, 185), (r.x, r.y, r.w, 4))
        for d in game.pickups:
            r = cam.apply(d.rect)
            if d.kind == "coin":
                pygame.draw.circle(scr, (250, 210, 60), r.center, 8)
                pygame.draw.circle(scr, (190, 150, 20), r.center, 8, 2)
            elif d.kind == "item":
                c = d.value.color
                pts = [(r.centerx, r.top - 2), (r.right + 2, r.centery), (r.centerx, r.bottom + 2), (r.left - 2, r.centery)]
                pygame.draw.polygon(scr, c, pts)
                pygame.draw.polygon(scr, (255, 255, 255), pts, 2)
            else:
                pygame.draw.circle(scr, (220, 60, 80), r.center, 9)
                pygame.draw.rect(scr, (255, 255, 255), (r.centerx - 5, r.centery - 2, 10, 4))
                pygame.draw.rect(scr, (255, 255, 255), (r.centerx - 2, r.centery - 5, 4, 10))
        for e in game.enemies:
            self._draw_enemy(e, cam)
        self._draw_player(game.player, cam)
        for a in game.attacks:
            if not a.active:
                continue
            if isinstance(a, Projectile):
                pygame.draw.ellipse(scr, a.color, cam.apply(a.rect))
            else:
                s = pygame.Surface(a.rect.size, pygame.SRCALPHA)
                s.fill((*a.color, 90))
                scr.blit(s, cam.apply(a.rect))

    def _body(self, rect, color, facing, alpha=255):
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        w, h = rect.size
        pygame.draw.rect(surf, color, (0, h // 4, w, h - h // 4), border_radius=6)
        pygame.draw.circle(surf, color, (w // 2, h // 5), max(8, w // 3))
        eye_x = w // 2 + facing * (w // 6)
        pygame.draw.circle(surf, (255, 255, 255), (eye_x, h // 5 - 2), 3)
        surf.set_alpha(alpha)
        self.screen.blit(surf, rect.topleft)

    def _draw_player(self, p, cam):
        r = cam.apply(p.rect)
        if not p.alive:
            return
        color = (255, 255, 255) if p.flash > 0 else p.character.class_def.color
        if p.dodge_t > 0:
            alpha = 110
        elif p.invuln > 0 and int(p.invuln * 16) % 2 == 0:
            alpha = 120
        else:
            alpha = 255
        self._body(r, color, p.facing, alpha)
        if p.buffs:
            pygame.draw.ellipse(self.screen, (255, 225, 100), r.inflate(16, 12), 2)
        # sword
        sx = r.right if p.facing > 0 else r.left
        swing = p.attack is not None and not p.attack.finished
        end = (sx + p.facing * (34 if swing else 14), r.centery - (6 if swing else 18))
        pygame.draw.line(self.screen, (220, 220, 230), (sx, r.centery), end, 4)
        if p.character.class_def.name == "Mage":
            pygame.draw.circle(self.screen, (255, 140, 60), end, 6)

    def _draw_enemy(self, e, cam):
        r = cam.apply(e.rect)
        if r.right < -50 or r.left > S.SCREEN_W + 50:
            return
        color = e.cfg["color"]
        if e.flash > 0:
            color = (255, 255, 255)
        elif e.telegraphing:
            color = tuple(min(255, c + 70) for c in color)
        alpha = max(0, int(255 * (1 - e.state_t))) if e.state == DEFEATED else 255
        self._body(r, color, e.facing, alpha)
        if e.telegraphing:
            txt = self.font_big.render("!", True, (255, 240, 120))
            self.screen.blit(txt, (r.centerx - 4, r.top - 40))
        if e.alive and (e.hp < e.max_hp):
            bw = max(40, r.w)
            bar = pygame.Rect(r.centerx - bw // 2, r.top - 14, bw, 6)
            pygame.draw.rect(self.screen, (40, 20, 20), bar)
            pygame.draw.rect(self.screen, (210, 60, 60), (bar.x, bar.y, int(bw * e.hp / e.max_hp), 6))
            pygame.draw.rect(self.screen, (0, 0, 0), bar, 1)

    def _draw_exit(self, rect, cam):
        r = cam.apply(rect)
        if r.right < -20 or r.left > S.SCREEN_W + 20:
            return
        pygame.draw.rect(self.screen, (90, 90, 110), r, border_radius=8)
        inner = r.inflate(-16, -16)
        pygame.draw.ellipse(self.screen, (120, 200, 255), inner)
        pygame.draw.ellipse(self.screen, (220, 245, 255), inner.inflate(-20, -30))
        txt = self.font.render("EXIT", True, (255, 255, 255))
        self.screen.blit(txt, txt.get_rect(center=(r.centerx, r.top - 14)))
