"""View shaper for the per-project Metrics tab.

Wraps the pure ``holoctl.lib.metrics`` functions and produces a template-ready
dict.  All mutable business logic stays in ``metrics.py``; this module is only
a thin presenter — rounding, slicing, SVG-geometry pre-computation.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Literal, Sequence

from ...lib import metrics as _m

# Maximum items to surface in WIP list and by-group tables.
_WIP_TOP_N = 20
_GROUP_TOP_N = 20

# Stale threshold for stalled detection (active tickets with no updates).
_STALE_DAYS_DEFAULT = 5

# When the since_days range exceeds this threshold, switch to weekly buckets
# for the throughput overlay (daily buckets become 1000+ rects above this).
_DAILY_BUCKET_MAX_DAYS = 180

# Statuses that are "active" (doing / review) — tickets should be moving here.
_ACTIVE_STATUSES: frozenset[str] = frozenset({"doing", "review"})
# Statuses that are terminal (done, cancelled).
_TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "cancelled"})


def stalled_view(
    tickets: list[dict],
    *,
    now: datetime | None = None,
    stale_days: int = _STALE_DAYS_DEFAULT,
    project_alias: str = "",
) -> dict:
    """Identify tickets that are stalled and explain why.

    A ticket is "stalled" if ANY of:
    - It is in an active status (doing/review) AND its ``updated`` timestamp is
      more than *stale_days* old (aging — work started but not progressing).
    - It is in ``backlog`` AND has no ``agent`` assigned (orphaned).
    - It is in ``backlog`` AND has no ``priority`` set (or priority is empty/None).
    - It is ``done`` but ``completed`` is null (data hygiene — shouldn't happen
      post-Task B but worth catching).

    Parameters
    ----------
    tickets:
        Raw ticket dicts as returned by ``Board.ls()``.
    now:
        Reference time.  Defaults to ``datetime.now(timezone.utc)``.
    stale_days:
        Threshold for active-status stale detection.
    project_alias:
        Alias used to build per-ticket detail links.  When empty, falls back to
        each ticket's ``_source_alias`` field (workspace-rolled tickets); if
        that is also absent, links use ``/board/{id}`` (relative).

    Returns
    -------
    ::

        {
            "count": int,
            "tickets": [
                {
                    "id": str,
                    "title": str,
                    "status": str,
                    "age_days": float,
                    "reasons": [str, ...],
                    "link": str,
                },
                ...  # sorted by age_days descending
            ],
            "is_empty": bool,
        }
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    def _age(updated: str | None) -> float:
        dt = _m._parse_ts(updated)
        if dt is None:
            return 0.0
        return max(0.0, (now - dt).total_seconds() / 86400.0)  # type: ignore[operator]

    items: list[dict] = []

    for t in tickets:
        status = t.get("status", "")
        if status in _TERMINAL_STATUSES and status != "done":
            continue  # cancelled etc — skip entirely

        reasons: list[str] = []
        age_days = _age(t.get("updated"))

        if status in _ACTIVE_STATUSES:
            if age_days > stale_days:
                reasons.append(f"no update in {math.floor(age_days)}d (threshold {stale_days}d)")

        elif status == "backlog":
            agents = t.get("agent") or []
            if isinstance(agents, str):
                agents = [agents] if agents else []
            if not agents:
                reasons.append("no agent assigned")
            priority = t.get("priority") or ""
            if not priority:
                reasons.append("no priority set")

        elif status == "done":
            if not t.get("completed"):
                reasons.append("done status but completed timestamp is missing")

        if not reasons:
            continue

        # Build the detail link.
        tid = t.get("id", "")
        if project_alias:
            link = f"/project/{project_alias}/board/{tid}"
        elif t.get("_source_alias"):
            link = f"/project/{t['_source_alias']}/board/{tid}"
        else:
            link = f"/board/{tid}"

        items.append(
            {
                "id": tid,
                "title": t.get("title", ""),
                "status": status,
                "age_days": round(age_days, 1),
                "reasons": reasons,
                "link": link,
            }
        )

    items.sort(key=lambda x: x["age_days"], reverse=True)

    return {
        "count": len(items),
        "tickets": items,
        "is_empty": len(items) == 0,
    }


