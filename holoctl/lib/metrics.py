"""Productivity metrics over ticket dicts — pure functions, stdlib only.

All public functions accept a list of ticket dicts (as returned by
``Board.ls()``) and optional keyword arguments.  They have **no I/O** and
**no imports** from the rest of holoctl so they can be called from any
context (server view, CLI, tests) without side effects.

Ticket dict shape (relevant fields):
    id: str
    status: str                     e.g. "backlog", "doing", "review", "done"
    created: str | None             ISO-8601 UTC, e.g. "2026-05-27T14:03:11Z"
    updated: str | None             ISO-8601 UTC
    completed: str | None           ISO-8601 UTC; set iff status == "done"
    agent: list[str]                assignees (may be empty)
    projects: list[str]             project scopes (may be empty)
    kind: str                       "task", "spec", "story", …
    sprint: str | None
    priority: str                   "p0"…"p3"

Design notes
------------
- Inject ``now: datetime`` wherever "current time" matters so tests are
  deterministic.  Callers that want wall-clock time pass
  ``datetime.now(timezone.utc)``.
- p95 uses the **nearest-rank** method:
  ``rank = ceil(0.95 * n)``; the p95 value is ``sorted_values[rank - 1]``.
  For n=1 this correctly returns the single value.
- Week buckets are keyed by the **Monday** of the ISO week containing the
  completion date (matching the ISO 8601 week convention).
- "(unassigned)" is the sentinel bucket for tickets with an empty / missing
  list-valued group field.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Literal


# ── Internal timestamp helper ─────────────────────────────────────────────────


def _parse_ts(value: str | None) -> datetime | None:
    """Parse an ISO-8601 UTC string to a timezone-aware datetime.

    Handles the ``Z`` suffix produced by ``Board._now()`` as well as the
    ``+00:00`` form produced by Python's ``datetime.isoformat()``.  Returns
    ``None`` on any bad / missing input rather than raising, so callers can
    treat missing timestamps as "exclude this ticket."
    """
    if not value:
        return None
    try:
        # Normalise trailing Z → +00:00 so fromisoformat works on Python < 3.11.
        normalised = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalised)
    except (ValueError, AttributeError):
        return None


def _week_monday(d: date) -> date:
    """Return the Monday of the ISO week that contains *d*."""
    return d - timedelta(days=d.weekday())


def _day_key(dt: datetime) -> str:
    return dt.date().isoformat()  # "YYYY-MM-DD"


def _week_key(dt: datetime) -> str:
    return _week_monday(dt.date()).isoformat()  # "YYYY-MM-DD" of Monday


# ── throughput ────────────────────────────────────────────────────────────────


def throughput(
    tickets: list[dict],
    *,
    bucket: Literal["day", "week"] = "day",
    since: datetime | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Completed tickets grouped by date-bucket of their ``completed`` timestamp.

    Returns an **ordered** list of ``{"bucket": "<YYYY-MM-DD>", "count": int}``
    covering every bucket from *since* to *now* inclusive (empty buckets are
    filled with count 0 so charts have continuous bars).

    Parameters
    ----------
    tickets:
        Raw ticket dicts (e.g. from ``Board.ls()``).
    bucket:
        ``"day"`` groups by calendar day; ``"week"`` groups by ISO week
        (bucket key is the Monday of the week).
    since:
        Start of the window (inclusive).  Defaults to 30 days before *now*.
    now:
        Reference "current" time.  Defaults to ``datetime.now(timezone.utc)``.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if since is None:
        since = now - timedelta(days=30)

    # Ensure both ends are timezone-aware for comparison.
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    key_fn = _week_key if bucket == "week" else _day_key

    # --- build the full ordered bucket list (spine) -------------------------
    # Advance by 1 day or 1 week until we cover now.
    spine: list[str] = []
    cursor_date = since.date()
    if bucket == "week":
        cursor_date = _week_monday(cursor_date)
    end_date = now.date()

    step = timedelta(weeks=1) if bucket == "week" else timedelta(days=1)
    while cursor_date <= end_date:
        spine.append(cursor_date.isoformat())
        cursor_date += step

    # --- count completions per bucket ---------------------------------------
    counts: dict[str, int] = {k: 0 for k in spine}
    for t in tickets:
        completed_dt = _parse_ts(t.get("completed"))
        if completed_dt is None:
            continue
        if completed_dt < since or completed_dt > now:
            continue
        k = key_fn(completed_dt)
        if k in counts:
            counts[k] += 1
        # Tickets that parse fine but whose bucket key is not in spine
        # (e.g. a weekly bucket boundary shift) are silently ignored.

    return [{"bucket": k, "count": counts[k]} for k in spine]


# ── cycle_time ────────────────────────────────────────────────────────────────


def cycle_time(
    tickets: list[dict],
    *,
    unit: Literal["days"] = "days",
) -> dict:
    """Cycle-time statistics over done tickets that have both timestamps.

    Only tickets with **both** a parseable ``created`` and a parseable
    ``completed`` are included.  Duration = ``completed - created`` in
    fractional days.

    Returns
    -------
    ``{"count": int, "mean": float, "median": float, "p95": float}``

    p95 uses the nearest-rank method: ``rank = ceil(0.95 * n)`` and the
    result is ``sorted_durations[rank - 1]``.  For ``count == 0`` all floats
    are 0.0.
    """
    durations: list[float] = []
    for t in tickets:
        created_dt = _parse_ts(t.get("created"))
        completed_dt = _parse_ts(t.get("completed"))
        if created_dt is None or completed_dt is None:
            continue
        delta = (completed_dt - created_dt).total_seconds()
        if unit == "days":
            durations.append(delta / 86400.0)

    n = len(durations)
    if n == 0:
        return {"count": 0, "mean": 0.0, "median": 0.0, "p95": 0.0}

    sorted_d = sorted(durations)
    rank = math.ceil(0.95 * n)
    rank = max(1, min(rank, n))  # clamp to [1, n]

    return {
        "count": n,
        "mean": statistics.mean(durations),
        "median": statistics.median(durations),
        "p95": sorted_d[rank - 1],
    }


# ── wip ───────────────────────────────────────────────────────────────────────


def wip(
    tickets: list[dict],
    *,
    active_statuses: tuple[str, ...] = ("doing", "review"),
    stale_days: float = 5,
    now: datetime | None = None,
) -> dict:
    """Work-In-Progress snapshot.

    Parameters
    ----------
    tickets:
        Raw ticket dicts.
    active_statuses:
        Only tickets whose ``status`` is in this tuple are included.
    stale_days:
        Tickets whose ``updated`` timestamp is more than *stale_days* old
        (i.e. ``age_days > stale_days``) are flagged as stale.
    now:
        Reference time.  Defaults to ``datetime.now(timezone.utc)``.

    Returns
    -------
    ::

        {
            "count": int,
            "stale_count": int,
            "items": [
                {"id": str, "status": str, "age_days": float, "stale": bool},
                ...
            ]
        }

    Items are sorted by ``age_days`` descending (oldest first).
    Tickets with a missing or unparseable ``updated`` timestamp are excluded.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    active_set = set(active_statuses)
    items: list[dict] = []

    for t in tickets:
        if t.get("status") not in active_set:
            continue
        updated_dt = _parse_ts(t.get("updated"))
        if updated_dt is None:
            continue
        age_days = (now - updated_dt).total_seconds() / 86400.0
        age_days = round(age_days, 4)
        stale = age_days > stale_days
        items.append(
            {
                "id": t["id"],
                "status": t["status"],
                "age_days": age_days,
                "stale": stale,
            }
        )

    items.sort(key=lambda x: x["age_days"], reverse=True)
    stale_count = sum(1 for item in items if item["stale"])

    return {
        "count": len(items),
        "stale_count": stale_count,
        "items": items,
    }


