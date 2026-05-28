from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..jinja import render
from ..views.board import board_context
from ..views.list import list_context
from ..views.tree import tree_context

router = APIRouter()

_VALID_VIEWS = {"kanban", "list", "tree"}

_PROJECT_TABS = [
    {"id": "board", "label": "Board"},
    {"id": "repos", "label": "Repos"},
    {"id": "agents", "label": "Agents"},
    {"id": "commands", "label": "Commands"},
    {"id": "context", "label": "Context"},
    {"id": "metrics", "label": "Metrics"},
]


@router.get("/project/{alias}/board", response_class=HTMLResponse)
def project_board(alias: str, view: str = "kanban"):
    # Lazy import: project lookup helpers live in projects.py.
    from ..projects import get_project
    from ...lib.board import Board

    project = get_project(alias)
    if not project:
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Not found")),
            status_code=404,
        )
    if view not in _VALID_VIEWS:
        view = "kanban"

    board = Board(Path(project["path"]), project["config"])
    tickets = board.ls()
    statuses = project["config"]["board"]["statuses"]

    ctx = board_context(project, tickets, project["config"], view=view)
    if view == "list":
        ctx.update(list_context(tickets, statuses, alias))
    elif view == "tree":
        ctx.update(tree_context(tickets, alias))

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
        **ctx,
    )


@router.get("/api/project/{alias}/board-html", response_class=HTMLResponse)
def api_board_html(alias: str):
    """Kanban fragment for the SSE board-update swap."""
    from ..projects import get_project
    from ...lib.board import Board

    project = get_project(alias)
    if not project:
        return HTMLResponse(render("partials/_empty_state.html", msg="Project not found"), status_code=404)
    board = Board(Path(project["path"]), project["config"])
    tickets = board.ls()
    ctx = board_context(project, tickets, project["config"], view="kanban")
    return HTMLResponse(render("partials/board/_kanban.html", **ctx))


@router.get("/api/project/{alias}/list-html", response_class=HTMLResponse)
def api_list_html(alias: str):
    """List view fragment for SSE swap. Mirrors api_board_html for list mode."""
    from ..projects import get_project
    from ...lib.board import Board

    project = get_project(alias)
    if not project:
        return HTMLResponse(render("partials/_empty_state.html", msg="Project not found"), status_code=404)
    board = Board(Path(project["path"]), project["config"])
    tickets = board.ls()
    statuses = project["config"]["board"]["statuses"]
    ctx = list_context(tickets, statuses, alias)
    return HTMLResponse(render("partials/board/_list.html", **ctx))