def _arrow(delta_pct: float | None, *, lower_is_better: bool = False) -> str:
    """Return "up", "down", or "flat" based on *delta_pct*.

    When *lower_is_better* is True (e.g. cycle time, stale count), the color
    logic is inverted: "up" means bad, "down" means good.  The arrow string
    itself still reflects the direction; the template is responsible for
    applying colour.
    """
    if delta_pct is None:
        return "flat"
    if delta_pct > 1.0:
        return "up"
    if delta_pct < -1.0:
        return "down"
    return "flat"


def _kpi_label(value: float | int | None, *, unit: str = "", delta_pct: float | None = None) -> str:
    """Build a one-liner display string like "47" or "47 (↑12%)"."""
    if value is None:
        return "—"
    val_str = f"{value}{unit}"
    if delta_pct is None:
        return val_str
    sign = "↑" if delta_pct > 0 else ("↓" if delta_pct < 0 else "→")
    return f"{val_str} ({sign}{abs(delta_pct):.1f}%)"


def _since_label(since_days: int, since_preset: str | None = None) -> str:
    """Return a human-readable label for the since window.

    Used in the KPI band header so "Throughput 9999d" never shows when the
    preset is "all".
    """
    preset = since_preset or ""
    if preset == "all":
        return "All time"
    if preset == "7d":
        return "7 days"
    if preset == "30d" or (not preset and since_days == 30):
        return "30 days"
    if preset == "90d":
        return "90 days"
    if preset == "sprint":
        return "Sprint"
    if preset == "custom":
        # since_days was computed from a custom ISO date; back-derive date from now
        # We don't have `now` here, so just show the day count.
        return f"since ({since_days}d)"
    # Fallback: show the day count directly.
    return f"{since_days} days"


