"""View shaper for the compact workspace summary band on the home page.

Computes three rolled-up stats across all projects using ``lib.metrics``
where it composes and plain sums elsewhere.  The shaper is pure (no I/O)
so it can be unit-tested directly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ...lib import metrics as _m


def workspace_summary(projects: list[dict]) -> dict:
    """Compute workspace-level summary stats from pre-loaded project dicts.

    Parameters
    ----------
    projects:
        List of project dicts as returned by ``get_projects()``.  Each must
        have a ``"counts"`` key with status-keyed ticket counts (from
        ``Board.stat()``).

    Returns
    -------
    ``{"total_wip": int, "last7_throughput": int, "stale_count": int}``

    ``total_wip`` — sum of tickets in active statuses ("doing" + "review")
    ``last7_throughput`` — sum of completed tickets from the last 7 days
    ``stale_count`` — total stale WIP items across all projects
    """
    total_wip = 0
    last7_throughput = 0
    stale_count = 0

    now = datetime.now(timezone.utc)
    since_7 = now - timedelta(days=7)

    for p in projects:
        counts = p.get("counts") or {}
        # WIP: doing + review from the stat snapshot.
        total_wip += int(counts.get("doing", 0)) + int(counts.get("review", 0))

        # last7 + stale require ticket-level data — use pre-loaded all_tickets
        # when available (projects enriched by the route), else fall back to 0.
        tickets: list[dict] = p.get("_tickets") or []
        if tickets:
            # last7 throughput via throughput() with 7-day window.
            buckets = _m.throughput(tickets, bucket="day", since=since_7, now=now)
            last7_throughput += sum(b["count"] for b in buckets)
            # Stale WIP via wip().
            wip_snap = _m.wip(tickets, now=now)
            stale_count += wip_snap["stale_count"]

    return {
        "total_wip": total_wip,
        "last7_throughput": last7_throughput,
        "stale_count": stale_count,
    }
