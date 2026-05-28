"""URL-driven filter model for the metrics pages.

This module is deliberately import-cheap — only stdlib.  FastAPI is not
imported here; callers pass a plain ``dict[str, list[str]]`` that they
extract from ``request.query_params.multi_items()`` (or equivalent).

Filter semantics
----------------
- **Date filter** (``since`` / ``until``) is applied to ``created``.
  This means "tickets created in this window" form the analysis set.
  The ``throughput`` function applies its own internal ``completed``-based
  bucketing on top — we pass ``f.since_dt`` through to it so the chart
  spans the same window.  ``cycle_time`` and ``by_group`` operate on
  whatever tickets survive the filter and need no extra date argument.
- **Multi-value fields** (``tags``, ``kinds``, ``statuses``, ``agents``,
  ``projects``, ``sprints``, ``priorities``) are AND-ed across field
  boundaries (a ticket must match ALL active filters), but OR-ed within a
  single field (it only needs to match ONE active value).
- An empty filter set for a field = that field is not constrained.
- Unknown/garbage values are silently ignored during parsing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TypedDict
from urllib.parse import urlencode


# ── Filter model ─────────────────────────────────────────────────────────────


class MetricsFilter(TypedDict, total=False):
    """Parsed, validated filter state from URL query params.

    All fields are optional.  Absent keys mean "no constraint on that field."
    """

    since: datetime | None         # lower bound on `created`
    until: datetime | None         # upper bound on `created` (inclusive)
    since_preset: str               # original preset string for UI state
    since_days: int                 # numeric width (used by throughput)
    tags: set[str]
    kinds: set[str]
    statuses: set[str]
    agents: set[str]
    projects: set[str]
    sprints: set[str]
    priorities: set[str]


# ── Internal helpers ──────────────────────────────────────────────────────────


def _parse_ts(value: str | None) -> datetime | None:
    """Parse an ISO-8601 UTC string to a tz-aware datetime (silent on errors)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _multi_values(raw: list[str]) -> set[str]:
    """Flatten repeated params + comma-separated values into a lowercased set."""
    out: set[str] = set()
    for item in raw:
        for part in item.split(","):
            v = part.strip().lower()
            if v:
                out.add(v)
    return out


# ── Public API ────────────────────────────────────────────────────────────────


_PRESET_DAYS: dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "all": 0,
}

_PRESET_DEFAULT = "30d"


