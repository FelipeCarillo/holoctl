"""Productivity metrics over ticket dicts — pure functions, stdlib only.

All public functions accept a list of ticket dicts (as returned by
``Board.ls()``) and optional keyword arguments.  They have **no I/O** and
**no imports** from the rest of holoctl so they can be called from any
context (server view, CLI, tests) without side effects.

I/O exception
-------------
``read_activity_events`` is the sole exception: it performs *read-only*
file I/O on ``.holoctl/activity.jsonl``.  It never writes.  All other
functions remain pure (no I/O, no side effects).

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

import json
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
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


# ── trend ─────────────────────────────────────────────────────────────────────


def trend(
    tickets: list[dict],
    *,
    since: datetime,
    until: datetime | None = None,
    prev_period: bool = True,
    now: datetime | None = None,
) -> dict:
    """Compare throughput in the current window against the previous equal-length window.

    The current window is ``[since, until)``.  When *until* is ``None`` it
    defaults to *now*.  The previous window is the equal-length interval
    immediately preceding *since*.

    Returns
    -------
    ::

        {
            "current": int,      # tickets completed in [since, until)
            "previous": int,     # tickets completed in prev window (0 if prev_period=False)
            "delta_pct": float | None,  # (current - previous) / previous * 100, or None when previous==0
        }
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    if until is None:
        until = now
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)

    window_len = until - since
    prev_since = since - window_len
    prev_until = since  # exclusive boundary

    current_count = 0
    previous_count = 0

    for t in tickets:
        completed_dt = _parse_ts(t.get("completed"))
        if completed_dt is None:
            continue
        if since <= completed_dt < until:
            current_count += 1
        if prev_period and prev_since <= completed_dt < prev_until:
            previous_count += 1

    if not prev_period:
        previous_count = 0

    delta_pct: float | None = None
    if prev_period and previous_count > 0:
        delta_pct = round((current_count - previous_count) / previous_count * 100.0, 1)

    return {
        "current": current_count,
        "previous": previous_count,
        "delta_pct": delta_pct,
    }


# ── cycle_time_distribution ───────────────────────────────────────────────────


def cycle_time_distribution(
    tickets: list[dict],
    *,
    bins: int = 10,
) -> dict:
    """Histogram + percentiles of cycle time for done tickets.

    Only tickets with **both** parseable ``created`` and ``completed``
    timestamps are included.

    Returns
    -------
    ::

        {
            "min": float,
            "max": float,
            "p50": float,
            "p75": float,
            "p95": float,
            "bins": [{"lo": float, "hi": float, "count": int}, ...]
        }

    When there are no qualifying tickets, all numeric fields are 0.0 and
    ``bins`` is an empty list.

    Percentiles use the nearest-rank method.
    """
    durations: list[float] = []
    for t in tickets:
        created_dt = _parse_ts(t.get("created"))
        completed_dt = _parse_ts(t.get("completed"))
        if created_dt is None or completed_dt is None:
            continue
        delta_days = (completed_dt - created_dt).total_seconds() / 86400.0
        durations.append(delta_days)

    n = len(durations)
    if n == 0:
        return {"min": 0.0, "max": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0, "bins": []}

    sorted_d = sorted(durations)

    def _percentile(p: float) -> float:
        rank = math.ceil(p * n)
        rank = max(1, min(rank, n))
        return round(sorted_d[rank - 1], 2)

    lo = sorted_d[0]
    hi = sorted_d[-1]

    # Build histogram bins across the full range [lo, hi].
    bin_count = max(1, bins)
    span = hi - lo
    histogram: list[dict]
    if span == 0.0:
        # All tickets have the same cycle time — single bin.
        histogram = [{"lo": round(lo, 2), "hi": round(hi, 2), "count": n}]
    else:
        width = span / bin_count
        histogram = []
        for i in range(bin_count):
            bin_lo = lo + i * width
            bin_hi = lo + (i + 1) * width
            # Last bin is closed on the right to include the max value.
            count = sum(
                1 for d in durations
                if bin_lo <= d < bin_hi or (i == bin_count - 1 and d == bin_hi)
            )
            histogram.append({"lo": round(bin_lo, 2), "hi": round(bin_hi, 2), "count": count})

    return {
        "min": round(lo, 2),
        "max": round(hi, 2),
        "p50": _percentile(0.50),
        "p75": _percentile(0.75),
        "p95": _percentile(0.95),
        "bins": histogram,
    }


# ── read_activity_events ──────────────────────────────────────────────────────


