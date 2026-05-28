from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..jinja import render
from ..views.home import home_context

router = APIRouter()


def _enrich_with_tickets(projects: list[dict]) -> list[dict]:
    """Attach ``_tickets`` to each project dict for workspace summary stats.

    Uses ``with_git=False`` (cheaper) and silently skips projects that fail
    to load (same guard as workspace_metrics route).
    """
    from ...lib.board import Board

    enriched = []
    for p in projects:
        try:
            board = Board(Path(p["path"]), p["config"])
            enriched.append({**p, "_tickets": board.ls()})
        except Exception:
            enriched.append({**p, "_tickets": []})
    return enriched


@router.get("/", response_class=HTMLResponse)
def home():
    # Lazy import: app.py imports this router and we'd loop on import otherwise.
    from ..projects import get_projects
    projects = get_projects()
    enriched = _enrich_with_tickets(projects)
    return render(
        "home.html",
        title="Home",
        projects=enriched,
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": "Home"}],
        **home_context(enriched),
    )
