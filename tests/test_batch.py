"""Tests for Board.batch_add — parallel-safe ticket creation."""
from __future__ import annotations
from pathlib import Path

import pytest

from holoctl.lib.board import Board


def test_batch_creates_all_tickets(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    result = board.batch_add(
        shared={"tags": ["par:auth"], "projects": ["backend"]},
        tickets=[
            {"title": "Sign", "agent": "developer", "files": ["src/sign.py"]},
            {"title": "Verify", "agent": "developer", "files": ["src/verify.py"]},
            {"title": "Tests", "agent": "reviewer", "files": ["tests/auth.py"]},
        ],
    )
    assert result["count"] == 3
    ids = [t["id"] for t in result["tickets"]]
    assert ids == ["TST-001", "TST-002", "TST-003"]


def test_batch_applies_shared_fields(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    result = board.batch_add(
        shared={"tags": ["par:auth"], "projects": ["backend"], "sprint": "s1"},
        tickets=[
            {"title": "A", "agent": "developer", "files": ["a.py"]},
            {"title": "B", "agent": "developer", "files": ["b.py"]},
        ],
    )
    for t in result["tickets"]:
        assert "par:auth" in t["tags"]
        assert "backend" in t["projects"]
        assert t["sprint"] == "s1"


def test_batch_per_ticket_overrides_shared(workspace: Path, workspace_config: dict):
    """Per-ticket agent wins over shared agent. Arrays merge additively."""
    board = Board(workspace, workspace_config)
    result = board.batch_add(
        shared={"tags": ["par:x"], "agent": ["developer"]},
        tickets=[
            {"title": "A", "files": ["a.py"]},  # inherits developer
            {"title": "B", "files": ["b.py"], "agent": "reviewer", "tags": ["urgent"]},
        ],
    )
    assert result["tickets"][0]["agent"] == ["developer"]
    # Per-ticket merges with shared tags (additive, dedupe).
    assert "par:x" in result["tickets"][1]["tags"]
    assert "urgent" in result["tickets"][1]["tags"]
    # Per-ticket agent wins:
    assert "reviewer" in result["tickets"][1]["agent"]


def test_batch_rejects_file_overlap(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="File overlap"):
        board.batch_add(
            shared={},
            tickets=[
                {"title": "A", "agent": "developer", "files": ["src/auth.py"]},
                {"title": "B", "agent": "developer", "files": ["src/auth.py", "src/db.py"]},
            ],
        )
    # Atomic: nothing should have been created.
    after = Board(workspace, workspace_config).ls()
    assert after == []


def test_batch_rejects_missing_files_field(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="no `files` field"):
        board.batch_add(
            shared={},
            tickets=[
                {"title": "A", "agent": "developer", "files": ["a.py"]},
                {"title": "B", "agent": "developer"},  # missing files
            ],
        )
    # Atomic.
    assert Board(workspace, workspace_config).ls() == []


def test_batch_rejects_sibling_dependency(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="sibling"):
        board.batch_add(
            shared={},
            tickets=[
                {"title": "Sign", "agent": "developer", "files": ["sign.py"]},
                {"title": "Verify", "agent": "developer", "files": ["verify.py"], "depends": ["Sign"]},
            ],
        )


def test_batch_rejects_invalid_priority(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="Invalid priority"):
        board.batch_add(
            shared={},
            tickets=[
                {"title": "A", "agent": "developer", "files": ["a.py"], "priority": "high"},
            ],
        )
    assert Board(workspace, workspace_config).ls() == []


def test_batch_rejects_unknown_agent(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="Unknown agent"):
        board.batch_add(
            shared={},
            tickets=[
                {"title": "A", "agent": "intern", "files": ["a.py"]},
            ],
        )


def test_batch_rejects_empty_tickets(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="Batch is empty"):
        board.batch_add(shared={}, tickets=[])


def test_batch_files_field_persisted_in_md(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    result = board.batch_add(
        shared={},
        tickets=[
            {"title": "A", "agent": "developer", "files": ["src/foo.py", "src/bar.py"]},
        ],
    )
    md = (workspace / ".holoctl" / "board" / result["tickets"][0]["file"]).read_text(encoding="utf-8")
    assert "files: src/foo.py, src/bar.py" in md


def test_batch_external_dep_is_allowed(workspace: Path, workspace_config: dict):
    """Depending on a ticket OUTSIDE the batch (already-existing ID) is fine."""
    board = Board(workspace, workspace_config)
    pre = board.add({"title": "Foundation", "agent": "developer"})
    result = board.batch_add(
        shared={},
        tickets=[
            {"title": "A", "agent": "developer", "files": ["a.py"], "depends": [pre["id"]]},
            {"title": "B", "agent": "developer", "files": ["b.py"], "depends": [pre["id"]]},
        ],
    )
    assert result["count"] == 2
    for t in result["tickets"]:
        assert pre["id"] in t["depends"]


def test_add_persists_files_field_when_provided(workspace: Path, workspace_config: dict):
    """Regular `add` (not batch) also accepts and persists `files`."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer", "files": ["src/a.py", "src/b.py"]})
    assert t["files"] == ["src/a.py", "src/b.py"]
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "files: src/a.py, src/b.py" in md


def test_add_files_optional_default_empty(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer"})
    assert t["files"] == []
