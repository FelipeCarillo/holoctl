from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..jinja import render
from ..views.board import board_context

router = APIRouter()

_VALID_VIEWS = {"kanban", "list", "timeline", "tree"}

_PROJECT_TABS = [
    {"id": "board", "label": "Board"},
    {"id": "repos", "label": "Repos"},
    {"id": "agents", "label": "Agents"},
    {"id": "commands", "label": "Commands"},
    {"id": "context", "label": "Context"},
]


@router.get("/project/{alias}/board", response_class=HTMLResponse)
def project_board(alias: str, view: str = "kanban"):
    # Lazy import: app.py still owns project lookup + the non-kanban view
    # renderers (_list_html, _timeline_html, _tree_html). PRs #4 and #5
    # replace those with Jinja-powered presenters.
    from ..app import (
        _get_project, _not_found_html,
        _list_html, _timeline_html, _tree_html,
    )
    from ...lib.board import Board

    project = _get_project(alias)
    if not project:
        return HTMLResponse(
            render("base.html", title="Not Found", content=_not_found_html()),
            status_code=404,
        )
    if view not in _VALID_VIEWS:
        view = "kanban"

    board = Board(Path(project["path"]), project["config"])
    tickets = board.ls()
    statuses = project["config"]["board"]["statuses"]

    body_html = ""
    if view == "list":
        body_html = _list_html(tickets, statuses, alias)
    elif view == "timeline":
        body_html = _timeline_html(tickets, statuses, alias)
    elif view == "tree":
        body_html = _tree_html(tickets, statuses, alias)

    ctx = board_context(project, tickets, project["config"], view=view)
    return render(
        "project/board.html",
        title=project["name"],
        current_alias=alias,
        current_tab="board",
        breadcrumbs=[
            {"label": "holoctl", "href": "/"},
            {"label": project["name"], "href": f"/project/{alias}/board"},
            {"label": "Board"},
        ],
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        actions='<span class="live-indicator"><span class="pulse"></span>LIVE</span>',
        body_html=body_html,
        **ctx,
    )


@router.get("/api/project/{alias}/board-html", response_class=HTMLResponse)
def api_board_html(alias: str):
    """Kanban fragment for the SSE board-update swap."""
    from ..app import _get_project, _not_found_html
    from ...lib.board import Board

    project = _get_project(alias)
    if not project:
        return HTMLResponse(_not_found_html("Project not found"), status_code=404)
    board = Board(Path(project["path"]), project["config"])
    tickets = board.ls()
    ctx = board_context(project, tickets, project["config"], view="kanban")
    return HTMLResponse(render("partials/board/_kanban.html", **ctx))
