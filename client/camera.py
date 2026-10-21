import pygame


class Camera:
    """Horizontal-follow camera, clamped to the level bounds."""

    def __init__(self, level_width: int, screen_w: int):
        self.level_width = level_width
        self.screen_w = screen_w
        self.x = 0.0

    def update(self, target: pygame.Rect, dt: float, snap: bool = False):
        goal = target.centerx - self.screen_w / 2
        goal = max(0, min(goal, self.level_width - self.screen_w))
        self.x = goal if snap else self.x + (goal - self.x) * min(1.0, 8.0 * dt)

    def apply(self, rect: pygame.Rect) -> pygame.Rect:
        return rect.move(-round(self.x), 0)