def read_activity_events(
    root: Path,
    *,
    since: datetime | None = None,
) -> list[dict]:
    """Read ``ticket.moved`` events from ``.holoctl/activity.jsonl``.

    I/O: reads one file; no writes, no network calls.

    Parameters
    ----------
    root:
        Project root directory (the directory that contains ``.holoctl/``).
    since:
        Optional lower bound on ``ts``.  Events with ``ts < since`` are
        excluded.  When ``None`` all events are returned.

    Returns
    -------
    A list of dicts, each with keys ``ts`` (datetime, tz-aware UTC),
    ``ticket`` (str), ``from`` (str), ``to`` (str).  Lines that cannot be
    parsed or lack required fields are silently skipped.

    Raises
    ------
    Nothing — a missing or unreadable file returns an empty list.
    """
    log_path = root / ".holoctl" / "activity.jsonl"
    if not log_path.exists():
        return []

    events: list[dict] = []
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "ticket.moved":
            continue
        ts_str = obj.get("ts")
        ts_dt = _parse_ts(ts_str)
        if ts_dt is None:
            continue
        ticket_id = obj.get("ticket")
        from_status = obj.get("from")
        to_status = obj.get("to")
        if not ticket_id or from_status is None or to_status is None:
            continue
        if since is not None:
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            if ts_dt < since:
                continue
        events.append({"ts": ts_dt, "ticket": ticket_id, "from": from_status, "to": to_status})

    return events


# ── time_in_status ────────────────────────────────────────────────────────────

_TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "cancelled"})