# ── by_group ──────────────────────────────────────────────────────────────────

_UNASSIGNED = "(unassigned)"


def by_group(
    tickets: list[dict],
    key: Literal["agent", "projects"],
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Aggregate metrics broken down by a list-valued grouping field.

    A ticket with multiple values in the group field (e.g. two agents)
    **contributes to each** group's count independently.  Tickets with an
    empty or missing group list fall into the ``"(unassigned)"`` bucket.

    Parameters
    ----------
    tickets:
        Raw ticket dicts.
    key:
        ``"agent"`` or ``"projects"`` — the list-valued field to group by.
    now:
        Reference time (used by :func:`wip` internally if extended later;
        kept for API consistency and future use).

    Returns
    -------
    Ordered list (by ``completed`` descending) of::

        {
            "group": str,
            "completed": int,
            "avg_cycle_days": float | None,
            "wip": int,
        }

    ``avg_cycle_days`` is ``None`` when the group has no done tickets with
    both ``created`` and ``completed`` timestamps.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Accumulate per-group stats.
    group_completed: dict[str, int] = {}
    group_cycle_secs: dict[str, list[float]] = {}
    group_wip: dict[str, int] = {}

    def _ensure(g: str) -> None:
        group_completed.setdefault(g, 0)
        group_cycle_secs.setdefault(g, [])
        group_wip.setdefault(g, 0)

    active_statuses = {"doing", "review"}

    for t in tickets:
        raw_groups: list[str] = t.get(key) or []
        groups = [g for g in raw_groups if g] or [_UNASSIGNED]

        completed_dt = _parse_ts(t.get("completed"))
        created_dt = _parse_ts(t.get("created"))
        status = t.get("status", "")
        is_active = status in active_statuses

        for g in groups:
            _ensure(g)
            if status == "done" and completed_dt is not None:
                group_completed[g] += 1
                if created_dt is not None:
                    delta_secs = (completed_dt - created_dt).total_seconds()
                    group_cycle_secs[g].append(delta_secs)
            if is_active:
                group_wip[g] += 1

    # Build result rows.
    all_groups = set(group_completed) | set(group_wip)
    rows: list[dict] = []
    for g in all_groups:
        _ensure(g)
        cycle_list = group_cycle_secs[g]
        if cycle_list:
            avg_cycle = statistics.mean(cycle_list) / 86400.0
        else:
            avg_cycle = None
        rows.append(
            {
                "group": g,
                "completed": group_completed[g],
                "avg_cycle_days": avg_cycle,
                "wip": group_wip[g],
            }
        )

    rows.sort(key=lambda r: r["completed"], reverse=True)
    return rows
