"""Tests for holoctl.lib.metrics — pure-function productivity metrics.

All tests use synthetic ticket dicts and a fixed `now` datetime so results
are fully deterministic and require no I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone

from holoctl.lib.metrics import (
    _parse_ts,
    throughput,
    cycle_time,
    wip,
    by_group,
)


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _ts(s: str) -> str:
    """Shorthand: build an ISO-8601 UTC string with Z suffix."""
    return s + "Z" if not s.endswith("Z") else s


def _ticket(
    *,
    id: str = "T-001",
    status: str = "backlog",
    created: str | None = None,
    updated: str | None = None,
    completed: str | None = None,
    agent: list[str] | None = None,
    projects: list[str] | None = None,
    kind: str = "task",
    sprint: str | None = None,
    priority: str = "p2",
) -> dict:
    return {
        "id": id,
        "status": status,
        "created": created,
        "updated": updated,
        "completed": completed,
        "agent": agent or [],
        "projects": projects or [],
        "kind": kind,
        "sprint": sprint,
        "priority": priority,
    }


# Fixed reference "now" for all tests: 2026-05-27T12:00:00Z
NOW = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)


# ── _parse_ts ─────────────────────────────────────────────────────────────────

class TestParseTs:
    def test_parses_z_suffix(self):
        dt = _parse_ts("2026-05-20T10:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 20
        assert dt.tzinfo == timezone.utc

    def test_parses_offset_plus_zero(self):
        dt = _parse_ts("2026-05-20T10:00:00+00:00")
        assert dt is not None
        assert dt.year == 2026

    def test_returns_none_on_garbage(self):
        assert _parse_ts("not-a-date") is None

    def test_returns_none_on_none(self):
        assert _parse_ts(None) is None  # type: ignore[arg-type]

    def test_returns_none_on_empty_string(self):
        assert _parse_ts("") is None

    def test_returns_none_on_missing_field(self):
        # Simulates a dict.get() that returns None for a missing key.
        result = _parse_ts(None)  # type: ignore[arg-type]
        assert result is None


# ── throughput ────────────────────────────────────────────────────────────────

class TestThroughput:
    def _make_done(self, ticket_id: str, completed_iso: str) -> dict:
        return _ticket(
            id=ticket_id,
            status="done",
            created="2026-04-01T00:00:00Z",
            updated=completed_iso,
            completed=completed_iso,
        )

    def test_returns_ordered_bucket_list(self):
        tickets = [
            self._make_done("T-1", "2026-05-25T10:00:00Z"),
            self._make_done("T-2", "2026-05-27T09:00:00Z"),
        ]
        result = throughput(tickets, bucket="day", now=NOW)
        buckets = [r["bucket"] for r in result]
        assert buckets == sorted(buckets), "buckets must be chronologically ordered"

    def test_empty_buckets_filled_with_zero(self):
        # Only one completed ticket; days in between should have count=0.
        tickets = [
            self._make_done("T-1", "2026-05-20T10:00:00Z"),
            self._make_done("T-2", "2026-05-27T10:00:00Z"),
        ]
        result = throughput(tickets, bucket="day", now=NOW)
        bucket_map = {r["bucket"]: r["count"] for r in result}
        # 2026-05-21 has no completions → must appear with count 0
        assert "2026-05-21" in bucket_map
        assert bucket_map["2026-05-21"] == 0

    def test_only_completed_tickets_counted(self):
        tickets = [
            _ticket(id="T-1", status="doing", updated="2026-05-27T10:00:00Z"),
            _ticket(id="T-2", status="backlog", updated="2026-05-27T10:00:00Z"),
            self._make_done("T-3", "2026-05-27T09:00:00Z"),
        ]
        result = throughput(tickets, bucket="day", now=NOW)
        total = sum(r["count"] for r in result)
        assert total == 1

    def test_tickets_without_completed_ignored(self):
        tickets = [
            _ticket(id="T-1", status="done", created="2026-05-20T00:00:00Z",
                    updated="2026-05-27T00:00:00Z", completed=None),
        ]
        result = throughput(tickets, bucket="day", now=NOW)
        total = sum(r["count"] for r in result)
        assert total == 0

    def test_since_window_respected(self):
        # Ticket completed before the since window must not appear in counts.
        tickets = [
            self._make_done("T-old", "2026-01-01T10:00:00Z"),
            self._make_done("T-new", "2026-05-27T10:00:00Z"),
        ]
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        result = throughput(tickets, bucket="day", since=since, now=NOW)
        bucket_map = {r["bucket"]: r["count"] for r in result}
        # The old ticket's bucket should not appear at all (outside window).
        assert "2026-01-01" not in bucket_map
        # The new ticket should be counted.
        assert bucket_map.get("2026-05-27", 0) == 1

    def test_weekly_bucket_grouping(self):
        # Two tickets completed in the same ISO week → count = 2.
        # 2026-05-25 (Mon) and 2026-05-26 (Tue) are in the same week.
        tickets = [
            self._make_done("T-1", "2026-05-25T10:00:00Z"),
            self._make_done("T-2", "2026-05-26T11:00:00Z"),
            self._make_done("T-3", "2026-05-19T11:00:00Z"),  # previous week
        ]
        result = throughput(tickets, bucket="week", now=NOW)
        # Find the bucket covering 2026-05-25
        # Week bucket key is the Monday of that week: 2026-05-25
        bucket_map = {r["bucket"]: r["count"] for r in result}
        week_25 = "2026-05-25"  # Monday of that week
        assert bucket_map.get(week_25, 0) == 2

    def test_week_bucket_keys_are_mondays(self):
        tickets = [self._make_done("T-1", "2026-05-27T10:00:00Z")]  # Wednesday
        result = throughput(tickets, bucket="week", now=NOW)
        # 2026-05-27 is a Wednesday; Monday of that week is 2026-05-25
        bucket_map = {r["bucket"]: r["count"] for r in result}
        assert "2026-05-25" in bucket_map
        assert bucket_map["2026-05-25"] == 1

    def test_default_since_approximately_30_days(self):
        # Without explicit since, range should cover ~30 days ending at now.
        tickets: list[dict] = []
        result = throughput(tickets, bucket="day", now=NOW)
        assert len(result) >= 28  # at least 28 days

    def test_count_in_correct_bucket(self):
        tickets = [
            self._make_done("T-1", "2026-05-24T23:59:59Z"),
            self._make_done("T-2", "2026-05-25T00:00:00Z"),
        ]
        result = throughput(tickets, bucket="day", now=NOW)
        bucket_map = {r["bucket"]: r["count"] for r in result}
        assert bucket_map.get("2026-05-24", 0) == 1
        assert bucket_map.get("2026-05-25", 0) == 1


# ── cycle_time ────────────────────────────────────────────────────────────────

class TestCycleTime:
    def _done(self, tid: str, created_iso: str, completed_iso: str) -> dict:
        return _ticket(
            id=tid,
            status="done",
            created=created_iso,
            updated=completed_iso,
            completed=completed_iso,
        )

    def test_empty_returns_zeros(self):
        result = cycle_time([])
        assert result["count"] == 0
        assert result["mean"] == 0.0
        assert result["median"] == 0.0
        assert result["p95"] == 0.0

    def test_known_values_mean_and_median(self):
        # Two tickets: 2 days and 4 days → mean=3, median=3
        tickets = [
            self._done("T-1", "2026-05-01T00:00:00Z", "2026-05-03T00:00:00Z"),
            self._done("T-2", "2026-05-01T00:00:00Z", "2026-05-05T00:00:00Z"),
        ]
        result = cycle_time(tickets)
        assert result["count"] == 2
        assert abs(result["mean"] - 3.0) < 0.01
        assert abs(result["median"] - 3.0) < 0.01

    def test_p95_single_ticket(self):
        # Single ticket: 10 days; p95 = 10
        tickets = [
            self._done("T-1", "2026-05-01T00:00:00Z", "2026-05-11T00:00:00Z"),
        ]
        result = cycle_time(tickets)
        assert result["count"] == 1
        assert abs(result["p95"] - 10.0) < 0.01

    def test_p95_larger_set(self):
        # 20 tickets, each 1..20 days. p95 ≈ 19 (nearest-rank method).
        base = "2026-01-01T00:00:00Z"
        base_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        tickets = []
        for i in range(1, 21):
            from datetime import timedelta
            comp = base_dt + timedelta(days=i)
            tickets.append(
                self._done(
                    f"T-{i}",
                    base,
                    comp.isoformat().replace("+00:00", "Z"),
                )
            )
        result = cycle_time(tickets)
        assert result["count"] == 20
        # p95 via nearest-rank of 20 items = ceil(0.95 * 20) = 19th value = 19 days
        assert abs(result["p95"] - 19.0) < 0.01

    def test_tickets_missing_created_excluded(self):
        tickets = [
            _ticket(id="T-1", status="done", created=None,
                    updated="2026-05-10T00:00:00Z", completed="2026-05-10T00:00:00Z"),
            self._done("T-2", "2026-05-01T00:00:00Z", "2026-05-06T00:00:00Z"),
        ]
        result = cycle_time(tickets)
        # Only T-2 is usable (5 days)
        assert result["count"] == 1
        assert abs(result["mean"] - 5.0) < 0.01

    def test_tickets_missing_completed_excluded(self):
        tickets = [
            _ticket(id="T-1", status="doing", created="2026-05-01T00:00:00Z",
                    updated="2026-05-05T00:00:00Z", completed=None),
            self._done("T-2", "2026-05-01T00:00:00Z", "2026-05-08T00:00:00Z"),
        ]
        result = cycle_time(tickets)
        assert result["count"] == 1
        assert abs(result["mean"] - 7.0) < 0.01

    def test_unit_days_is_float(self):
        # Completed 36 hours after created → 1.5 days
        tickets = [
            self._done(
                "T-1",
                "2026-05-01T00:00:00Z",
                "2026-05-02T12:00:00Z",
            )
        ]
        result = cycle_time(tickets, unit="days")
        assert abs(result["mean"] - 1.5) < 0.01


# ── wip ───────────────────────────────────────────────────────────────────────

class TestWip:
    def _active(self, tid: str, status: str, updated_iso: str) -> dict:
        return _ticket(
            id=tid,
            status=status,
            created="2026-05-01T00:00:00Z",
            updated=updated_iso,
        )

    def test_only_active_statuses_counted(self):
        tickets = [
            self._active("T-1", "doing", "2026-05-25T00:00:00Z"),
            self._active("T-2", "review", "2026-05-26T00:00:00Z"),
            self._active("T-3", "backlog", "2026-05-26T00:00:00Z"),
            _ticket(id="T-4", status="done", created="2026-05-01T00:00:00Z",
                    updated="2026-05-20T00:00:00Z", completed="2026-05-20T00:00:00Z"),
        ]
        result = wip(tickets, active_statuses=("doing", "review"), now=NOW)
        assert result["count"] == 2
        ids = {item["id"] for item in result["items"]}
        assert ids == {"T-1", "T-2"}

    def test_age_days_computed_from_updated_vs_now(self):
        # Updated 3 days ago → age_days ≈ 3
        tickets = [
            self._active("T-1", "doing", "2026-05-24T12:00:00Z"),
        ]
        result = wip(tickets, active_statuses=("doing",), now=NOW)
        item = result["items"][0]
        assert abs(item["age_days"] - 3.0) < 0.1

    def test_stale_flag_above_threshold(self):
        # stale_days=5; ticket updated 6 days ago → stale=True
        tickets = [
            self._active("T-1", "doing", "2026-05-21T12:00:00Z"),
        ]
        result = wip(tickets, active_statuses=("doing",), stale_days=5, now=NOW)
        assert result["items"][0]["stale"] is True

    def test_stale_flag_at_boundary_not_stale(self):
        # Exactly 5 days ago → NOT stale (> not >=)
        tickets = [
            self._active("T-1", "doing", "2026-05-22T12:00:00Z"),
        ]
        result = wip(tickets, active_statuses=("doing",), stale_days=5, now=NOW)
        assert result["items"][0]["stale"] is False

    def test_stale_count(self):
        tickets = [
            self._active("T-1", "doing", "2026-05-20T00:00:00Z"),  # 7 days ago → stale
            self._active("T-2", "doing", "2026-05-26T00:00:00Z"),  # 1 day ago → fresh
        ]
        result = wip(tickets, active_statuses=("doing",), stale_days=5, now=NOW)
        assert result["count"] == 2
        assert result["stale_count"] == 1

    def test_items_sorted_by_age_desc(self):
        tickets = [
            self._active("T-fresh", "doing", "2026-05-26T00:00:00Z"),  # 1 day
            self._active("T-old", "doing", "2026-05-20T00:00:00Z"),    # 7 days
            self._active("T-mid", "doing", "2026-05-23T00:00:00Z"),    # 4 days
        ]
        result = wip(tickets, active_statuses=("doing",), now=NOW)
        ages = [item["age_days"] for item in result["items"]]
        assert ages == sorted(ages, reverse=True)

    def test_items_include_id_status_age_stale(self):
        tickets = [
            self._active("T-1", "doing", "2026-05-25T00:00:00Z"),
        ]
        result = wip(tickets, active_statuses=("doing",), now=NOW)
        item = result["items"][0]
        assert "id" in item
        assert "status" in item
        assert "age_days" in item
        assert "stale" in item

    def test_empty_tickets_returns_zero_count(self):
        result = wip([], now=NOW)
        assert result["count"] == 0
        assert result["stale_count"] == 0
        assert result["items"] == []

    def test_ticket_with_missing_updated_excluded(self):
        tickets = [
            _ticket(id="T-1", status="doing", created="2026-05-01T00:00:00Z", updated=None),
            self._active("T-2", "doing", "2026-05-25T00:00:00Z"),
        ]
        result = wip(tickets, active_statuses=("doing",), now=NOW)
        assert result["count"] == 1
        assert result["items"][0]["id"] == "T-2"


# ── by_group ──────────────────────────────────────────────────────────────────

class TestByGroup:
    def _done_ticket(
        self,
        tid: str,
        *,
        agents: list[str] | None = None,
        projects: list[str] | None = None,
        created: str = "2026-05-01T00:00:00Z",
        completed: str | None = "2026-05-10T00:00:00Z",
        status: str = "done",
    ) -> dict:
        return _ticket(
            id=tid,
            status=status,
            created=created,
            updated=completed or "2026-05-05T00:00:00Z",
            completed=completed,
            agent=agents or [],
            projects=projects or [],
        )

    def test_agent_fan_out_single_group(self):
        tickets = [
            self._done_ticket("T-1", agents=["alice"]),
            self._done_ticket("T-2", agents=["alice"]),
        ]
        result = by_group(tickets, key="agent", now=NOW)
        groups = {r["group"]: r for r in result}
        assert "alice" in groups
        assert groups["alice"]["completed"] == 2

    def test_agent_fan_out_multi_agent_ticket(self):
        # Ticket with 2 agents counts in BOTH agent buckets.
        tickets = [
            self._done_ticket("T-1", agents=["alice", "bob"]),
        ]
        result = by_group(tickets, key="agent", now=NOW)
        groups = {r["group"]: r for r in result}
        assert "alice" in groups
        assert "bob" in groups
        assert groups["alice"]["completed"] == 1
        assert groups["bob"]["completed"] == 1

    def test_unassigned_bucket_for_empty_agent(self):
        tickets = [
            self._done_ticket("T-1", agents=[]),
        ]
        result = by_group(tickets, key="agent", now=NOW)
        groups = {r["group"]: r for r in result}
        assert "(unassigned)" in groups
        assert groups["(unassigned)"]["completed"] == 1

    def test_projects_fan_out(self):
        tickets = [
            self._done_ticket("T-1", projects=["backend", "api"]),
            self._done_ticket("T-2", projects=["backend"]),
        ]
        result = by_group(tickets, key="projects", now=NOW)
        groups = {r["group"]: r for r in result}
        assert groups["backend"]["completed"] == 2
        assert groups["api"]["completed"] == 1

    def test_unassigned_bucket_for_empty_projects(self):
        tickets = [
            self._done_ticket("T-1", projects=[]),
        ]
        result = by_group(tickets, key="projects", now=NOW)
        groups = {r["group"]: r for r in result}
        assert "(unassigned)" in groups

    def test_wip_count_in_group(self):
        tickets = [
            self._done_ticket("T-done", agents=["alice"], completed="2026-05-10T00:00:00Z"),
            _ticket(
                id="T-wip",
                status="doing",
                created="2026-05-01T00:00:00Z",
                updated="2026-05-25T00:00:00Z",
                agent=["alice"],
            ),
        ]
        result = by_group(tickets, key="agent", now=NOW)
        groups = {r["group"]: r for r in result}
        assert groups["alice"]["wip"] == 1

    def test_avg_cycle_days_only_done_tickets(self):
        # alice: two done tickets with 2-day and 8-day cycles → avg = 5
        tickets = [
            self._done_ticket(
                "T-1", agents=["alice"],
                created="2026-05-01T00:00:00Z",
                completed="2026-05-03T00:00:00Z",
            ),
            self._done_ticket(
                "T-2", agents=["alice"],
                created="2026-05-01T00:00:00Z",
                completed="2026-05-09T00:00:00Z",
            ),
        ]
        result = by_group(tickets, key="agent", now=NOW)
        groups = {r["group"]: r for r in result}
        assert abs(groups["alice"]["avg_cycle_days"] - 5.0) < 0.01

    def test_avg_cycle_days_none_when_no_done(self):
        tickets = [
            _ticket(
                id="T-1", status="doing",
                created="2026-05-01T00:00:00Z",
                updated="2026-05-25T00:00:00Z",
                agent=["alice"],
            ),
        ]
        result = by_group(tickets, key="agent", now=NOW)
        groups = {r["group"]: r for r in result}
        assert groups["alice"]["avg_cycle_days"] is None

    def test_ordered_by_completed_desc(self):
        tickets = [
            self._done_ticket("T-1", agents=["alice"]),
            self._done_ticket("T-2", agents=["bob"]),
            self._done_ticket("T-3", agents=["bob"]),
        ]
        result = by_group(tickets, key="agent", now=NOW)
        completeds = [r["completed"] for r in result]
        assert completeds == sorted(completeds, reverse=True)

    def test_result_has_required_keys(self):
        tickets = [self._done_ticket("T-1", agents=["alice"])]
        result = by_group(tickets, key="agent", now=NOW)
        row = result[0]
        assert "group" in row
        assert "completed" in row
        assert "avg_cycle_days" in row
        assert "wip" in row
