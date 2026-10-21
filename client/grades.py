"""Level grades. F 1-24, E 25-99, D 100-199, C 200-349, B 350-499, A 500-999,
S 1000-1999, God Tier 2000+ (the ranges you gave overlapped at 99/500; the lower
boundary of each higher grade wins)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Grade:
    short: str
    label: str
    low: int
    color: tuple


GRADES = (
    Grade("F", "F Grade", 1, (165, 165, 175)),
    Grade("E", "E Grade", 25, (110, 205, 110)),
    Grade("D", "D Grade", 100, (90, 160, 255)),
    Grade("C", "C Grade", 200, (70, 210, 200)),
    Grade("B", "B Grade", 350, (190, 110, 255)),
    Grade("A", "A Grade", 500, (255, 160, 60)),
    Grade("S", "S Grade", 1000, (255, 90, 90)),
    Grade("God", "God Tier", 2000, (255, 225, 100)),
)


def grade_for_level(level: int) -> Grade:
    found = GRADES[0]
    for g in GRADES:
        if level >= g.low:
            found = g
    return found
