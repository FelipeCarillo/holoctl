"""Card presenter: turns a `Board` ticket dict into the context the
`partials/board/_card.html` macros consume.

Lives here (not inside a template helper) so the same shape can power the
kanban card, the list row, the tree row, and the timeline row — each view
only renders different macros over the same context.
"""
from __future__ import annotations
from pathlib import Path


def card_context(t: dict, alias: str, *, project_root: Path | None = None) -> dict:
    """Normalize a ticket dict for the card macros.

    Pre-computes CSV variants used by `data-*` attributes (so the template
    doesn't carry joining logic), and resolves the optional first-line
    preview pulled from the ticket .md.
    """
    # Lazy import: _ticket_preview / _format_due still live in app.py until
    # the PR-10 cleanup. Avoids a circular import at module load.
    from ..app import _ticket_preview, _format_due

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
        "due": _format_due(t.get("due") or ""),
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
        "preview": _ticket_preview(project_root, t) if project_root else "",
    }
