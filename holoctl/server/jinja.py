"""Jinja2 environment for the dashboard.

`autoescape=True` replaces the manual `_e()` calls scattered through the old
string-based renderer — any value interpolated into a template is escaped
unless wrapped in `{% autoescape false %}` or marked `| safe`.

Filters registered here are the cross-template helpers (date formatting,
avatar initials/hue). View-specific transforms live in `views/` modules.
"""
from __future__ import annotations
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .views.avatars import initials, avatar_hue
from .views.dates import format_relative_date

_TPL_DIR = Path(__file__).parent / "templates"

env = Environment(
    loader=FileSystemLoader(str(_TPL_DIR)),
    autoescape=select_autoescape(["html", "svg"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

env.filters["initials"] = initials
env.filters["avatar_hue"] = avatar_hue
env.filters["rel_date"] = format_relative_date


def render(name: str, **ctx) -> str:
    """Render a template by name (relative to `templates/`)."""
    return env.get_template(name).render(**ctx)
