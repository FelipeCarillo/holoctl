from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..jinja import render
from ..views.detail import detail_context
from .project_board import _PROJECT_TABS

router = APIRouter()


def _build_detail_ctx(alias: str, ticket_id: str) -> tuple[dict, dict] | None:
    """Load project + ticket and build the detail view context.

    Returns ``(project, ctx)`` or None when either is missing. Shared by the
    full detail page and the SSE swap fragment so both render identically.
    """
    from ..projects import get_project
    from ...lib.board import Board
    from ...lib.markdown import parse_frontmatter

    project = get_project(alias)
    if not project:
        return None

    project_root = Path(project["path"])
    board = Board(project_root, project["config"])
    ticket = board.get(ticket_id)
    if not ticket:
        return None

    ticket_file = project_root / ".holoctl" / "board" / ticket["file"]
    if ticket_file.exists():
        _, body = parse_frontmatter(ticket_file.read_text(encoding="utf-8"))
    else:
        body = ""

    all_tickets = board.ls()
    ctx = detail_context(
        ticket, body, alias,
        all_tickets=all_tickets,
        project_root=project_root,
        statuses=project["config"]["board"]["statuses"],
    )
    return project, ctx


@router.get("/project/{alias}/board/{ticket_id}", response_class=HTMLResponse)
def project_ticket(alias: str, ticket_id: str):
    built = _build_detail_ctx(alias, ticket_id)
    if not built:
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Not found")),
            status_code=404,
        )
    project, ctx = built

    return render(
        "project/detail.html",
        title=f"{ticket_id} — {project['name']}",
        current_alias=alias,
        current_tab="board",
        breadcrumbs=[
            {"label": "holoctl", "href": "/"},
            {"label": project["name"], "href": f"/project/{alias}/board"},
            {"label": "Board", "href": f"/project/{alias}/board"},
            {"label": ticket_id},
        ],
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        **ctx,
    )


@router.get("/api/project/{alias}/board/{ticket_id}/detail-html", response_class=HTMLResponse)
def api_detail_html(alias: str, ticket_id: str):
    """Detail fragment for the SSE detail-page swap (mirrors api_board_html)."""
    built = _build_detail_ctx(alias, ticket_id)
    if not built:
        return HTMLResponse(render("partials/_empty_state.html", msg="Ticket not found"), status_code=404)
    _project, ctx = built
    return HTMLResponse(render("partials/detail/_content.html", **ctx))
