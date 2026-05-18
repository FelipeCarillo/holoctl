"""Tests for `hctl init` idempotency in 0.11."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.cli.init_ import _semver_lt, _semver_tuple, app as init_app
from holoctl import __version__


def test_semver_tuple_parses():
    assert _semver_tuple("1.2.3") == (1, 2, 3)
    assert _semver_tuple("0.0.0") == (0, 0, 0)
    # Malformed → (0, 0, 0) treated as oldest
    assert _semver_tuple("foo") == (0, 0, 0)


def test_semver_lt():
    assert _semver_lt("0.9.0", "0.10.0")
    assert _semver_lt("0.10.0", "0.11.0")
    assert not _semver_lt("0.11.0", "0.11.0")
    assert not _semver_lt("0.12.0", "0.11.0")


def test_init_idempotent_same_version_re_syncs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Running `hctl init` twice in same workspace at same version should
    re-sync templates non-destructively, not raise."""
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--skip-compile"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".holoctl" / "config.json").exists()

    # User customizes a ticket — must NOT be touched on re-sync.
    user_ticket = tmp_path / ".holoctl" / "board" / "tickets" / "X-001-my.md"
    user_ticket.write_text("---\nid: X-001\ntitle: mine\n---\n# user content", encoding="utf-8")

    # Run init again — same version → sync mode.
    result2 = runner.invoke(init_app, ["--skip-compile"])
    assert result2.exit_code == 0, result2.output
    # User ticket preserved.
    assert user_ticket.read_text(encoding="utf-8").startswith("---\nid: X-001")
    assert "user content" in user_ticket.read_text(encoding="utf-8")


def test_init_refuses_downgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Workspace version > installed → exit 2."""
    monkeypatch.chdir(tmp_path)
    holoctl_dir = tmp_path / ".holoctl"
    holoctl_dir.mkdir()
    (holoctl_dir / "config.json").write_text(
        json.dumps({
            "holoctlVersion": "99.0.0",
            "project": {"name": "X", "prefix": "X"},
        }),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(init_app, [])
    assert result.exit_code == 2
    assert "downgrade" in result.output.lower()


def test_init_directs_outdated_to_upgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Workspace version < installed → exit 0 with hint pointing at upgrade."""
    monkeypatch.chdir(tmp_path)
    holoctl_dir = tmp_path / ".holoctl"
    holoctl_dir.mkdir()
    (holoctl_dir / "config.json").write_text(
        json.dumps({
            "holoctlVersion": "0.0.1",
            "project": {"name": "X", "prefix": "X"},
        }),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(init_app, [])
    assert result.exit_code == 0
    assert "upgrade" in result.output.lower()


def test_init_bare_skips_compile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--bare"])
    assert result.exit_code == 0, result.output
    # Skeleton present but no compile output.
    assert (tmp_path / ".holoctl" / "config.json").exists()
    assert not (tmp_path / "CLAUDE.md").exists()


def test_init_creates_journal_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--skip-compile"])
    assert (tmp_path / ".holoctl" / "journal").is_dir()


def test_init_creates_memory_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--skip-compile"])
    assert (tmp_path / ".holoctl" / "memory" / "MEMORY.md").exists()
    assert (tmp_path / ".holoctl" / "memory" / ".gitignore").exists()


def test_init_creates_workspace_gitignore_with_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`.holoctl/.gitignore` is seeded so persona-suggester cache (and any
    other transient `.cache/` debris) never gets committed."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--skip-compile"])
    gi = tmp_path / ".holoctl" / ".gitignore"
    assert gi.exists()
    content = gi.read_text(encoding="utf-8")
    assert ".cache/" in content


def test_init_workspace_gitignore_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Re-running init must not clobber a user-edited `.holoctl/.gitignore`."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--skip-compile"])
    gi = tmp_path / ".holoctl" / ".gitignore"
    gi.write_text(
        gi.read_text(encoding="utf-8") + "\n# user added\nlocal-notes/\n",
        encoding="utf-8",
    )
    runner.invoke(init_app, ["--skip-compile"])
    after = gi.read_text(encoding="utf-8")
    assert "# user added" in after
    assert "local-notes/" in after
