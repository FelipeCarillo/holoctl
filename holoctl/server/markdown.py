"""Markdown rendering for the dashboard.

Replaces the hand-rolled `_render_markdown` that used to live in `app.py`.
`strip_empty_sections` drops `# Header` blocks whose body is only
placeholder hints (parenthetical text, empty checklist items, HTML
comments) so template-only tickets render clean.
"""
from __future__ import annotations

import re

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

_PLACEHOLDER_PATTERNS = (
    re.compile(r"^\([^)]*\)\s*$"),
    re.compile(r"^[-*]\s*\[\s*[xX ]?\s*\]\s+\([^)]*\)\s*$"),
    re.compile(r"^<!--.*-->\s*$"),
)

_md = MarkdownIt("gfm-like", {"linkify": False}).use(tasklists_plugin, enabled=True)


def _is_placeholder_only(content: str) -> bool:
    real = [line.strip() for line in content.splitlines() if line.strip()]
    if not real:
        return False
    return all(any(p.match(line) for p in _PLACEHOLDER_PATTERNS) for line in real)


def strip_empty_sections(body: str) -> str:
    """Remove heading sections whose content is only placeholder hints."""
    parts = re.split(r"^(# .+)$", body, flags=re.MULTILINE)
    if len(parts) <= 1:
        return body
    out = [parts[0]]
    i = 1
    while i < len(parts):
        header = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""
        if not _is_placeholder_only(content):
            out.append(header)
            out.append(content)
        i += 2
    return "".join(out)


def render_markdown(body: str) -> str:
    """Render a markdown string to HTML, stripping placeholder-only sections."""
    body = strip_empty_sections(body)
    if not body.strip():
        return '<span class="detail-empty">No description</span>'
    return _md.render(body)
