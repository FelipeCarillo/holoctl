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


def metrics_context(
    tickets: list[dict],
    *,
    since_days: int = 30,
    now: datetime | None = None,
    active_statuses: Sequence[str] | None = None,
    activity_events: list[dict] | None = None,
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
        ``wip_view``                – ``{"count", "stale_count", "tickets": [...top N]}``
        ``by_agent``                – list of group rows (top N by completed)
        ``by_project``              – same, keyed on "projects"
        ``since_days``              – passed through for display
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
    trend_current_buckets = _m.throughput(tickets, bucket="day", since=since, now=now)
    prev_since = since - timedelta(days=since_days)
    trend_prev_buckets = _m.throughput(tickets, bucket="day", since=prev_since, now=since)
    trend_throughput_overlay = {
        "current": trend_current_buckets,
        "previous": trend_prev_buckets,
        "current_total": raw_trend["current"],
        "previous_total": raw_trend["previous"],
        "delta_pct": trend_delta,
    }

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
        # F2 additions
        "kpis": kpis,
        "time_in_status_view": raw_tis,
        "cycle_dist": cycle_dist,
        "trend_throughput_overlay": trend_throughput_overlay,
    }
