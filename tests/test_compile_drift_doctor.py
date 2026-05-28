"""F13 — `hctl doctor --compile-drift` detects compiled outputs that are stale
vs `.holoctl/` (source edited but `hctl compile` not re-run)."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.__main__ import app

runner = CliRunner()


def _init(tmp_path: Path) -> None:
    res = runner.invoke(app, ["init", "--name", "Drift", "--prefix", "DR",
                              "--targets", "agents,claude"])
    assert res.exit_code == 0, res.output


def test_fresh_compile_reports_no_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    res = runner.invoke(app, ["doctor", "--compile-drift"])
    assert res.exit_code == 0, res.output
    assert "holoctl: ok" in res.output
    assert "in sync" in res.output


def test_edited_source_reports_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    # Change the source without recompiling → CLAUDE.md / AGENTS.md go stale.
    (tmp_path / ".holoctl" / "instructions.md").write_text(
        "# Drift\n\nCHANGED but not recompiled.\n", encoding="utf-8"
    )
    res = runner.invoke(app, ["doctor", "--compile-drift"])
    assert res.exit_code == 1, res.output
    assert "holoctl: compile-drift" in res.output
    assert "stale" in res.output
    assert "CLAUDE.md" in res.output

    # Recompiling clears the drift.
    assert runner.invoke(app, ["compile"]).exit_code == 0
    res2 = runner.invoke(app, ["doctor", "--compile-drift"])
    assert res2.exit_code == 0, res2.output
    assert "holoctl: ok" in res2.output


def test_hand_edited_output_is_not_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    # User hand-edits CLAUDE.md (strips the holoctl header) — intentional, not drift.
    (tmp_path / "CLAUDE.md").write_text("# My own CLAUDE\n\nmine.\n", encoding="utf-8")
    res = runner.invoke(app, ["doctor", "--compile-drift"])
    assert res.exit_code == 0, res.output
    assert "holoctl: ok" in res.output
    assert "Hand-edited" in res.output
