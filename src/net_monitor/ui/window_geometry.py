"""Logical-pixel placement; no DPI multipliers and no desktop-sized overlay."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains(self, other: Rect) -> bool:
        return (self.x <= other.x and self.y <= other.y
                and other.right <= self.right and other.bottom <= self.bottom)


def screen_for(rect: Rect, screens: tuple[Rect, ...]) -> Rect:
    if not screens:
        raise ValueError("No available screen geometry")
    def score(area: Rect) -> tuple[int, int]:
        overlap = max(0, min(rect.right, area.right) - max(rect.x, area.x)) * max(
            0, min(rect.bottom, area.bottom) - max(rect.y, area.y))
        dx = rect.x + rect.width // 2 - (area.x + area.width // 2)
        dy = rect.y + rect.height // 2 - (area.y + area.height // 2)
        return overlap, -(dx * dx + dy * dy)
    return max(screens, key=score)


def fit_rect(rect: Rect, screens: tuple[Rect, ...], *, snap: int = 0) -> Rect:
    area = screen_for(rect, screens)
    width, height = min(rect.width, area.width), min(rect.height, area.height)
    x = max(area.x, min(rect.x, area.right - width))
    y = max(area.y, min(rect.y, area.bottom - height))
    if abs(x - area.x) <= snap:
        x = area.x
    elif abs(x + width - area.right) <= snap:
        x = area.right - width
    if abs(y - area.y) <= snap:
        y = area.y
    elif abs(y + height - area.bottom) <= snap:
        y = area.bottom - height
    return Rect(x, y, width, height)


def place_card(anchor: Rect, size: tuple[int, int], screens: tuple[Rect, ...], gap: int = 6) -> Rect:
    area = screen_for(anchor, screens)
    width, height = min(size[0], area.width), min(size[1], area.height)
    candidates = (
        Rect(anchor.right + gap, anchor.y, width, height),
        Rect(anchor.x - gap - width, anchor.y, width, height),
        Rect(anchor.x, anchor.bottom + gap, width, height),
        Rect(anchor.x, anchor.y - gap - height, width, height),
    )
    return next((candidate for candidate in candidates if area.contains(candidate)),
                fit_rect(candidates[0], (area,)))
