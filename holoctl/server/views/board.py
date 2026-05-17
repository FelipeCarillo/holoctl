"""Board presenter: groups tickets into kanban columns ready for the template."""
from __future__ import annotations
from pathlib import Path

from .card import card_context


def board_context(project: dict, tickets: list[dict], config: dict,
                  view: str = "kanban") -> dict:
    """Prep the board page context: header, controls, columns (for kanban view)."""
    alias = project["alias"]
    name = project.get("name") or alias
    path_display = project.get("path", "")
    project_root = Path(path_display) if path_display else None
    statuses = config["board"]["statuses"]

    columns = []
    if view == "kanban":
        for status in statuses:
            col_tickets = [t for t in tickets if t["status"] == status]
            columns.append({
                "status": status,
                "tickets": [card_context(t, alias, project_root=project_root)
                            for t in col_tickets],
                "count": len(col_tickets),
            })

    return {
        "project_name": name,
        "project_path": path_display,
        "alias": alias,
        "view": view,
        "columns": columns,
        "statuses": statuses,
    }
