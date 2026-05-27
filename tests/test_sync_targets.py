"""F2 — the sync allow-list is a single source of truth and covers every
template-managed command, including `/spec` and `/agent-new` (which used to be
seeded once at init but never refreshed by sync/upgrade/re-init)."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.cli.init_ import app as init_app
from holoctl.cli.sync_ import app as sync_app
from holoctl.lib.config import get_defaults
from holoctl.lib.templates import SYNC_TARGETS, get_templates


def test_sync_targets_includes_spec_and_agent_new():
    assert ".holoctl/commands/spec.md" in SYNC_TARGETS
    assert ".holoctl/commands/agent-new.md" in SYNC_TARGETS


def test_every_sync_target_is_a_real_template():
    """Each path in the allow-list must actually be produced by get_templates,
    else `sync` silently no-ops on a path that will never match."""
    produced = set(get_templates(get_defaults()))
    missing = SYNC_TARGETS - produced
    assert not missing, f"SYNC_TARGETS references paths get_templates never emits: {missing}"


def test_call_sites_share_the_constant():
    """The three sync call sites must import the shared constant, not redefine
    their own copy (the drift that left /spec and /agent-new stale)."""
    import holoctl.cli.sync_ as sync_mod
    import holoctl.cli.upgrade_ as upgrade_mod
    from holoctl.lib import templates as templates_mod

    assert sync_mod.SYNC_TARGETS is templates_mod.SYNC_TARGETS
    assert upgrade_mod.SYNC_TARGETS is templates_mod.SYNC_TARGETS


def test_sync_refreshes_stale_spec_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A drifted spec.md must be restored to the template by `hctl sync`."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--skip-compile"])

    spec = tmp_path / ".holoctl" / "commands" / "spec.md"
    agent_new = tmp_path / ".holoctl" / "commands" / "agent-new.md"
    assert spec.exists() and agent_new.exists()

    spec.write_text("stale hand-broken content\n", encoding="utf-8")
    agent_new.write_text("stale\n", encoding="utf-8")

    result = runner.invoke(sync_app, [])
    assert result.exit_code == 0, result.output

    fresh = get_templates(get_defaults())
    # Project name/prefix differ from defaults, so compare structurally: the
    # refreshed file must no longer be the stale stub and must look like the
    # real command (has its frontmatter `name:`).
    assert "stale" not in spec.read_text(encoding="utf-8")
    assert "name: spec" in spec.read_text(encoding="utf-8")
    assert "stale" not in agent_new.read_text(encoding="utf-8")
    assert "name: agent-new" in agent_new.read_text(encoding="utf-8")


def test_reinit_refreshes_stale_spec_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Re-running `hctl init` at the same version also refreshes spec.md."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--skip-compile"])

    spec = tmp_path / ".holoctl" / "commands" / "spec.md"
    spec.write_text("stale\n", encoding="utf-8")

    runner.invoke(init_app, ["--skip-compile"])
    assert "stale" not in spec.read_text(encoding="utf-8")
    assert "name: spec" in spec.read_text(encoding="utf-8")
