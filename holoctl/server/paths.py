"""Shared path-safety helpers for the holoctl dashboard.

``_safe_resolve`` is imported by any route that needs to serve files from a
bounded directory root (context, agents, commands).  Centralising it here
ensures every caller uses the same traversal guard.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException


def safe_resolve(root: Path, name: str) -> Path:
    """Resolve ``root / name`` and assert it stays inside ``root``.

    Raises HTTP 403 on path-traversal attempts (``..`` etc.).
    """
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden")
    return candidate
