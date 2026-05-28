"""Workspace-level metrics rollup route — GET /metrics."""
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
from ...lib import metrics as _m
from ...lib.metrics import read_activity_events

router = APIRouter()


def _workspace_breadcrumbs() -> list[dict]:
    return [
        {"label": "holoctl", "href": "/"},
        {"label": "Workspace metrics"},
    ]


def _by_workspace_project(all_tickets: list[dict]) -> list[dict]:
    """Per-source-project breakdown for the cross-project comparison block.

    Each ticket carries a ``_source_alias`` field injected by the route to
    identify which project it came from.  Returns rows sorted by completed
    descending.
    """
    from statistics import mean as _mean

    alias_completed: dict[str, int] = {}
    alias_cycle_secs: dict[str, list[float]] = {}
    alias_wip: dict[str, int] = {}
    active_statuses = {"doing", "review"}

    for t in all_tickets:
        src = t.get("_source_alias", "?")
        alias_completed.setdefault(src, 0)
        alias_cycle_secs.setdefault(src, [])
        alias_wip.setdefault(src, 0)

        status = t.get("status", "")
        completed_dt = _m._parse_ts(t.get("completed"))
        created_dt = _m._parse_ts(t.get("created"))

        if status == "done" and completed_dt is not None:
            alias_completed[src] += 1
            if created_dt is not None:
                delta = (completed_dt - created_dt).total_seconds()
                alias_cycle_secs[src].append(delta)
        if status in active_statuses:
            alias_wip[src] += 1

    all_keys = set(alias_completed) | set(alias_wip)
    rows: list[dict] = []
    for src in all_keys:
        cyc = alias_cycle_secs.get(src, [])
        avg_cycle = round(_mean(cyc) / 86400.0, 1) if cyc else None
        rows.append({
            "alias": src,
            "completed": alias_completed.get(src, 0),
            "avg_cycle_days": avg_cycle,
            "wip": alias_wip.get(src, 0),
        })

    rows.sort(key=lambda r: r["completed"], reverse=True)
    return rows


@router.get("/metrics", response_class=HTMLResponse)
def workspace_metrics(request: Request):
    from ..projects import get_projects
    from ...lib.board import Board

    projects = get_projects(with_git=False)

    # Union tickets from every project, stamping _source_alias on each.
    all_tickets: list[dict] = []
    for p in projects:
        try:
            board = Board(Path(p["path"]), p["config"])
            for t in board.ls():
                all_tickets.append({**t, "_source_alias": p["alias"]})
        except Exception:
            pass

    # Parse filter from URL query params.
    qp: dict[str, list[str]] = {}
    for k, v in request.query_params.multi_items():
        qp.setdefault(k, []).append(v)
    f = parse_filter_from_query(qp)

    # Derive options BEFORE filtering so dropdowns show all available values.
    options = available_filter_options(all_tickets)

    # Apply filter to get the analysis set.
    tickets = apply_filter(all_tickets, f)

    # Load activity events for time-in-status / flow-efficiency — union across projects.
    all_activity_events: list[dict] = []
    for p in projects:
        try:
            all_activity_events.extend(read_activity_events(Path(p["path"])))
        except Exception:
            pass

    ctx = metrics_context(  # type: ignore[arg-type]
        tickets,
        since_days=f.get("since_days", 30),
        activity_events=all_activity_events,
    )

    # by_workspace_project runs AFTER apply_filter so it reflects the filter.
    by_ws_project = _by_workspace_project(tickets)
    project_max = max((r["completed"] for r in by_ws_project), default=0)

    base_url = "/metrics"

    return render(
        "metrics.html",
        title="Workspace metrics",
        breadcrumbs=_workspace_breadcrumbs(),
        tabs=None,
        actions="",
        by_ws_project=by_ws_project,
        ws_project_max=project_max,
        # Filter context for toolbar.
        metrics_filter=f,
        filter_options=options,
        filter_qs=filter_to_query_string(f),
        chip_remove_urls=build_chip_remove_urls(f),
        preset_urls=build_preset_urls(f),
        base_url=base_url,
        is_workspace=True,
        **ctx,
    )
