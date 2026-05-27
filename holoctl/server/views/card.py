"""Card presenter: turns a `Board` ticket dict into the context the
`partials/board/_card.html` macros consume.

Lives here (not inside a template helper) so the same shape can power the
kanban card, the list row, the tree row, and the timeline row — each view
only renders different macros over the same context.
"""
from __future__ import annotations
import re
from pathlib import Path

from ..markdown import strip_empty_sections
from ...lib.markdown import parse_frontmatter


def format_due(due_iso: str) -> str:
    """Short due-date label like 'May 9' for ISO dates; empty if unparseable."""
    if not due_iso:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(due_iso))
    if not m:
        return ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        mo = int(m.group(2))
        day = int(m.group(3))
        return f"{months[mo - 1]} {day}"
    except (ValueError, IndexError):
        return ""


def ticket_preview(project_root: Path, ticket: dict, max_chars: int = 80) -> str:
    """First non-trivial prose line from a ticket .md, for the kanban card preview.

    Strips frontmatter, drops empty/placeholder sections, then walks the body
    looking for the first line that isn't a header, blank, list marker, or
    HTML comment. Returns "" gracefully when the ticket body is template-only.
    """
    rel = ticket.get("file")
    if not rel:
        return ""
    # `ticket["file"]` is stored relative to `.holoctl/board/` (e.g.
    # `tickets/HOL-001-foo.md`). Resolve from there; fall back to a path
    # treated as workspace-relative for older indices that may have stored it
    # differently.
    candidates = [
        project_root / ".holoctl" / "board" / rel,
        project_root / rel,
    ]
    md_path = next((p for p in candidates if p.exists()), None)
    if md_path is None:
        return ""
    try:
        raw = md_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    _, body = parse_frontmatter(raw)
    body = strip_empty_sections(body)
    in_html_comment = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Multi-line HTML comments — skip until close.
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue
        if line.startswith("<!--"):
            if "-->" not in line:
                in_html_comment = True
            continue
        # Markdown structural lines.
        if line.startswith("#") or line.startswith("---"):
            continue
        # List / checkbox markers — skip the marker but keep substantive text.
        m = re.match(r"^(?:[-*+]\s*(?:\[[ xX]\]\s+)?|\d+\.\s+)(.*)$", line)
        if m:
            line = m.group(1).strip()
            if not line:
                continue
        # Skip parenthetical placeholder hints.
        if re.match(r"^\([^)]*\)\s*$", line):
            continue
        # Strip basic markdown emphasis / inline code for the preview.
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        if len(line) > max_chars:
            line = line[: max_chars - 1].rstrip() + "…"
        return line
    return ""


def card_context(t: dict, alias: str, *, project_root: Path | None = None) -> dict:
    """Normalize a ticket dict for the card macros.

    Pre-computes CSV variants used by `data-*` attributes (so the template
    doesn't carry joining logic), and resolves the optional first-line
    preview pulled from the ticket .md.
    """
    agents_list = [a for a in (t.get("agent") or []) if a]
    projects_list = [p for p in (t.get("projects") or []) if p]
    depends_list = [d for d in (t.get("depends") or []) if d]
    tags_list = list(t.get("tags") or [])

    return {
        "id": t["id"],
        "title": t.get("title", ""),
        "status": t.get("status", "backlog"),
        "priority": t.get("priority", "p2"),
        "sprint": t.get("sprint") or "",
        "kind": t.get("kind") or "task",
        "parent": t.get("parent") or "",
        "due": format_due(t.get("due") or ""),
        "created": t.get("created", ""),
        "updated": t.get("updated", ""),
        "alias": alias,
        "agents": agents_list,
        "agents_csv": ",".join(agents_list),
        "projects": projects_list,
        "projects_csv": ",".join(projects_list),
        "depends": depends_list,
        "depends_csv": ",".join(depends_list),
        "tags": tags_list,
        "tags_csv": ",".join(tags_list),
        "source_provider": t.get("source_provider") or "",
        "source_ref": t.get("source_ref") or "",
        "source_url": t.get("source_url") or "",
        "source_label": t.get("source_label") or "",
        "preview": ticket_preview(project_root, t) if project_root else "",
    }
