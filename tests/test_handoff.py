"""Tests for `hctl handoff` — end-of-session persistence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.cli.handoff import _format_duration, _format_files_brief, app as handoff_app
from holoctl.lib.config import get_defaults, save_config
from holoctl.lib.journal import Journal
from holoctl.lib.memory import Memory


def _seed(tmp_path: Path) -> None:
    cfg = get_defaults()
    cfg["project"]["name"] = "HandoffTest"
    cfg["project"]["prefix"] = "HT"
    save_config(tmp_path, cfg)
    (tmp_path / ".holoctl" / "memory" / "topics").mkdir(parents=True, exist_ok=True)
    Memory(tmp_path).ensure_seed("HandoffTest")


def test_format_duration_subminute():
    assert _format_duration("2026-05-07T13:42:00Z", "2026-05-07T13:42:30Z") == "30s"


def test_format_duration_minutes():
    assert _format_duration("2026-05-07T13:00:00Z", "2026-05-07T13:42:00Z") == "42min"


def test_format_duration_hours_with_remainder():
    assert _format_duration("2026-05-07T10:00:00Z", "2026-05-07T13:42:00Z") == "3h42min"


def test_format_duration_exact_hours():
    assert _format_duration("2026-05-07T10:00:00Z", "2026-05-07T13:00:00Z") == "3h"


def test_format_files_brief_under_limit():
    assert _format_files_brief(["a.py", "b.py"]) == "a.py, b.py"


def test_format_files_brief_truncates():
    files = [f"f{i}.py" for i in range(10)]
    out = _format_files_brief(files, limit=3)
    assert out.startswith("f0.py, f1.py, f2.py")
    assert "(+7 more)" in out


def test_handoff_creates_session_trail_topic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    j = Journal(tmp_path)
    j.record("session_start", source="claude")
    j.record("tool_use", source="claude", payload={"tool": "Edit"})

    runner = CliRunner()
    result = runner.invoke(handoff_app, [])
    assert result.exit_code == 0, result.output

    mem = Memory(tmp_path)
    topic = mem.get_topic("session-trail")
    assert topic is not None
    assert "events: 1" in topic.body or "events: 2" in topic.body
    # Description set so it can be lazy-loaded by Claude/Cursor.
    assert "session" in topic.description.lower()


def test_handoff_appends_to_existing_trail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    mem = Memory(tmp_path)
    mem.add_topic(
        "session-trail",
        body="# Session trail\n\n- **2026-05-06** prior session line\n",
        scope="lazy",
        description="Recent session activity log",
    )
    j = Journal(tmp_path)
    j.record("tool_use", source="claude")

    runner = CliRunner()
    runner.invoke(handoff_app, ["--note", "shipped 0.12"])

    body = mem.get_topic("session-trail").body
    assert "prior session line" in body
    assert "shipped 0.12" in body


def test_handoff_records_journal_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(handoff_app, [])
    j = Journal(tmp_path)
    kinds = [r["kind"] for r in j.recent(limit=5)]
    assert "handoff" in kinds


def test_handoff_quiet_suppresses_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(handoff_app, ["--quiet"])
    assert result.exit_code == 0
    assert "session trail updated" not in result.output