def metrics_context(
    tickets: list[dict],
    *,
    since_days: int = 30,
    since_preset: str | None = None,
    now: datetime | None = None,
    active_statuses: Sequence[str] | None = None,
    activity_events: list[dict] | None = None,
    project_alias: str = "",
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
    activity_events:
        Pre-loaded ``ticket.moved`` events from
        ``holoctl.lib.metrics.read_activity_events()``.  When ``None`` the
        time-in-status and flow-efficiency surfaces are computed over an empty
        event list (graceful empty state).

    Returns
    -------
    Dict with keys:
        ``throughput``              – ``{"days": [...buckets], "max_count": int}``
        ``cycle``                   – ``{"count", "mean", "median", "p95"}`` (rounded)
        ``wip_view``                – ``{"count", "stale_count", "stale_days", "tickets": [...top N]}``
        ``by_agent``                – list of group rows (top N by completed)
        ``by_project``              – same, keyed on "projects"
        ``since_days``              – passed through for display
        ``since_label``             – human-readable label for the since window
        ``throughput_bucket``       – "day" or "week" (auto-selected based on range)
        ``kpis``                    – executive KPI band dict
        ``time_in_status_view``     – per-status totals + bottleneck pointer
        ``cycle_dist``              – histogram + percentiles for cycle time
        ``trend_throughput_overlay``– paired series (current + prev period)
    """
    if now is None:
        now = datetime.now(timezone.utc)

    active = tuple(active_statuses) if active_statuses is not None else ("doing", "review")
    since = now - timedelta(days=since_days)
    events = activity_events if activity_events is not None else []

    # ── Throughput ────────────────────────────────────────────────────────────
    # Auto-switch to weekly buckets when the range is long to avoid thousands
    # of tiny SVG rects that are invisible and slow to render.
    throughput_bucket: Literal["day", "week"] = "week" if since_days > _DAILY_BUCKET_MAX_DAYS else "day"
    raw_days = _m.throughput(tickets, bucket=throughput_bucket, since=since, now=now)
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
    raw_wip = _m.wip(tickets, active_statuses=active, now=now, stale_days=_STALE_DAYS_DEFAULT)
    wip_items = raw_wip["items"][:_WIP_TOP_N]
    wip_view = {
        "count": raw_wip["count"],
        "stale_count": raw_wip["stale_count"],
        "stale_days": _STALE_DAYS_DEFAULT,
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

    # ── F2: Trend ─────────────────────────────────────────────────────────────
    raw_trend = _m.trend(tickets, since=since, until=now, now=now)
    trend_delta = raw_trend["delta_pct"]

    # ── F2: Cycle distribution ────────────────────────────────────────────────
    cycle_dist = _m.cycle_time_distribution(tickets)

    # ── F2: Time-in-status ────────────────────────────────────────────────────
    raw_tis = _m.time_in_status(tickets, events, now=now)

    # ── F2: Flow efficiency ───────────────────────────────────────────────────
    raw_fe = _m.flow_efficiency(raw_tis)
    fe_ratio = raw_fe["ratio"]
    fe_pct = round(fe_ratio * 100, 1) if fe_ratio is not None else None

    # ── F2: Backlog size for forecast ─────────────────────────────────────────
    backlog_statuses = {"backlog", "todo"}
    backlog_size = sum(1 for t in tickets if t.get("status", "") in backlog_statuses)

    # Use weekly buckets for forecast.
    raw_weekly = _m.throughput(tickets, bucket="week", now=now)
    raw_fc = _m.forecast(raw_weekly, backlog_size=backlog_size, now=now)

    # ── F2: KPI band ──────────────────────────────────────────────────────────
    # Throughput delta polarity: up = good (green).
    thrput_arrow = _arrow(trend_delta)
    # Cycle time delta: down = good (lower is better).
    cycle_p50_val = cycle_dist["p50"]
    cycle_p95_val = cycle_dist["p95"]

    # Build paired overlay series for trend chart: current vs previous period.
    # existing throughput() uses `now` as the upper bound so we pass now=now for current,
    # and now=since for the previous period (so it ends at `since`).
    # Use the same smart bucket (day vs week) as the main throughput series.
    trend_current_buckets = _m.throughput(tickets, bucket=throughput_bucket, since=since, now=now)
    prev_since = since - timedelta(days=since_days)
    trend_prev_buckets = _m.throughput(tickets, bucket=throughput_bucket, since=prev_since, now=since)
    trend_throughput_overlay = {
        "current": trend_current_buckets,
        "previous": trend_prev_buckets,
        "current_total": raw_trend["current"],
        "previous_total": raw_trend["previous"],
        "delta_pct": trend_delta,
    }

    # ── F3: Stalled tickets ───────────────────────────────────────────────────
    stalled = stalled_view(tickets, now=now, project_alias=project_alias)

    kpis = {
        # Throughput 30d
        "throughput_30d_count": raw_trend["current"],
        "throughput_30d_previous": raw_trend["previous"],
        "throughput_30d_delta_pct": trend_delta,
        "throughput_30d_arrow": thrput_arrow,
        "throughput_30d_arrow_good": thrput_arrow == "up",
        "throughput_30d_label": _kpi_label(raw_trend["current"], delta_pct=trend_delta),
        # Cycle p50
        "cycle_p50": cycle_p50_val if raw_cycle["count"] > 0 else None,
        "cycle_p50_label": f"{cycle_p50_val}d" if raw_cycle["count"] > 0 else "—",
        # Cycle p95
        "cycle_p95": cycle_p95_val if raw_cycle["count"] > 0 else None,
        "cycle_p95_label": f"{cycle_p95_val}d" if raw_cycle["count"] > 0 else "—",
        # WIP
        "wip_count": raw_wip["count"],
        "wip_label": str(raw_wip["count"]),
        # Stale count (up = bad)
        "stale_count": raw_wip["stale_count"],
        "stale_label": str(raw_wip["stale_count"]),
        # Flow efficiency
        "flow_efficiency_ratio": fe_ratio,
        "flow_efficiency_pct": fe_pct,
        "flow_efficiency_label": f"{fe_pct}%" if fe_pct is not None else "—",
        # Forecast
        "forecast_weeks_to_clear": raw_fc["weeks_to_clear"],
        "forecast_eta": raw_fc["eta"],
        "forecast_weekly_rate": raw_fc["weekly_rate"],
        "forecast_label": (
            f"{raw_fc['weeks_to_clear']}w" if raw_fc["weeks_to_clear"] is not None else "—"
        ),
        # Bottleneck
        "bottleneck": raw_tis["bottleneck"],
        # Has data flag
        "has_flow_data": bool(events),
    }

    return {
        "throughput": throughput_view,
        "cycle": cycle_view,
        "wip_view": wip_view,
        "by_agent": _round_rows(by_agent),
        "by_project": _round_rows(by_project),
        "agent_max": agent_max,
        "project_max": project_max,
        "since_days": since_days,
        "since_label": _since_label(since_days, since_preset),
        "throughput_bucket": throughput_bucket,
        # F2 additions
        "kpis": kpis,
        "time_in_status_view": raw_tis,
        "cycle_dist": cycle_dist,
        "trend_throughput_overlay": trend_throughput_overlay,
        # F3 additions
        "stalled_view": stalled,
    }
