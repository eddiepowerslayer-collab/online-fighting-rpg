import pygame

BG = (22, 24, 36)
PANEL = (36, 40, 58)
EDGE = (74, 80, 110)
TEXT = (235, 235, 242)
DIM = (150, 155, 178)
GOLD = (250, 210, 60)
GREEN = (120, 230, 120)


def text(screen, font, s, pos, color=TEXT, center=False):
    img = font.render(s, True, color)
    r = img.get_rect()
    if center:
        r.center = pos
    else:
        r.topleft = pos
    screen.blit(img, r)
    return r


def wrap(font, s, width):
    lines, cur = [], ""
    for w in s.split():
        t = (cur + " " + w).strip()
        if font.size(t)[0] <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def panel(screen, rect, color=PANEL, edge=EDGE):
    pygame.draw.rect(screen, color, rect, border_radius=10)
    pygame.draw.rect(screen, edge, rect, 2, border_radius=10)


def bar(screen, rect, frac, fill):
    pygame.draw.rect(screen, (20, 20, 30), rect, border_radius=4)
    inner = pygame.Rect(rect.x, rect.y, int(rect.w * max(0.0, min(1.0, frac))), rect.h)
    pygame.draw.rect(screen, fill, inner, border_radius=4)
    pygame.draw.rect(screen, (0, 0, 0), rect, 2, border_radius=4)


class Button:
    def __init__(self, rect, label, on_click, enabled=True, sub="", selected=False,
                 badge="", color=TEXT, sub_color=DIM):
        self.rect = pygame.Rect(rect)
        self.label, self.on_click, self.enabled = label, on_click, enabled
        self.sub, self.selected, self.badge = sub, selected, badge
        self.color, self.sub_color = color, sub_color

    def draw(self, screen, fonts, mouse):
        hover = self.enabled and self.rect.collidepoint(mouse)
        fill = (34, 36, 48) if not self.enabled else (66, 74, 108) if hover else (48, 54, 82)
        pygame.draw.rect(screen, fill, self.rect, border_radius=10)
        edge = GOLD if self.selected else (110, 118, 150) if hover else EDGE
        pygame.draw.rect(screen, edge, self.rect, 3 if self.selected else 2, border_radius=10)
        c = self.color if self.enabled else (100, 104, 120)
        if self.sub:
            text(screen, fonts["m"], self.label, (self.rect.centerx, self.rect.centery - 11), c, True)
            text(screen, fonts["xs"], self.sub, (self.rect.centerx, self.rect.centery + 15),
                 self.sub_color if self.enabled else (90, 94, 110), True)
        else:
            text(screen, fonts["m"], self.label, self.rect.center, c, True)
        if self.badge:
            pygame.draw.circle(screen, (220, 60, 70), (self.rect.right - 6, self.rect.top + 6), 14)
            text(screen, fonts["xs"], self.badge, (self.rect.right - 6, self.rect.top + 6), (255, 255, 255), True)


class TextField:
    def __init__(self, rect, label="", text="", max_len=24, password=False, digits=False):
        self.rect = pygame.Rect(rect)
        self.label, self.text, self.max_len = label, text, max_len
        self.password, self.digits, self.focused = password, digits, False

    def handle_event(self, e):
        """Returns "submit" (Enter), "tab", or None."""
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.focused = self.rect.collidepoint(e.pos)
            return None
        if not self.focused or e.type != pygame.KEYDOWN:
            return None
        if e.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return "submit"
        elif e.key == pygame.K_TAB:
            return "tab"
        else:
            ch = getattr(e, "unicode", "")
            if ch and ch.isprintable() and len(self.text) < self.max_len and (ch.isdigit() or not self.digits):
                self.text += ch
        return None

    def draw(self, screen, fonts):
        if self.label:
            text(screen, fonts["xs"], self.label, (self.rect.x, self.rect.y - 18), DIM)
        pygame.draw.rect(screen, (18, 20, 30), self.rect, border_radius=6)
        pygame.draw.rect(screen, GOLD if self.focused else EDGE, self.rect, 2, border_radius=6)
        shown = "*" * len(self.text) if self.password else self.text
        if self.focused and int(pygame.time.get_ticks() / 450) % 2 == 0:
            shown += "|"
        screen.blit(fonts["m"].render(shown, True, TEXT), (self.rect.x + 10, self.rect.centery - 9))


class Screen:
    """Base scene: owns buttons, routes clicks, draws."""

    def __init__(self, game):
        self.game = game
        self.buttons = []

    fields = ()

    def on_submit(self):
        pass

    def handle_event(self, e):
        for i, f in enumerate(self.fields):
            r = f.handle_event(e)
            if r == "submit":
                self.on_submit()
                return
            if r == "tab":
                f.focused = False
                self.fields[(i + 1) % len(self.fields)].focused = True
                return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for b in list(self.buttons):
                if b.enabled and b.rect.collidepoint(e.pos):
                    b.on_click()
                    break

    def click(self, label):
        """Programmatic click (used by tests)."""
        for b in self.buttons:
            if b.label == label and b.enabled:
                b.on_click()
                return True
        return False

    def update(self, dt):
        pass

    def draw_buttons(self, screen):
        for f in self.fields:
            f.draw(screen, self.game.fonts)
        mouse = pygame.mouse.get_pos()
        for b in self.buttons:
            b.draw(screen, self.game.fonts, mouse)
