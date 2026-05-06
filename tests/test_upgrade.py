"""Tests for `hctl upgrade` — orchestrates sync/compile/rebuild-index/version bump."""
from __future__ import annotations
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.__main__ import app
from holoctl.lib.config import load_config


runner = CliRunner()


def _patch_version(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    """Force both `holoctl.__version__` and the alias inside `cli.upgrade_`
    to a known value, so tests don't depend on the real wheel version."""
    import holoctl
    import holoctl.cli.upgrade_ as upgrade_mod
    monkeypatch.setattr(holoctl, "__version__", version)
    monkeypatch.setattr(upgrade_mod, "__version__", version)


def _write_config_version(workspace: Path, version: str) -> None:
    config_path = workspace / ".holoctl" / "config.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg["holoctlVersion"] = version
    cfg["targets"] = ["claude"]
    config_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def test_check_when_already_in_sync(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """workspace_version == installed_version → 'Already in sync', no writes."""
    _patch_version(monkeypatch, "0.8.1")
    _write_config_version(workspace, "0.8.1")
    monkeypatch.chdir(workspace)

    result = runner.invoke(app, ["upgrade", "--check"])

    assert result.exit_code == 0, result.stdout
    assert "Already in sync" in result.stdout
    # No CLAUDE.md was written
    assert not (workspace / "CLAUDE.md").exists()


def test_check_shows_old_and_new_versions(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """--check on a stale workspace shows both versions but writes nothing."""
    _patch_version(monkeypatch, "0.8.1")
    _write_config_version(workspace, "0.7.0")
    monkeypatch.chdir(workspace)

    result = runner.invoke(app, ["upgrade", "--check"])

    assert result.exit_code == 0, result.stdout
    assert "0.7.0" in result.stdout
    assert "0.8.1" in result.stdout
    # config.json untouched
    assert load_config(workspace)["holoctlVersion"] == "0.7.0"
    # No compile happened
    assert not (workspace / "CLAUDE.md").exists()


def test_dry_run_does_not_bump_version(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """--dry-run shows what would happen but never bumps holoctlVersion."""
    _patch_version(monkeypatch, "0.8.1")
    _write_config_version(workspace, "0.7.0")
    monkeypatch.chdir(workspace)

    result = runner.invoke(app, ["upgrade", "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert load_config(workspace)["holoctlVersion"] == "0.7.0"


def test_full_run_bumps_version_and_compiles(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """A real upgrade bumps holoctlVersion and writes the Claude target files."""
    _patch_version(monkeypatch, "0.8.1")
    _write_config_version(workspace, "0.7.0")
    # `instructions.md` is required by the Claude compiler to write CLAUDE.md;
    # plant it the way `init` would.
    (workspace / ".holoctl" / "instructions.md").write_text(
        "# Test Project\n\nBootstrap content.\n", encoding="utf-8"
    )
    monkeypatch.chdir(workspace)

    result = runner.invoke(app, ["upgrade"])

    assert result.exit_code == 0, result.stdout
    assert load_config(workspace)["holoctlVersion"] == "0.8.1"
    assert (workspace / "CLAUDE.md").exists()
    assert (workspace / ".claude" / "commands" / "holoctl.md").exists()
    assert (workspace / ".claude" / "commands" / "hctl-upgrade.md").exists()


def test_full_run_preserves_user_ticket_bodies(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """User-authored ticket .md must be byte-identical after upgrade.

    Templates managed by `sync` (e.g. `_template.md`) may legitimately change;
    only files NOT in the sync_targets set must survive untouched.
    """
    _patch_version(monkeypatch, "0.8.1")
    _write_config_version(workspace, "0.7.0")
    (workspace / ".holoctl" / "instructions.md").write_text(
        "# Test\n", encoding="utf-8"
    )

    user_ticket = workspace / ".holoctl" / "board" / "tickets" / "TST-001-example.md"
    original_body = (
        "---\n"
        "id: TST-001\n"
        "title: User-authored ticket\n"
        "agent: developer\n"
        "status: backlog\n"
        "priority: p2\n"
        "projects: []\n"
        "files: []\n"
        "created: 2026-05-06T00:00:00Z\n"
        "updated: 2026-05-06T00:00:00Z\n"
        "---\n\n"
        "# Goal — Definition of Done\n\n- [ ] do the thing\n"
    )
    user_ticket.write_text(original_body, encoding="utf-8")

    user_decision = workspace / ".holoctl" / "context" / "decisions" / "0001-pick-sqlite.md"
    user_decision.parent.mkdir(parents=True, exist_ok=True)
    decision_body = "# 0001 Pick SQLite\n\nContext content the user wrote.\n"
    user_decision.write_text(decision_body, encoding="utf-8")

    monkeypatch.chdir(workspace)
    result = runner.invoke(app, ["upgrade"])

    assert result.exit_code == 0, result.stdout
    assert user_ticket.read_text(encoding="utf-8") == original_body
    assert user_decision.read_text(encoding="utf-8") == decision_body


def test_downgrade_is_refused(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """Installed older than workspace → exit 2, no writes."""
    _patch_version(monkeypatch, "0.7.0")
    _write_config_version(workspace, "0.8.1")
    monkeypatch.chdir(workspace)

    result = runner.invoke(app, ["upgrade"])

    assert result.exit_code == 2
    assert load_config(workspace)["holoctlVersion"] == "0.8.1"


def test_upgrade_without_holoctl_dir_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """No `.holoctl/` in cwd → exit 1 with a helpful message."""
    _patch_version(monkeypatch, "0.8.1")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["upgrade"])

    assert result.exit_code == 1
    assert "No .holoctl/" in result.stdout
