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
    # User hand-edits a compiled, manifest-tracked CLAUDE.md — intentional, not drift.
    (tmp_path / "CLAUDE.md").write_text("# My own CLAUDE\n\nmine.\n", encoding="utf-8")
    res = runner.invoke(app, ["doctor", "--compile-drift"])
    assert res.exit_code == 0, res.output
    assert "holoctl: ok" in res.output
    assert "Hand-edited" in res.output


def test_hand_edited_managed_agent_is_not_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Hand-editing a MANAGED agent (not CLAUDE.md) must be reported as
    hand-edited, not stale — its manifest entry survives the recompile so drift
    classifies it by hash mismatch rather than by absence."""
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)

    # Find a holoctl-managed agent output and hand-edit it.
    agents_dir = tmp_path / ".claude" / "agents"
    managed = sorted(agents_dir.glob("*.md"))
    assert managed, "expected at least one compiled agent"
    target = managed[0]
    rel = f".claude/agents/{target.name}"
    target.write_text("# hand-edited agent\n", encoding="utf-8")

    # A recompile hits the skip branch for this owned-but-diverged file; it must
    # keep the manifest entry so drift can tell hand-edit from stale.
    assert runner.invoke(app, ["compile"]).exit_code == 0

    res = runner.invoke(app, ["doctor", "--compile-drift"])
    assert res.exit_code == 0, res.output
    assert "holoctl: ok" in res.output
    assert "Hand-edited" in res.output
    assert target.name in res.output
    assert "stale" not in res.output
    # The hand-edit survived the recompile.
    assert target.read_text(encoding="utf-8") == "# hand-edited agent\n"


def test_compile_drift_cross_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Both `claude` and `agents` outputs are checked; a fresh compile of a
    multi-target workspace must report no false drift on either side."""
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)  # inits with both agents + claude targets

    # Sanity: both targets' headline outputs exist.
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / "AGENTS.md").exists()

    res = runner.invoke(app, ["doctor", "--compile-drift"])
    assert res.exit_code == 0, res.output
    assert "holoctl: ok" in res.output
    assert "in sync" in res.output
    # The targets line names both.
    assert "claude" in res.output
    assert "agents" in res.output