def time_in_status(
    tickets: list[dict],
    moved_events: list[dict],
    *,
    now: datetime | None = None,
) -> dict:
    """Compute time each ticket spent in each status, summed across the population.

    For each ticket the function walks its move history (sorted by ``ts``)
    to determine how long it occupied each status.  For the *current* status
    the open interval is ``now - last_move_ts``.

    Parameters
    ----------
    tickets:
        Raw ticket dicts.  The ``status`` field is the authoritative current
        status used for the open-ended interval calculation.
    moved_events:
        Events from :func:`read_activity_events` (or synthetic equivalents
        for tests).  Each event: ``{ts: datetime, ticket: str, from: str, to: str}``.
    now:
        Reference time.  Defaults to ``datetime.now(timezone.utc)``.

    Returns
    -------
    ::

        {
            "per_status": [
                {"status": str, "total_days": float, "ticket_count": int, "avg_days": float},
                ...  # sorted by total_days descending
            ],
            "bottleneck": str | None  # status with highest avg_days (non-terminal)
        }

    When *moved_events* is empty, returns ``{"per_status": [], "bottleneck": None}``.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if not moved_events:
        return {"per_status": [], "bottleneck": None}

    # Build a lookup for current ticket status.
    ticket_status: dict[str, str] = {t["id"]: t.get("status", "") for t in tickets}

    # Group events by ticket.
    by_ticket: dict[str, list[dict]] = {}
    for ev in moved_events:
        tid = ev["ticket"]
        by_ticket.setdefault(tid, []).append(ev)

    # Accumulators: total seconds and number of distinct tickets that passed through.
    status_secs: dict[str, float] = {}
    status_ticket_set: dict[str, set[str]] = {}

    for tid, evs in by_ticket.items():
        sorted_evs = sorted(evs, key=lambda e: e["ts"])

        # Walk the move history computing intervals.
        for i, ev in enumerate(sorted_evs):
            from_st = ev["from"]
            interval_start = ev["ts"]
            if interval_start.tzinfo is None:
                interval_start = interval_start.replace(tzinfo=timezone.utc)

            # The interval in `from_st` ends when the ticket moves again.
            if i + 1 < len(sorted_evs):
                interval_end = sorted_evs[i + 1]["ts"]
            else:
                # Last move: interval in `to` status ends at `now` if still there.
                to_st = ev["to"]
                current = ticket_status.get(tid, "")
                if current == to_st:
                    interval_end = now
                else:
                    # Status has changed beyond our log — skip open interval.
                    interval_end = None

            # Accumulate time in `from_st` for this segment.
            # (The from_st interval ended when this move happened.)
            # Actually: we accumulate the time spent in from_st *before* this event.
            # The first event tells us from_status ended at ev["ts"].
            # We don't know when the ticket entered from_status from the events alone,
            # but since we process all events, consecutive events chain correctly.
            # Correct approach: for each move, the 'from' status interval is
            # [prev_event.ts, this_event.ts]; for the first event we don't have
            # a start anchor so we skip (we only know it was there).
            # For final status open interval: [last_event.ts, now] in 'to' status.
            _ = from_st  # from_st interval without start anchor — handled below

            # Accumulate the `to` status open/closed interval.
            to_st = ev["to"]
            if interval_end is not None:
                if interval_end.tzinfo is None:
                    interval_end = interval_end.replace(tzinfo=timezone.utc)
                secs = max(0.0, (interval_end - interval_start).total_seconds())
                status_secs[to_st] = status_secs.get(to_st, 0.0) + secs
                status_ticket_set.setdefault(to_st, set()).add(tid)

    # Build per-status rows, excluding terminal statuses for bottleneck detection.
    rows: list[dict] = []
    for st, total_secs in status_secs.items():
        ticket_count = len(status_ticket_set.get(st, set()))
        total_days = round(total_secs / 86400.0, 3)
        avg_days = round(total_days / ticket_count, 3) if ticket_count > 0 else 0.0
        rows.append({
            "status": st,
            "total_days": total_days,
            "ticket_count": ticket_count,
            "avg_days": avg_days,
        })

    rows.sort(key=lambda r: r["total_days"], reverse=True)

    # Bottleneck: non-terminal status with highest avg_days.
    bottleneck: str | None = None
    best_avg = -1.0
    for r in rows:
        if r["status"] not in _TERMINAL_STATUSES and r["avg_days"] > best_avg:
            best_avg = r["avg_days"]
            bottleneck = r["status"]

    return {"per_status": rows, "bottleneck": bottleneck}


# ── flow_efficiency ───────────────────────────────────────────────────────────


def flow_efficiency(
    time_in_status_result: dict,
    *,
    active_statuses: tuple[str, ...] = ("doing",),
) -> dict:
    """Ratio of value-add time vs waiting time across the ticket population.

    Active time is the time spent in *active_statuses*; total time is the
    sum across all non-terminal statuses (``done`` and ``cancelled`` are
    excluded because they represent completion, not flow).

    Parameters
    ----------
    time_in_status_result:
        The return value of :func:`time_in_status`.
    active_statuses:
        Statuses considered "value-add" (work is actively happening).
        Default: ``("doing",)``.

    Returns
    -------
    ::

        {"active_days": float, "total_days": float, "ratio": float | None}

    ``ratio = active_days / total_days``.  ``None`` when total_days == 0.
    """
    per_status = time_in_status_result.get("per_status", [])
    active_set = set(active_statuses)

    active_days = 0.0
    total_days = 0.0

    for row in per_status:
        st = row["status"]
        if st in _TERMINAL_STATUSES:
            continue
        total_days += row["total_days"]
        if st in active_set:
            active_days += row["total_days"]

    ratio: float | None = None
    if total_days > 0:
        ratio = round(active_days / total_days, 3)

    return {
        "active_days": round(active_days, 3),
        "total_days": round(total_days, 3),
        "ratio": ratio,
    }


# ── forecast ─────────────────────────────────────────────────────────────────


def forecast(
    throughput_buckets: list[dict],
    *,
    backlog_size: int,
    now: datetime | None = None,
) -> dict:
    """Estimate when the backlog will clear based on recent weekly throughput.

    Parameters
    ----------
    throughput_buckets:
        Output of :func:`throughput` (daily or weekly buckets).  If daily
        buckets are provided the function aggregates them into weeks internally.
        Each bucket: ``{"bucket": "YYYY-MM-DD", "count": int}``.
    backlog_size:
        Number of tickets remaining in backlog.
    now:
        Reference time.  Defaults to ``datetime.now(timezone.utc)``.

    Returns
    -------
    ::

        {
            "weekly_rate": float,   # mean tickets/week over last K full weeks
            "weeks_to_clear": int | None,
            "eta": str | None,      # ISO date of projected completion
        }

    Strategy: take up to K=4 recent full-week buckets (or equivalent weekly
    totals when daily buckets are given), compute the mean.  Zero rate or
    empty throughput → ``weekly_rate=0, weeks_to_clear=None, eta=None``.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not throughput_buckets or backlog_size <= 0:
        return {"weekly_rate": 0.0, "weeks_to_clear": None, "eta": None}

    # Aggregate daily buckets into weekly totals keyed by week-Monday.
    week_totals: dict[str, int] = {}
    for b in throughput_buckets:
        bucket_str = b.get("bucket", "")
        count = b.get("count", 0)
        try:
            d = date.fromisoformat(bucket_str)
        except (ValueError, TypeError):
            continue
        week_key = _week_monday(d).isoformat()
        week_totals[week_key] = week_totals.get(week_key, 0) + count

    if not week_totals:
        return {"weekly_rate": 0.0, "weeks_to_clear": None, "eta": None}

    # Take the last K=4 full weeks (exclude the current in-progress week).
    current_week_key = _week_monday(now.date()).isoformat()
    completed_weeks = sorted(
        (k for k in week_totals if k < current_week_key), reverse=True
    )

    K = 4
    sample = completed_weeks[:K]
    if not sample:
        # No completed weeks yet — fall back to all weeks including current.
        sample = sorted(week_totals.keys(), reverse=True)[:K]

    rates = [week_totals[k] for k in sample]
    weekly_rate = round(statistics.mean(rates), 2) if rates else 0.0

    if weekly_rate <= 0:
        return {"weekly_rate": 0.0, "weeks_to_clear": None, "eta": None}

    weeks_to_clear = math.ceil(backlog_size / weekly_rate)
    eta_date = now.date() + timedelta(weeks=weeks_to_clear)

    return {
        "weekly_rate": weekly_rate,
        "weeks_to_clear": weeks_to_clear,
        "eta": eta_date.isoformat(),
    }
