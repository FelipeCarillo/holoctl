from __future__ import annotations
import re

AVATAR_HUE_COUNT = 6


def initials(name: str) -> str:
    """Two-character uppercase glyph for an avatar circle."""
    if not name:
        return "?"
    parts = re.split(r"[\s\-_./]+", name.strip())
    parts = [p for p in parts if p]
    if not parts:
        return name.strip()[:2].upper()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[1][:1]).upper()


def avatar_hue(name: str) -> int:
    """Deterministic 0..5 hue index — same name always lands the same color."""
    if not name:
        return 0
    return sum(ord(c) for c in name) % AVATAR_HUE_COUNT
