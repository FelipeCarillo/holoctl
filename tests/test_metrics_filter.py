"""Tests for holoctl.server.filters — URL-driven MetricsFilter.

All tests use synthetic data and a fixed ``now`` so results are deterministic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from holoctl.server.filters import (
    apply_filter,
    available_filter_options,
    build_chip_remove_urls,
    build_preset_urls,
    filter_to_query_string,
    parse_filter_from_query,
)

# Fixed reference "now" for all tests: 2026-05-27T12:00:00Z
NOW = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ticket(
    *,
    id: str = "T-001",
    status: str = "backlog",
    created: str | None = "2026-05-20T00:00:00Z",
    kind: str = "task",
    sprint: str | None = None,
    priority: str = "p2",
    agent: list[str] | None = None,
    projects: list[str] | None = None,
    tags: str | None = None,
    completed: str | None = None,
) -> dict:
    return {
        "id": id,
        "status": status,
        "created": created,
        "updated": created,
        "completed": completed,
        "kind": kind,
        "sprint": sprint,
        "priority": priority,
        "agent": agent or [],
        "projects": projects or [],
        "tags": tags,
    }


def _qp(d: dict[str, str | list[str]]) -> dict[str, list[str]]:
    """Build a dict[str, list[str]] suitable for parse_filter_from_query."""
    out: dict[str, list[str]] = {}
    for k, v in d.items():
        out[k] = v if isinstance(v, list) else [v]
    return out


# ── parse_filter_from_query ───────────────────────────────────────────────────


class TestParseFilterFromQuery:
    def test_default_since_30d(self):
        f = parse_filter_from_query({}, now=NOW)
        assert f["since_preset"] == "30d"
        assert f["since_days"] == 30
        expected = NOW - timedelta(days=30)
        assert f["since"] is not None
        diff = abs((f["since"] - expected).total_seconds())
        assert diff < 2

    def test_preset_7d(self):
        f = parse_filter_from_query(_qp({"since": "7d"}), now=NOW)
        assert f["since_preset"] == "7d"
        assert f["since_days"] == 7
        expected = NOW - timedelta(days=7)
        assert f["since"] is not None
        diff = abs((f["since"] - expected).total_seconds())
        assert diff < 2

    def test_preset_90d(self):
        f = parse_filter_from_query(_qp({"since": "90d"}), now=NOW)
        assert f["since_preset"] == "90d"
        assert f["since_days"] == 90

    def test_preset_sprint(self):
        f = parse_filter_from_query(_qp({"since": "sprint"}), now=NOW)
        assert f["since_preset"] == "sprint"
        assert f["since_days"] == 14

    def test_preset_all(self):
        f = parse_filter_from_query(_qp({"since": "all"}), now=NOW)
        assert f["since_preset"] == "all"
        assert f["since"] is None
        assert f["since_days"] == 9999

    def test_custom_iso_date(self):
        f = parse_filter_from_query(_qp({"since": "2026-05-01"}), now=NOW)
        assert f["since_preset"] == "custom"
        assert f["since"] is not None
        assert f["since"].year == 2026
        assert f["since"].month == 5
        assert f["since"].day == 1

    def test_unknown_since_falls_back_to_30d(self):
        f = parse_filter_from_query(_qp({"since": "bogus-value"}), now=NOW)
        assert f["since_preset"] == "30d"
        assert f["since_days"] == 30

    def test_multi_value_tags_repeated(self):
        f = parse_filter_from_query(
            _qp({"tags": ["auth", "ui"]}), now=NOW
        )
        assert f["tags"] == {"auth", "ui"}

    def test_multi_value_tags_comma_separated(self):
        f = parse_filter_from_query(_qp({"tags": "auth,ui"}), now=NOW)
        assert f["tags"] == {"auth", "ui"}

    def test_multi_value_tags_mixed(self):
        f = parse_filter_from_query(
            _qp({"tags": ["auth,ui", "api"]}), now=NOW
        )
        assert f["tags"] == {"auth", "ui", "api"}

    def test_kind_and_kinds_aliases(self):
        f = parse_filter_from_query(_qp({"kind": "task"}), now=NOW)
        assert "task" in f["kinds"]

    def test_status_alias(self):
        f = parse_filter_from_query(_qp({"status": "doing"}), now=NOW)
        assert "doing" in f["statuses"]

    def test_agent_alias(self):
        f = parse_filter_from_query(_qp({"agent": "alice"}), now=NOW)
        assert "alice" in f["agents"]

    def test_values_lowercased(self):
        f = parse_filter_from_query(_qp({"kind": "TASK", "tags": "AUTH"}), now=NOW)
        assert "task" in f["kinds"]
        assert "auth" in f["tags"]

    def test_empty_values_ignored(self):
        f = parse_filter_from_query(_qp({"tags": ",,,"}), now=NOW)
        assert f["tags"] == set()

    def test_accepts_list_of_tuples(self):
        pairs: list[tuple[str, str]] = [("since", "7d"), ("kind", "task"), ("tags", "auth")]
        f = parse_filter_from_query(pairs, now=NOW)
        assert f["since_preset"] == "7d"
        assert "task" in f["kinds"]
        assert "auth" in f["tags"]

    def test_empty_dict_returns_defaults(self):
        f = parse_filter_from_query({}, now=NOW)
        assert f["tags"] == set()
        assert f["kinds"] == set()
        assert f["statuses"] == set()
        assert f["agents"] == set()
        assert f["projects"] == set()
        assert f["sprints"] == set()
        assert f["priorities"] == set()


# ── apply_filter ──────────────────────────────────────────────────────────────


class TestApplyFilter:
    def test_empty_filter_is_passthrough(self):
        tickets = [_ticket(id="T-1"), _ticket(id="T-2"), _ticket(id="T-3")]
        f = parse_filter_from_query({}, now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 3

    def test_since_date_filter_on_created(self):
        tickets = [
            _ticket(id="T-old", created="2026-04-01T00:00:00Z"),
            _ticket(id="T-new", created="2026-05-25T00:00:00Z"),
        ]
        f = parse_filter_from_query(_qp({"since": "30d"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        ids = {t["id"] for t in out}
        assert "T-new" in ids
        assert "T-old" not in ids

    def test_since_all_includes_old_tickets(self):
        tickets = [
            _ticket(id="T-old", created="2020-01-01T00:00:00Z"),
            _ticket(id="T-new", created="2026-05-25T00:00:00Z"),
        ]
        f = parse_filter_from_query(_qp({"since": "all"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 2

    def test_tickets_with_missing_created_excluded_when_since_set(self):
        tickets = [
            _ticket(id="T-no-date", created=None),
            _ticket(id="T-ok", created="2026-05-25T00:00:00Z"),
        ]
        f = parse_filter_from_query(_qp({"since": "7d"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        ids = {t["id"] for t in out}
        assert "T-ok" in ids
        assert "T-no-date" not in ids

    def test_kind_filter(self):
        tickets = [
            _ticket(id="T-task", kind="task"),
            _ticket(id="T-spec", kind="spec"),
        ]
        f = parse_filter_from_query(_qp({"kind": "task", "since": "all"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 1
        assert out[0]["id"] == "T-task"

    def test_status_filter(self):
        tickets = [
            _ticket(id="T-doing", status="doing"),
            _ticket(id="T-backlog", status="backlog"),
        ]
        f = parse_filter_from_query(_qp({"status": "doing", "since": "all"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 1
        assert out[0]["id"] == "T-doing"

    def test_priority_filter(self):
        tickets = [
            _ticket(id="T-p0", priority="p0"),
            _ticket(id="T-p2", priority="p2"),
        ]
        f = parse_filter_from_query(_qp({"priority": "p0", "since": "all"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 1
        assert out[0]["id"] == "T-p0"

    def test_sprint_filter(self):
        tickets = [
            _ticket(id="T-s1", sprint="s1"),
            _ticket(id="T-s2", sprint="s2"),
            _ticket(id="T-none", sprint=None),
        ]
        f = parse_filter_from_query(_qp({"sprint": "s1", "since": "all"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 1
        assert out[0]["id"] == "T-s1"

    def test_tags_filter_csv(self):
        tickets = [
            _ticket(id="T-auth", tags="auth,api"),
            _ticket(id="T-ui", tags="ui"),
        ]
        f = parse_filter_from_query(_qp({"tags": "auth", "since": "all"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 1
        assert out[0]["id"] == "T-auth"

    def test_tags_filter_list(self):
        tickets = [
            _ticket(id="T-auth", tags=["auth", "api"]),
            _ticket(id="T-ui", tags=["ui"]),
        ]
        f = parse_filter_from_query(_qp({"tags": "auth", "since": "all"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 1
        assert out[0]["id"] == "T-auth"

    def test_agent_filter(self):
        tickets = [
            _ticket(id="T-alice", agent=["alice"]),
            _ticket(id="T-bob", agent=["bob"]),
        ]
        f = parse_filter_from_query(_qp({"agent": "alice", "since": "all"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 1
        assert out[0]["id"] == "T-alice"

    def test_projects_filter(self):
        tickets = [
            _ticket(id="T-be", projects=["backend"]),
            _ticket(id="T-fe", projects=["frontend"]),
        ]
        f = parse_filter_from_query(_qp({"project": "backend", "since": "all"}), now=NOW)
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 1
        assert out[0]["id"] == "T-be"

    def test_multi_field_and_semantics(self):
        """Ticket must match ALL active filter fields (AND across fields)."""
        tickets = [
            _ticket(id="T-match", kind="task", status="doing", agent=["alice"]),
            _ticket(id="T-kind-only", kind="task", status="backlog", agent=["bob"]),
            _ticket(id="T-agent-only", kind="spec", status="doing", agent=["alice"]),
        ]
        f = parse_filter_from_query(
            _qp({"kind": "task", "status": "doing", "agent": "alice", "since": "all"}),
            now=NOW,
        )
        out = apply_filter(tickets, f, now=NOW)
        assert len(out) == 1
        assert out[0]["id"] == "T-match"

    def test_intra_field_or_semantics(self):
        """Within a single field, multiple values are OR-ed."""
        tickets = [
            _ticket(id="T-task", kind="task"),
            _ticket(id="T-spec", kind="spec"),
            _ticket(id="T-story", kind="story"),
        ]
        f = parse_filter_from_query(
            _qp({"kind": ["task", "spec"], "since": "all"}), now=NOW
        )
        out = apply_filter(tickets, f, now=NOW)
        ids = {t["id"] for t in out}
        assert ids == {"T-task", "T-spec"}

    def test_naive_created_iso_does_not_crash_apply_filter(self):
        """Tickets with a bare (tz-naive) ISO ``created`` must not raise TypeError.

        Regression guard: _parse_ts must always return a tz-aware datetime so
        that comparing it against a tz-aware ``since`` never raises
        ``TypeError: can't compare offset-naive and offset-aware datetimes``.
        """
        # Bare ISO — no 'Z' and no UTC offset.
        naive_ticket = _ticket(id="T-naive", created="2026-05-20T10:00:00")
        aware_ticket = _ticket(id="T-aware", created="2026-05-20T10:00:00Z")

        f = parse_filter_from_query(_qp({"since": "30d"}), now=NOW)

        # Must not raise; both tickets are within the 30-day window.
        result = apply_filter([naive_ticket, aware_ticket], f, now=NOW)
        ids = {t["id"] for t in result}
        assert "T-naive" in ids
        assert "T-aware" in ids


# ── filter_to_query_string ────────────────────────────────────────────────────


class TestFilterToQueryString:
    def test_round_trip_preset(self):
        f = parse_filter_from_query(_qp({"since": "7d"}), now=NOW)
        qs = filter_to_query_string(f)
        assert "since=7d" in qs

    def test_round_trip_multi_values(self):
        f = parse_filter_from_query(
            _qp({"since": "30d", "kind": ["task", "spec"], "tags": "auth"}),
            now=NOW,
        )
        qs = filter_to_query_string(f)
        assert "since=30d" in qs
        assert "kind=task" in qs
        assert "kind=spec" in qs
        assert "tags=auth" in qs

    def test_exclude_field_value(self):
        f = parse_filter_from_query(
            _qp({"since": "30d", "kind": ["task", "spec"]}), now=NOW
        )
        qs = filter_to_query_string(f, exclude_field="kind", exclude_value="task")
        assert "kind=task" not in qs
        assert "kind=spec" in qs

    def test_override_since(self):
        f = parse_filter_from_query(_qp({"since": "7d"}), now=NOW)
        qs = filter_to_query_string(f, override={"since": "30d"})
        assert "since=30d" in qs
        assert "since=7d" not in qs

    def test_empty_filter_only_since(self):
        f = parse_filter_from_query({}, now=NOW)
        qs = filter_to_query_string(f)
        assert qs == "since=30d"


# ── available_filter_options ──────────────────────────────────────────────────


class TestAvailableFilterOptions:
    def test_returns_sorted_unique_values(self):
        tickets = [
            _ticket(id="T-1", kind="task", status="doing", priority="p1",
                    agent=["alice"], projects=["backend"], tags="auth,api", sprint="s1"),
            _ticket(id="T-2", kind="spec", status="backlog", priority="p2",
                    agent=["bob"], projects=["frontend"], tags="ui", sprint="s2"),
            _ticket(id="T-3", kind="task", status="doing", priority="p1",
                    agent=["alice"], projects=["backend"], tags="auth", sprint="s1"),
        ]
        opts = available_filter_options(tickets)

        assert opts["kinds"] == ["spec", "task"]
        assert opts["statuses"] == ["backlog", "doing"]
        assert opts["priorities"] == ["p1", "p2"]
        assert opts["agents"] == ["alice", "bob"]
        assert opts["projects"] == ["backend", "frontend"]
        assert set(opts["tags"]) == {"auth", "api", "ui"}
        assert opts["sprints"] == ["s1", "s2"]

    def test_empty_values_excluded(self):
        tickets = [_ticket(id="T-1", tags="", sprint=None, agent=[])]
        opts = available_filter_options(tickets)
        assert opts["tags"] == []
        assert opts["sprints"] == []
        assert opts["agents"] == []

    def test_tag_list_format(self):
        tickets = [_ticket(id="T-1", tags=["auth", "api"])]
        opts = available_filter_options(tickets)
        assert "auth" in opts["tags"]
        assert "api" in opts["tags"]

    def test_all_keys_present(self):
        opts = available_filter_options([])
        for key in ("tags", "kinds", "statuses", "agents", "projects", "sprints", "priorities"):
            assert key in opts
            assert opts[key] == []


# ── build_chip_remove_urls ────────────────────────────────────────────────────


class TestBuildChipRemoveUrls:
    def test_chip_key_format(self):
        f = parse_filter_from_query(
            _qp({"since": "30d", "kind": "task", "tags": "auth"}), now=NOW
        )
        urls = build_chip_remove_urls(f)
        assert "kind:task" in urls
        assert "tags:auth" in urls

    def test_remove_url_excludes_value(self):
        f = parse_filter_from_query(
            _qp({"since": "30d", "kind": ["task", "spec"]}), now=NOW
        )
        urls = build_chip_remove_urls(f)
        remove_task_qs = urls["kind:task"]
        assert "kind=task" not in remove_task_qs
        assert "kind=spec" in remove_task_qs

    def test_empty_filter_returns_empty_dict(self):
        f = parse_filter_from_query({}, now=NOW)
        urls = build_chip_remove_urls(f)
        assert urls == {}


# ── build_preset_urls ─────────────────────────────────────────────────────────


class TestBuildPresetUrls:
    def test_all_presets_present(self):
        f = parse_filter_from_query({}, now=NOW)
        urls = build_preset_urls(f)
        for preset in ("7d", "30d", "90d", "sprint", "all"):
            assert preset in urls

    def test_preset_url_contains_correct_since(self):
        f = parse_filter_from_query(_qp({"since": "30d", "kind": "task"}), now=NOW)
        urls = build_preset_urls(f)
        assert "since=7d" in urls["7d"]
        assert "since=all" in urls["all"]

    def test_preset_url_preserves_other_filters(self):
        f = parse_filter_from_query(
            _qp({"since": "30d", "kind": "task", "tags": "auth"}), now=NOW
        )
        urls = build_preset_urls(f)
        qs_7d = urls["7d"]
        assert "kind=task" in qs_7d
        assert "tags=auth" in qs_7d
