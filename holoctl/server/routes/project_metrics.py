"""Per-project Metrics tab route."""
from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..jinja import render
from ..views.metrics import metrics_context
from ..filters import (
    apply_filter,
    available_filter_options,
    build_chip_remove_urls,
    build_preset_urls,
    filter_to_query_string,
    parse_filter_from_query,
)
from .project_board import _PROJECT_TABS

router = APIRouter()


def _project_breadcrumbs(project: dict, label: str) -> list[dict]:
    return [
        {"label": "holoctl", "href": "/"},
        {"label": project["name"], "href": f"/project/{project['alias']}/board"},
        {"label": label},
    ]


@router.get("/project/{alias}/metrics", response_class=HTMLResponse)
def project_metrics(alias: str, request: Request):
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
    all_tickets = board.ls()

    # Parse filter from URL query params.
    qp: dict[str, list[str]] = {}
    for k, v in request.query_params.multi_items():
        qp.setdefault(k, []).append(v)
    f = parse_filter_from_query(qp)

    # Derive options BEFORE filtering (so we show all available options).
    options = available_filter_options(all_tickets)

    # Apply filter to get the analysis set.
    tickets = apply_filter(all_tickets, f)

    ctx = metrics_context(tickets, since_days=f.get("since_days", 30))  # type: ignore[arg-type]

    base_url = f"/project/{alias}/metrics"

    return render(
        "project/metrics.html",
        title=project["name"],
        current_alias=alias,
        current_tab="metrics",
        breadcrumbs=_project_breadcrumbs(project, "Metrics"),
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        # Filter context for toolbar.
        metrics_filter=f,
        filter_options=options,
        filter_qs=filter_to_query_string(f),
        chip_remove_urls=build_chip_remove_urls(f),
        preset_urls=build_preset_urls(f),
        base_url=base_url,
        is_workspace=False,
        **ctx,
    )
