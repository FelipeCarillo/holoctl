"""Tests for holoctl.lib.metrics — pure-function productivity metrics.

All tests use synthetic ticket dicts and a fixed `now` datetime so results
are fully deterministic and require no I/O.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from holoctl.lib.metrics import (
    _parse_ts,
    throughput,
    cycle_time,
    wip,
    by_group,
    trend,
    cycle_time_distribution,
    read_activity_events,
    time_in_status,
    flow_efficiency,
    forecast,
)
from holoctl.server.views.metrics import stalled_view


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

    def test_naive_iso_assumed_utc_aware(self):
        # Regression: a bare ISO with no Z and no +offset must come back
        # tz-aware (assumed UTC) so downstream comparisons against
        # `datetime.now(timezone.utc)` don't raise
        # "can't compare offset-naive and offset-aware datetimes".
        dt = _parse_ts("2026-05-20T10:00:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc


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


# ── trend ─────────────────────────────────────────────────────────────────────

class TestTrend:
    def _done(self, tid: str, completed_iso: str) -> dict:
        return _ticket(
            id=tid,
            status="done",
            created="2026-04-01T00:00:00Z",
            updated=completed_iso,
            completed=completed_iso,
        )

    def test_current_window_counts_correctly(self):
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        tickets = [
            self._done("T-1", "2026-05-10T00:00:00Z"),
            self._done("T-2", "2026-05-20T00:00:00Z"),
            self._done("T-3", "2026-04-05T00:00:00Z"),  # in prev window
        ]
        result = trend(tickets, since=since, now=NOW)
        assert result["current"] == 2

    def test_previous_window_counts_correctly(self):
        # since=2026-05-01, window=26d (May 1..May 27).
        # prev window = Apr 5..Apr 30 (same length).
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        tickets = [
            self._done("T-1", "2026-05-10T00:00:00Z"),  # current
            self._done("T-2", "2026-04-10T00:00:00Z"),  # prev
            self._done("T-3", "2026-04-15T00:00:00Z"),  # prev
        ]
        result = trend(tickets, since=since, now=NOW)
        assert result["previous"] == 2

    def test_delta_pct_positive(self):
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        tickets = [
            self._done("T-cur1", "2026-05-05T00:00:00Z"),
            self._done("T-cur2", "2026-05-10T00:00:00Z"),
            self._done("T-prev1", "2026-04-05T00:00:00Z"),
        ]
        result = trend(tickets, since=since, now=NOW)
        assert result["current"] == 2
        assert result["previous"] == 1
        assert result["delta_pct"] == 100.0

    def test_delta_pct_none_when_previous_is_zero(self):
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        tickets = [self._done("T-1", "2026-05-10T00:00:00Z")]
        result = trend(tickets, since=since, now=NOW)
        assert result["previous"] == 0
        assert result["delta_pct"] is None

    def test_prev_period_false_suppresses_previous(self):
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        tickets = [
            self._done("T-cur", "2026-05-10T00:00:00Z"),
            self._done("T-prev", "2026-04-10T00:00:00Z"),
        ]
        result = trend(tickets, since=since, now=NOW, prev_period=False)
        assert result["previous"] == 0
        assert result["delta_pct"] is None

    def test_empty_tickets_returns_zeros(self):
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        result = trend([], since=since, now=NOW)
        assert result["current"] == 0
        assert result["previous"] == 0
        assert result["delta_pct"] is None

    def test_result_keys(self):
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        result = trend([], since=since, now=NOW)
        assert "current" in result
        assert "previous" in result
        assert "delta_pct" in result


# ── cycle_time_distribution ───────────────────────────────────────────────────

class TestCycleTimeDistribution:
    def _done(self, tid: str, created_iso: str, completed_iso: str) -> dict:
        return _ticket(
            id=tid,
            status="done",
            created=created_iso,
            completed=completed_iso,
            updated=completed_iso,
        )

    def test_empty_returns_zero_values(self):
        result = cycle_time_distribution([])
        assert result["min"] == 0.0
        assert result["max"] == 0.0
        assert result["p50"] == 0.0
        assert result["p75"] == 0.0
        assert result["p95"] == 0.0
        assert result["bins"] == []

    def test_single_ticket_single_bin(self):
        tickets = [self._done("T-1", "2026-05-01T00:00:00Z", "2026-05-06T00:00:00Z")]
        result = cycle_time_distribution(tickets)
        assert result["min"] == 5.0
        assert result["max"] == 5.0
        assert result["p50"] == 5.0
        assert result["p95"] == 5.0
        assert len(result["bins"]) == 1
        assert result["bins"][0]["count"] == 1

    def test_percentile_values(self):
        # 4 tickets: 1d, 2d, 3d, 10d  → sorted [1,2,3,10]
        # p50 = ceil(0.5*4)=2nd value=2; p75=ceil(0.75*4)=3rd=3; p95=ceil(0.95*4)=4th=10
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        tickets = [
            self._done("T-1", "2026-05-01T00:00:00Z", "2026-05-02T00:00:00Z"),  # 1d
            self._done("T-2", "2026-05-01T00:00:00Z", "2026-05-03T00:00:00Z"),  # 2d
            self._done("T-3", "2026-05-01T00:00:00Z", "2026-05-04T00:00:00Z"),  # 3d
            self._done("T-4", "2026-05-01T00:00:00Z", "2026-05-11T00:00:00Z"),  # 10d
        ]
        result = cycle_time_distribution(tickets)
        assert result["p50"] == 2.0
        assert result["p75"] == 3.0
        assert result["p95"] == 10.0

    def test_bins_count_sums_to_total(self):
        tickets = [
            self._done(f"T-{i}", "2026-05-01T00:00:00Z",
                       (datetime(2026, 5, 1, tzinfo=timezone.utc) + timedelta(days=i)).isoformat().replace("+00:00", "Z"))
            for i in range(1, 11)
        ]
        result = cycle_time_distribution(tickets, bins=5)
        total = sum(b["count"] for b in result["bins"])
        assert total == 10

    def test_result_has_required_keys(self):
        result = cycle_time_distribution([])
        assert "min" in result
        assert "max" in result
        assert "p50" in result
        assert "p75" in result
        assert "p95" in result
        assert "bins" in result

    def test_missing_timestamps_excluded(self):
        tickets = [
            _ticket(id="T-1", status="done", created=None, completed="2026-05-10T00:00:00Z"),
            self._done("T-2", "2026-05-01T00:00:00Z", "2026-05-06T00:00:00Z"),
        ]
        result = cycle_time_distribution(tickets)
        # Only T-2 counts
        assert result["min"] == 5.0
        assert result["max"] == 5.0


# ── read_activity_events ──────────────────────────────────────────────────────

class TestReadActivityEvents:
    def _make_root(self, lines: list[str]) -> Path:
        """Create a temp directory with .holoctl/activity.jsonl populated."""
        tmp = Path(tempfile.mkdtemp())
        log_dir = tmp / ".holoctl"
        log_dir.mkdir()
        log_path = log_dir / "activity.jsonl"
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return tmp

    def test_returns_empty_when_file_missing(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / ".holoctl").mkdir()
        result = read_activity_events(tmp)
        assert result == []

    def test_parses_valid_moved_events(self):
        lines = [
            json.dumps({"ts": "2026-05-10T12:00:00Z", "type": "ticket.moved",
                        "ticket": "T-1", "from": "backlog", "to": "doing"}),
        ]
        root = self._make_root(lines)
        result = read_activity_events(root)
        assert len(result) == 1
        assert result[0]["ticket"] == "T-1"
        assert result[0]["from"] == "backlog"
        assert result[0]["to"] == "doing"
        assert isinstance(result[0]["ts"], datetime)

    def test_ignores_non_moved_events(self):
        lines = [
            json.dumps({"ts": "2026-05-10T12:00:00Z", "type": "ticket.created",
                        "ticket": "T-1", "actor": "cli"}),
            json.dumps({"ts": "2026-05-10T13:00:00Z", "type": "ticket.moved",
                        "ticket": "T-2", "from": "backlog", "to": "doing"}),
        ]
        root = self._make_root(lines)
        result = read_activity_events(root)
        assert len(result) == 1
        assert result[0]["ticket"] == "T-2"

    def test_skips_malformed_json_lines(self):
        lines = [
            "{this is not json}",
            json.dumps({"ts": "2026-05-10T12:00:00Z", "type": "ticket.moved",
                        "ticket": "T-1", "from": "backlog", "to": "doing"}),
        ]
        root = self._make_root(lines)
        result = read_activity_events(root)
        assert len(result) == 1

    def test_since_filter_applied(self):
        lines = [
            json.dumps({"ts": "2026-05-01T00:00:00Z", "type": "ticket.moved",
                        "ticket": "T-old", "from": "backlog", "to": "doing"}),
            json.dumps({"ts": "2026-05-20T00:00:00Z", "type": "ticket.moved",
                        "ticket": "T-new", "from": "doing", "to": "review"}),
        ]
        root = self._make_root(lines)
        since = datetime(2026, 5, 10, tzinfo=timezone.utc)
        result = read_activity_events(root, since=since)
        assert len(result) == 1
        assert result[0]["ticket"] == "T-new"

    def test_empty_file_returns_empty_list(self):
        root = self._make_root([])
        result = read_activity_events(root)
        assert result == []

    def test_skips_non_dict_json_lines(self):
        """Valid JSON non-dict values (null, int, list) must not raise AttributeError."""
        lines = [
            "null",
            "42",
            "[1, 2, 3]",
            json.dumps({"ts": "2026-05-10T12:00:00Z", "type": "ticket.moved",
                        "ticket": "T-1", "from": "backlog", "to": "doing"}),
        ]
        root = self._make_root(lines)
        result = read_activity_events(root)
        assert len(result) == 1
        assert result[0]["ticket"] == "T-1"


# ── time_in_status ────────────────────────────────────────────────────────────

class TestTimeInStatus:
    def _moved(self, ts_iso: str, ticket: str, from_st: str, to_st: str) -> dict:
        return {
            "ts": datetime.fromisoformat(ts_iso.replace("Z", "+00:00")),
            "ticket": ticket,
            "from": from_st,
            "to": to_st,
        }

    def test_empty_events_returns_empty(self):
        result = time_in_status([], [], now=NOW)
        assert result == {"per_status": [], "bottleneck": None}

    def test_single_move_accumulates_to_status(self):
        tickets = [_ticket(id="T-1", status="doing", updated="2026-05-25T00:00:00Z")]
        events = [
            # T-1 moved from backlog to doing at T+0; now is 2d later
            self._moved("2026-05-25T00:00:00Z", "T-1", "backlog", "doing"),
        ]
        # now = 2026-05-27T12:00:00Z → 2.5 days in "doing"
        result = time_in_status(tickets, events, now=NOW)
        per = {r["status"]: r for r in result["per_status"]}
        assert "doing" in per
        assert abs(per["doing"]["avg_days"] - 2.5) < 0.1

    def test_multiple_moves_chain_correctly(self):
        # T-1: backlog→doing at t0, doing→review at t0+1d, review→done at t0+2d
        t0 = "2026-05-20T00:00:00Z"
        t1 = "2026-05-21T00:00:00Z"
        t2 = "2026-05-22T00:00:00Z"
        tickets = [_ticket(id="T-1", status="done", updated=t2, completed=t2)]
        events = [
            self._moved(t0, "T-1", "backlog", "doing"),
            self._moved(t1, "T-1", "doing", "review"),
            self._moved(t2, "T-1", "review", "done"),
        ]
        result = time_in_status(tickets, events, now=NOW)
        per = {r["status"]: r for r in result["per_status"]}
        # "doing" = 1 day (t0→t1), "review" = 1 day (t1→t2)
        assert "doing" in per
        assert "review" in per
        assert abs(per["doing"]["avg_days"] - 1.0) < 0.01
        assert abs(per["review"]["avg_days"] - 1.0) < 0.01

    def test_bottleneck_is_highest_avg_non_terminal(self):
        t0 = "2026-05-10T00:00:00Z"
        t1 = "2026-05-15T00:00:00Z"  # 5 days in "doing"
        t2 = "2026-05-16T00:00:00Z"  # 1 day in "review"
        t3 = "2026-05-17T00:00:00Z"  # terminal
        tickets = [_ticket(id="T-1", status="done", updated=t3, completed=t3)]
        events = [
            self._moved(t0, "T-1", "backlog", "doing"),
            self._moved(t1, "T-1", "doing", "review"),
            self._moved(t2, "T-1", "review", "done"),
        ]
        result = time_in_status(tickets, events, now=NOW)
        assert result["bottleneck"] == "doing"

    def test_done_not_bottleneck(self):
        # Even if done has longest time, it should not be the bottleneck.
        t0 = "2026-05-01T00:00:00Z"
        t1 = "2026-05-26T00:00:00Z"  # 25 days in doing
        t2 = "2026-05-27T00:00:00Z"  # 1 day in done
        tickets = [_ticket(id="T-1", status="done", updated=t2, completed=t2)]
        events = [
            self._moved(t0, "T-1", "backlog", "doing"),
            self._moved(t1, "T-1", "doing", "done"),
        ]
        result = time_in_status(tickets, events, now=NOW)
        # bottleneck should be "doing" (non-terminal), not "done"
        assert result["bottleneck"] == "doing"

    def test_result_has_required_keys(self):
        tickets = [_ticket(id="T-1", status="doing", updated="2026-05-25T00:00:00Z")]
        events = [self._moved("2026-05-25T00:00:00Z", "T-1", "backlog", "doing")]
        result = time_in_status(tickets, events, now=NOW)
        assert "per_status" in result
        assert "bottleneck" in result
        for row in result["per_status"]:
            assert "status" in row
            assert "total_days" in row
            assert "ticket_count" in row
            assert "avg_days" in row


# ── flow_efficiency ───────────────────────────────────────────────────────────

class TestFlowEfficiency:
    def _tis_result(self, per_status: list[dict]) -> dict:
        return {"per_status": per_status, "bottleneck": None}

    def test_empty_returns_none_ratio(self):
        result = flow_efficiency(self._tis_result([]))
        assert result["ratio"] is None
        assert result["active_days"] == 0.0
        assert result["total_days"] == 0.0

    def test_ratio_all_active(self):
        per = [{"status": "doing", "total_days": 10.0, "ticket_count": 1, "avg_days": 10.0}]
        result = flow_efficiency(self._tis_result(per), active_statuses=("doing",))
        assert result["ratio"] == 1.0
        assert result["active_days"] == 10.0

    def test_ratio_mixed_statuses(self):
        per = [
            {"status": "doing", "total_days": 4.0, "ticket_count": 1, "avg_days": 4.0},
            {"status": "review", "total_days": 4.0, "ticket_count": 1, "avg_days": 4.0},
            {"status": "backlog", "total_days": 2.0, "ticket_count": 1, "avg_days": 2.0},
        ]
        # active = doing only = 4d; total non-terminal = 10d
        result = flow_efficiency(self._tis_result(per), active_statuses=("doing",))
        assert abs(result["ratio"] - 0.4) < 0.001
        assert result["total_days"] == 10.0
        assert result["active_days"] == 4.0

    def test_terminal_statuses_excluded_from_total(self):
        per = [
            {"status": "doing", "total_days": 5.0, "ticket_count": 1, "avg_days": 5.0},
            {"status": "done", "total_days": 100.0, "ticket_count": 1, "avg_days": 100.0},
            {"status": "cancelled", "total_days": 50.0, "ticket_count": 1, "avg_days": 50.0},
        ]
        result = flow_efficiency(self._tis_result(per), active_statuses=("doing",))
        # done and cancelled excluded from total; total = 5, active = 5 → ratio = 1.0
        assert result["total_days"] == 5.0
        assert result["ratio"] == 1.0

    def test_result_has_required_keys(self):
        result = flow_efficiency({"per_status": [], "bottleneck": None})
        assert "active_days" in result
        assert "total_days" in result
        assert "ratio" in result


# ── forecast ──────────────────────────────────────────────────────────────────

class TestForecast:
    def _buckets(self, week_counts: list[tuple[str, int]]) -> list[dict]:
        """Build weekly bucket list from (YYYY-MM-DD monday, count) pairs."""
        return [{"bucket": k, "count": v} for k, v in week_counts]

    def test_empty_throughput_returns_zero(self):
        result = forecast([], backlog_size=10, now=NOW)
        assert result["weekly_rate"] == 0.0
        assert result["weeks_to_clear"] is None
        assert result["eta"] is None

    def test_zero_backlog_returns_zero(self):
        buckets = self._buckets([("2026-05-18", 5)])
        result = forecast(buckets, backlog_size=0, now=NOW)
        assert result["weekly_rate"] == 0.0
        assert result["weeks_to_clear"] is None

    def test_single_week_rate(self):
        # One completed week with 4 tickets, backlog=8 → 2 weeks to clear.
        # NOW week (2026-05-25) is current/incomplete, so only 2026-05-18 counts.
        buckets = self._buckets([
            ("2026-05-18", 4),   # completed week
            ("2026-05-25", 2),   # current week (incomplete, excluded by default)
        ])
        result = forecast(buckets, backlog_size=8, now=NOW)
        assert result["weekly_rate"] == 4.0
        assert result["weeks_to_clear"] == 2

    def test_multi_week_mean_rate(self):
        # 4 complete weeks: 4, 6, 4, 6 → mean = 5.0; backlog=10 → 2 weeks
        buckets = self._buckets([
            ("2026-04-27", 4),
            ("2026-05-04", 6),
            ("2026-05-11", 4),
            ("2026-05-18", 6),
        ])
        result = forecast(buckets, backlog_size=10, now=NOW)
        assert result["weekly_rate"] == 5.0
        assert result["weeks_to_clear"] == 2

    def test_eta_is_valid_iso_date(self):
        buckets = self._buckets([("2026-05-18", 5)])
        result = forecast(buckets, backlog_size=5, now=NOW)
        assert result["eta"] is not None
        from datetime import date
        date.fromisoformat(result["eta"])  # must not raise

    def test_zero_rate_returns_none(self):
        buckets = self._buckets([("2026-05-18", 0)])
        result = forecast(buckets, backlog_size=5, now=NOW)
        assert result["weeks_to_clear"] is None
        assert result["eta"] is None

    def test_result_keys(self):
        result = forecast([], backlog_size=0, now=NOW)
        assert "weekly_rate" in result
        assert "weeks_to_clear" in result
        assert "eta" in result


# ── stalled_view (F3 shaper) ──────────────────────────────────────────────────


class TestStalledView:
    """Tests for stalled_view() in holoctl.server.views.metrics."""

    def _t(self, **kw) -> dict:
        """Build a minimal ticket dict; updated defaults to 1 day ago."""
        updated = kw.pop(
            "updated",
            (NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        return {
            "id": kw.pop("id", "T-001"),
            "title": kw.pop("title", "A ticket"),
            "status": kw.pop("status", "backlog"),
            "updated": updated,
            "completed": kw.pop("completed", None),
            "agent": kw.pop("agent", []),
            "priority": kw.pop("priority", ""),
            **kw,
        }

    # ── empty state ──────────────────────────────────────────────────────────

    def test_empty_tickets_returns_empty(self):
        result = stalled_view([], now=NOW)
        assert result["count"] == 0
        assert result["tickets"] == []
        assert result["is_empty"] is True

    def test_all_healthy_returns_empty(self):
        tickets = [
            self._t(id="T-1", status="doing",
                    updated=(NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    agent=["alice"], priority="p1"),
            self._t(id="T-2", status="backlog",
                    agent=["bob"], priority="p2"),
        ]
        result = stalled_view(tickets, now=NOW, stale_days=5)
        assert result["is_empty"] is True

    # ── reason: active + stale ────────────────────────────────────────────────

    def test_doing_stale_flagged(self):
        tickets = [
            self._t(id="T-1", status="doing",
                    updated=(NOW - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    agent=["alice"], priority="p1"),
        ]
        result = stalled_view(tickets, now=NOW, stale_days=5)
        assert result["count"] == 1
        item = result["tickets"][0]
        assert item["id"] == "T-1"
        assert any("no update" in r for r in item["reasons"])

    def test_review_stale_flagged(self):
        tickets = [
            self._t(id="T-1", status="review",
                    updated=(NOW - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    agent=["alice"], priority="p1"),
        ]
        result = stalled_view(tickets, now=NOW, stale_days=5)
        assert result["count"] == 1
        assert any("no update" in r for r in result["tickets"][0]["reasons"])

    def test_doing_within_threshold_not_flagged(self):
        tickets = [
            self._t(id="T-1", status="doing",
                    updated=(NOW - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    agent=["alice"], priority="p1"),
        ]
        result = stalled_view(tickets, now=NOW, stale_days=5)
        assert result["is_empty"] is True

    # ── reason: backlog orphaned (no agent) ───────────────────────────────────

    def test_backlog_no_agent_flagged(self):
        tickets = [
            self._t(id="T-1", status="backlog", agent=[], priority="p1"),
        ]
        result = stalled_view(tickets, now=NOW)
        assert result["count"] == 1
        assert any("no agent" in r for r in result["tickets"][0]["reasons"])

    def test_backlog_with_agent_string_not_orphaned(self):
        # agent as a non-empty string (some callers pass string)
        tickets = [
            self._t(id="T-1", status="backlog", agent=["alice"], priority="p1"),
        ]
        result = stalled_view(tickets, now=NOW)
        assert result["is_empty"] is True

    # ── reason: backlog no priority ───────────────────────────────────────────

    def test_backlog_no_priority_flagged(self):
        tickets = [
            self._t(id="T-1", status="backlog", agent=["alice"], priority=""),
        ]
        result = stalled_view(tickets, now=NOW)
        assert result["count"] == 1
        assert any("no priority" in r for r in result["tickets"][0]["reasons"])

    def test_backlog_none_priority_flagged(self):
        tickets = [
            self._t(id="T-1", status="backlog", agent=["alice"], priority=None),
        ]
        result = stalled_view(tickets, now=NOW)
        assert result["count"] == 1
        assert any("no priority" in r for r in result["tickets"][0]["reasons"])

    def test_backlog_both_missing_has_two_reasons(self):
        tickets = [
            self._t(id="T-1", status="backlog", agent=[], priority=""),
        ]
        result = stalled_view(tickets, now=NOW)
        assert result["count"] == 1
        assert len(result["tickets"][0]["reasons"]) == 2

    # ── reason: done but completed is null ────────────────────────────────────

    def test_done_missing_completed_flagged(self):
        tickets = [
            self._t(id="T-1", status="done", completed=None,
                    agent=["alice"], priority="p1"),
        ]
        result = stalled_view(tickets, now=NOW)
        assert result["count"] == 1
        assert any("completed" in r for r in result["tickets"][0]["reasons"])

    def test_done_with_completed_not_flagged(self):
        tickets = [
            self._t(id="T-1", status="done",
                    completed=(NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    agent=["alice"], priority="p1"),
        ]
        result = stalled_view(tickets, now=NOW)
        assert result["is_empty"] is True

    # ── cancelled skipped ─────────────────────────────────────────────────────

    def test_cancelled_skipped(self):
        tickets = [
            self._t(id="T-1", status="cancelled", agent=[], priority=""),
        ]
        result = stalled_view(tickets, now=NOW)
        assert result["is_empty"] is True

    # ── ordering ──────────────────────────────────────────────────────────────

    def test_items_sorted_by_age_desc(self):
        tickets = [
            self._t(id="T-new", status="doing",
                    updated=(NOW - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    agent=["a"], priority="p1"),
            self._t(id="T-old", status="doing",
                    updated=(NOW - timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    agent=["a"], priority="p1"),
        ]
        result = stalled_view(tickets, now=NOW, stale_days=5)
        assert result["tickets"][0]["id"] == "T-old"
        assert result["tickets"][1]["id"] == "T-new"

    # ── required keys ─────────────────────────────────────────────────────────

    def test_result_has_required_keys(self):
        result = stalled_view([], now=NOW)
        assert "count" in result
        assert "tickets" in result
        assert "is_empty" in result

    def test_item_has_required_keys(self):
        tickets = [
            self._t(id="T-1", status="backlog", agent=[], priority=""),
        ]
        result = stalled_view(tickets, now=NOW)
        item = result["tickets"][0]
        assert "id" in item
        assert "title" in item
        assert "status" in item
        assert "age_days" in item
        assert "reasons" in item
        assert "link" in item

    # ── link generation ───────────────────────────────────────────────────────

    def test_link_with_project_alias(self):
        tickets = [
            self._t(id="T-1", status="backlog", agent=[], priority=""),
        ]
        result = stalled_view(tickets, now=NOW, project_alias="myproject")
        assert result["tickets"][0]["link"] == "/project/myproject/board/T-1"

    def test_link_without_project_alias(self):
        tickets = [
            self._t(id="T-1", status="backlog", agent=[], priority=""),
        ]
        result = stalled_view(tickets, now=NOW, project_alias="")
        assert result["tickets"][0]["link"] == "/board/T-1"

    def test_link_uses_source_alias_when_project_alias_empty(self):
        """Workspace-rolled tickets with _source_alias build /project/<alias>/board/<id>."""
        tickets = [
            {**self._t(id="T-42", status="backlog", agent=[], priority=""), "_source_alias": "myrepo"},
        ]
        result = stalled_view(tickets, now=NOW, project_alias="")
        assert result["tickets"][0]["link"] == "/project/myrepo/board/T-42"

    def test_link_project_alias_takes_precedence_over_source_alias(self):
        """Explicit project_alias wins over _source_alias."""
        tickets = [
            {**self._t(id="T-1", status="backlog", agent=[], priority=""), "_source_alias": "other"},
        ]
        result = stalled_view(tickets, now=NOW, project_alias="explicit")
        assert result["tickets"][0]["link"] == "/project/explicit/board/T-1"