def parse_filter_from_query(
    qp: dict[str, list[str]] | list[tuple[str, str]],
    *,
    now: datetime | None = None,
) -> MetricsFilter:
    """Parse URL query params into a :class:`MetricsFilter`.

    *qp* may be:
    - A ``dict[str, list[str]]`` — already grouped by key.
    - A list of ``(key, value)`` tuples — as returned by FastAPI's
      ``request.query_params.multi_items()``.

    Date presets
    ~~~~~~~~~~~~
    ``since=7d``   → 7 calendar days back from *now*
    ``since=30d``  → 30 days (default when absent)
    ``since=90d``  → 90 days
    ``since=sprint`` → alias for 14 days (typical sprint window)
    ``since=all``  → no lower bound
    ``since=<ISO date>``  → explicit date (parsed as midnight UTC)

    Multi-valued fields accept repeated keys (``?tags=a&tags=b``) and
    comma-separated values (``?tags=a,b``).  Values are lowercased.
    Unknown values are silently ignored.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Normalise input to dict[str, list[str]].
    if isinstance(qp, list):
        grouped: dict[str, list[str]] = {}
        for k, v in qp:
            grouped.setdefault(k, []).append(v)
        qp = grouped

    # ── Date / since ─────────────────────────────────────────────────────────
    raw_since_list = qp.get("since", [])
    raw_since = raw_since_list[0].strip() if raw_since_list else _PRESET_DEFAULT
    if not raw_since:
        raw_since = _PRESET_DEFAULT

    since: datetime | None
    until: datetime | None = None
    since_days: int = 30

    if raw_since in _PRESET_DAYS:
        days = _PRESET_DAYS[raw_since]
        if days == 0:
            since = None  # "all" — no lower bound
            since_days = 9999
        else:
            since = now - timedelta(days=days)
            since_days = days
        since_preset = raw_since
    elif raw_since == "sprint":
        since = now - timedelta(days=14)
        since_days = 14
        since_preset = "sprint"
    else:
        # Try ISO date / datetime.
        parsed = _parse_ts(raw_since + "T00:00:00Z") if len(raw_since) == 10 else _parse_ts(raw_since)
        if parsed is not None:
            since = parsed
            since_preset = "custom"
            since_days = max(1, int((now - parsed).days) + 1)
        else:
            # Unrecognised → fall back to default 30d.
            since = now - timedelta(days=30)
            since_days = 30
            since_preset = _PRESET_DEFAULT

    # Optional until (custom upper bound; mostly unused but complete).
    raw_until_list = qp.get("until", [])
    if raw_until_list:
        raw_until = raw_until_list[0].strip()
        parsed_until = (
            _parse_ts(raw_until + "T23:59:59Z") if len(raw_until) == 10 else _parse_ts(raw_until)
        )
        if parsed_until is not None:
            until = parsed_until

    # ── Multi-value fields ────────────────────────────────────────────────────
    tags = _multi_values(qp.get("tags", []))
    kinds = _multi_values(qp.get("kind", []) + qp.get("kinds", []))
    statuses = _multi_values(qp.get("status", []) + qp.get("statuses", []))
    agents = _multi_values(qp.get("agent", []) + qp.get("agents", []))
    projects = _multi_values(qp.get("project", []) + qp.get("projects", []))
    sprints = _multi_values(qp.get("sprint", []) + qp.get("sprints", []))
    priorities = _multi_values(qp.get("priority", []) + qp.get("priorities", []))

    return MetricsFilter(
        since=since,
        until=until,
        since_preset=since_preset,
        since_days=since_days,
        tags=tags,
        kinds=kinds,
        statuses=statuses,
        agents=agents,
        projects=projects,
        sprints=sprints,
        priorities=priorities,
    )


def apply_filter(
    tickets: list[dict],
    f: MetricsFilter,
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Return the subset of *tickets* that match every active filter criterion.

    Date filter
    -----------
    ``f["since"]`` and ``f["until"]`` are tested against the ticket's
    ``created`` field.  Tickets with a missing/unparseable ``created`` are
    **excluded** when ``since`` is set (we can't confirm they're in window).

    Multi-field AND / intra-field OR
    ---------------------------------
    A ticket passes if, for every field with active values, the ticket's
    value for that field overlaps with the active set.  Across fields the
    constraints are AND-ed.

    Example: ``kinds={"task"}, agents={"alice"}`` → ticket must be kind
    "task" AND have alice in its agent list.

    Empty filter = pass-through
    ---------------------------
    A filter with no active values for a field imposes no constraint on
    that field.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    since: datetime | None = f.get("since")  # type: ignore[assignment]
    until: datetime | None = f.get("until")  # type: ignore[assignment]
    tags: set[str] = f.get("tags", set())  # type: ignore[assignment]
    kinds: set[str] = f.get("kinds", set())  # type: ignore[assignment]
    statuses: set[str] = f.get("statuses", set())  # type: ignore[assignment]
    agents: set[str] = f.get("agents", set())  # type: ignore[assignment]
    projects: set[str] = f.get("projects", set())  # type: ignore[assignment]
    sprints: set[str] = f.get("sprints", set())  # type: ignore[assignment]
    priorities: set[str] = f.get("priorities", set())  # type: ignore[assignment]

    out: list[dict] = []
    for t in tickets:
        # ── Date range on `created` ──────────────────────────────────────────
        if since is not None or until is not None:
            created_dt = _parse_ts(t.get("created"))
            if since is not None:
                if created_dt is None or created_dt < since:
                    continue
            if until is not None:
                if created_dt is None or created_dt > until:
                    continue

        # ── Scalar fields ─────────────────────────────────────────────────────
        if kinds:
            if (t.get("kind") or "").lower() not in kinds:
                continue
        if statuses:
            if (t.get("status") or "").lower() not in statuses:
                continue
        if priorities:
            if (t.get("priority") or "").lower() not in priorities:
                continue

        # ── sprint (scalar or list) ───────────────────────────────────────────
        if sprints:
            ticket_sprint = t.get("sprint")
            if ticket_sprint is None:
                continue
            if isinstance(ticket_sprint, list):
                if not any(str(s).lower() in sprints for s in ticket_sprint):
                    continue
            else:
                if str(ticket_sprint).lower() not in sprints:
                    continue

        # ── tags (may be str CSV or list) ─────────────────────────────────────
        if tags:
            raw_tags = t.get("tags")
            if raw_tags is None:
                continue
            if isinstance(raw_tags, list):
                ticket_tags = {str(tg).lower() for tg in raw_tags}
            else:
                ticket_tags = {tg.strip().lower() for tg in str(raw_tags).split(",")}
            ticket_tags.discard("")
            if not tags & ticket_tags:
                continue

        # ── agents (list) ─────────────────────────────────────────────────────
        if agents:
            ticket_agents = {str(a).lower() for a in (t.get("agent") or [])}
            if not agents & ticket_agents:
                continue

        # ── projects (list) ───────────────────────────────────────────────────
        if projects:
            ticket_projects = {str(p).lower() for p in (t.get("projects") or [])}
            if not projects & ticket_projects:
                continue

        out.append(t)

    return out


def filter_to_query_string(
    f: MetricsFilter,
    *,
    exclude_field: str | None = None,
    exclude_value: str | None = None,
    override: dict[str, str] | None = None,
) -> str:
    """Build a query-string from *f*, optionally removing one value.

    Useful for "×" remove chips: call with ``exclude_field="tags",
    exclude_value="auth"`` to get the URL with that tag removed.

    ``override`` lets callers swap a single scalar field (e.g.
    ``{"since": "7d"}``).

    Returns a string like ``"since=7d&tags=auth&kind=task"`` (no leading ``?``).
    """
    params: list[tuple[str, str]] = []

    # ── since preset ─────────────────────────────────────────────────────────
    since_preset: str = f.get("since_preset", "30d") or "30d"  # type: ignore[assignment]
    if override and "since" in override:
        since_preset = override["since"]
    if exclude_field != "since":
        params.append(("since", since_preset))

    # ── multi-value fields ────────────────────────────────────────────────────
    multi_map: list[tuple[str, set[str]]] = [
        ("tags", f.get("tags", set())),  # type: ignore[arg-type]
        ("kind", f.get("kinds", set())),  # type: ignore[arg-type]
        ("status", f.get("statuses", set())),  # type: ignore[arg-type]
        ("agent", f.get("agents", set())),  # type: ignore[arg-type]
        ("project", f.get("projects", set())),  # type: ignore[arg-type]
        ("sprint", f.get("sprints", set())),  # type: ignore[arg-type]
        ("priority", f.get("priorities", set())),  # type: ignore[arg-type]
    ]

    for key, values in multi_map:
        for v in sorted(values):
            if exclude_field == key and exclude_value == v:
                continue
            params.append((key, v))

    return urlencode(params)


def build_chip_remove_urls(f: MetricsFilter) -> dict[str, str]:
    """Pre-compute remove-URLs for every active filter chip.

    Returns a dict keyed by ``"<field>:<value>"`` (e.g. ``"kind:task"``),
    with the corresponding query-string to use for a remove link.
    """
    out: dict[str, str] = {}
    multi_map: list[tuple[str, set[str]]] = [
        ("kind", f.get("kinds", set())),  # type: ignore[arg-type]
        ("status", f.get("statuses", set())),  # type: ignore[arg-type]
        ("agent", f.get("agents", set())),  # type: ignore[arg-type]
        ("priority", f.get("priorities", set())),  # type: ignore[arg-type]
        ("sprint", f.get("sprints", set())),  # type: ignore[arg-type]
        ("tags", f.get("tags", set())),  # type: ignore[arg-type]
        ("project", f.get("projects", set())),  # type: ignore[arg-type]
    ]
    for field, values in multi_map:
        for v in values:
            key = f"{field}:{v}"
            out[key] = filter_to_query_string(f, exclude_field=field, exclude_value=v)
    return out


def build_preset_urls(f: MetricsFilter) -> dict[str, str]:
    """Pre-compute full query-strings for each date preset chip.

    Returns a dict keyed by preset name (``"7d"``, ``"30d"``, etc.),
    with the query-string that switches to that preset while preserving
    all other active filters.
    """
    presets = ["7d", "30d", "90d", "sprint", "all"]
    return {
        preset: filter_to_query_string(f, override={"since": preset})
        for preset in presets
    }


def available_filter_options(tickets: list[dict]) -> dict[str, list[str]]:
    """Return sorted unique values present in *tickets* for each filterable field.

    Returns a dict with keys: ``tags``, ``kinds``, ``statuses``, ``agents``,
    ``projects``, ``sprints``, ``priorities``.  Values are sorted lists of
    strings.  Empty strings are excluded.

    This is used to populate the facet dropdowns with only values that
    actually exist in the current ticket set (avoiding phantom options).
    """
    sets: dict[str, set[str]] = {
        "tags": set(),
        "kinds": set(),
        "statuses": set(),
        "agents": set(),
        "projects": set(),
        "sprints": set(),
        "priorities": set(),
    }

    for t in tickets:
        # kinds
        kind = t.get("kind")
        if kind:
            sets["kinds"].add(str(kind).lower())

        # statuses
        status = t.get("status")
        if status:
            sets["statuses"].add(str(status).lower())

        # priorities
        prio = t.get("priority")
        if prio:
            sets["priorities"].add(str(prio).lower())

        # sprint
        sprint = t.get("sprint")
        if sprint:
            if isinstance(sprint, list):
                for s in sprint:
                    if s:
                        sets["sprints"].add(str(s).lower())
            else:
                sets["sprints"].add(str(sprint).lower())

        # tags (str CSV or list)
        raw_tags = t.get("tags")
        if raw_tags is not None:
            if isinstance(raw_tags, list):
                for tg in raw_tags:
                    if tg:
                        sets["tags"].add(str(tg).lower())
            else:
                for tg in str(raw_tags).split(","):
                    tg = tg.strip()
                    if tg:
                        sets["tags"].add(tg.lower())

        # agents (list)
        for a in t.get("agent") or []:
            if a:
                sets["agents"].add(str(a).lower())

        # projects (list)
        for p in t.get("projects") or []:
            if p:
                sets["projects"].add(str(p).lower())

    return {k: sorted(v) for k, v in sets.items()}
