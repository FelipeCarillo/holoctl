"""CLI integration tests for `hctl board` — covers tree rendering + batch --schema."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.cli.init_ import app as init_app
from holoctl.cli.board import app as board_app


@pytest.fixture
def cli_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace initialized via `hctl init` (so the CLI's find_project_root works)."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--skip-compile"])
    assert result.exit_code == 0, result.output
    return tmp_path


def test_batch_schema_flag_prints_payload_structure(cli_workspace: Path):
    """`hctl board batch --schema` prints the payload schema and exits 0."""
    runner = CliRunner()
    result = runner.invoke(board_app, ["batch", "--schema"])
    assert result.exit_code == 0
    # Schema mentions both top-level keys and a couple of nested fields.
    assert "shared" in result.output
    assert "tickets" in result.output
    assert "files" in result.output
    assert "source_provider" in result.output


def test_batch_help_includes_schema_example(cli_workspace: Path):
    """`hctl board batch --help` surfaces the JSON example, not just a one-liner."""
    runner = CliRunner()
    result = runner.invoke(board_app, ["batch", "--help"])
    assert result.exit_code == 0
    assert "shared" in result.output
    assert "tickets" in result.output


def test_ls_tree_renders_glyphs(cli_workspace: Path):
    """`hctl board ls --tree` prints ├─/└─ when a hierarchy exists."""
    runner = CliRunner()
    # Build a spec + 2 children via the add CLI so we exercise the full path.
    # Use `boardmaster` because that's the only agent seeded by default init.
    r1 = runner.invoke(board_app, ["add", json.dumps({"title": "Spec", "kind": "spec"})])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(board_app, ["add", json.dumps({"title": "C1", "agent": "boardmaster", "parent": "X-001"})])
    assert r2.exit_code == 0, r2.output
    r3 = runner.invoke(board_app, ["add", json.dumps({"title": "C2", "agent": "boardmaster", "parent": "X-001"})])
    assert r3.exit_code == 0, r3.output

    result = runner.invoke(board_app, ["ls", "--tree"])
    assert result.exit_code == 0, result.output
    # At least one of ├─ / └─ must be present in the rendered output.
    assert "├─" in result.output or "└─" in result.output


def test_children_deep_prints_subtree(cli_workspace: Path):
    """`hctl board children <ID> --deep` walks the full subtree."""
    runner = CliRunner()
    r1 = runner.invoke(board_app, ["add", json.dumps({"title": "Spec", "kind": "spec"})])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(board_app, ["add", json.dumps({"title": "C1", "agent": "boardmaster", "parent": "X-001"})])
    assert r2.exit_code == 0, r2.output
    r3 = runner.invoke(board_app, ["add", json.dumps({"title": "GC1", "agent": "boardmaster", "parent": "X-002"})])
    assert r3.exit_code == 0, r3.output

    result = runner.invoke(board_app, ["children", "X-001", "--deep"])
    assert result.exit_code == 0, result.output
    assert "X-001" in result.output
    assert "X-002" in result.output
    assert "X-003" in result.output  # grandchild rendered too
