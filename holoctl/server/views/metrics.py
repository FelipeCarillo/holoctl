"""View shaper for the per-project Metrics tab.

Wraps the pure ``holoctl.lib.metrics`` functions and produces a template-ready
dict.  All mutable business logic stays in ``metrics.py``; this module is only
a thin presenter — rounding, slicing, SVG-geometry pre-computation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from ...lib import metrics as _m

# Maximum items to surface in WIP list and by-group tables.
_WIP_TOP_N = 10
_GROUP_TOP_N = 10


def metrics_context(
    tickets: list[dict],
    *,
    since_days: int = 30,
    now: datetime | None = None,
    active_statuses: Sequence[str] | None = None,
) -> dict:
    """Build a template-ready metrics dict from raw ticket dicts.

    Parameters
    ----------
    tickets:
        Raw ticket dicts as returned by ``Board.ls()``.
    since_days:
        Window width for throughput (calendar days back from *now*).
    now:
        Reference time.  Defaults to ``datetime.now(timezone.utc)``.
    active_statuses:
        WIP statuses.  Defaults to ``("doing", "review")``.

    Returns
    -------
    Dict with keys:
        ``throughput``  – ``{"days": [...buckets], "max_count": int}``
        ``cycle``       – ``{"count", "mean", "median", "p95"}`` (rounded)
        ``wip_view``    – ``{"count", "stale_count", "tickets": [...top N]}``
        ``by_agent``    – list of group rows (top N by completed)
        ``by_project``  – same, keyed on "projects"
        ``since_days``  – passed through for display
    """
    if now is None:
        now = datetime.now(timezone.utc)

    active = tuple(active_statuses) if active_statuses is not None else ("doing", "review")
    since = now - timedelta(days=since_days)

    # ── Throughput ────────────────────────────────────────────────────────────
    raw_days = _m.throughput(tickets, bucket="day", since=since, now=now)
    max_count = max((b["count"] for b in raw_days), default=0)
    throughput_view = {
        "days": raw_days,
        "max_count": max_count,
    }

    # ── Cycle time ────────────────────────────────────────────────────────────
    raw_cycle = _m.cycle_time(tickets)
    cycle_view = {
        "count": raw_cycle["count"],
        "mean": round(raw_cycle["mean"], 1),
        "median": round(raw_cycle["median"], 1),
        "p95": round(raw_cycle["p95"], 1),
    }

    # ── WIP ───────────────────────────────────────────────────────────────────
    raw_wip = _m.wip(tickets, active_statuses=active, now=now)
    wip_items = raw_wip["items"][:_WIP_TOP_N]
    wip_view = {
        "count": raw_wip["count"],
        "stale_count": raw_wip["stale_count"],
        "tickets": wip_items,
    }

    # ── By-group ──────────────────────────────────────────────────────────────
    by_agent = _m.by_group(tickets, "agent", now=now)[:_GROUP_TOP_N]
    by_project = _m.by_group(tickets, "projects", now=now)[:_GROUP_TOP_N]

    # Pre-compute max completed for normalising horizontal bars in the template.
    agent_max = max((r["completed"] for r in by_agent), default=0)
    project_max = max((r["completed"] for r in by_project), default=0)

    # Round avg_cycle_days for display.
    def _round_rows(rows: list[dict]) -> list[dict]:
        out = []
        for r in rows:
            acd = r["avg_cycle_days"]
            out.append({
                **r,
                "avg_cycle_days": round(acd, 1) if acd is not None else None,
            })
        return out

    return {
        "throughput": throughput_view,
        "cycle": cycle_view,
        "wip_view": wip_view,
        "by_agent": _round_rows(by_agent),
        "by_project": _round_rows(by_project),
        "agent_max": agent_max,
        "project_max": project_max,
        "since_days": since_days,
    }
