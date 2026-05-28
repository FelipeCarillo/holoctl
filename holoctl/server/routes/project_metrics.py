"""Per-project Metrics tab route."""
from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..jinja import render
from ..views.metrics import metrics_context
from .project_board import _PROJECT_TABS

router = APIRouter()


def _project_breadcrumbs(project: dict, label: str) -> list[dict]:
    return [
        {"label": "holoctl", "href": "/"},
        {"label": project["name"], "href": f"/project/{project['alias']}/board"},
        {"label": label},
    ]


@router.get("/project/{alias}/metrics", response_class=HTMLResponse)
def project_metrics(alias: str):
    from ..projects import get_project
    from ...lib.board import Board

    project = get_project(alias)
    if not project:
        return HTMLResponse(
            render(
                "base.html",
                title="Not Found",
                content=render("partials/_empty_state.html", msg="Not found"),
            ),
            status_code=404,
        )

    board = Board(Path(project["path"]), project["config"])
    tickets = board.ls()
    ctx = metrics_context(tickets)

    return render(
        "project/metrics.html",
        title=project["name"],
        current_alias=alias,
        current_tab="metrics",
        breadcrumbs=_project_breadcrumbs(project, "Metrics"),
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        **ctx,
    )
