"""Task 23 — `hctl doctor` MCP health + ecosystem awareness sections."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.__main__ import app

runner = CliRunner()


def _init_compile(tmp_path: Path) -> None:
    """Init a fresh workspace with both targets, then compile."""
    res = runner.invoke(app, ["init", "--name", "EcoTest", "--prefix", "ET",
                              "--targets", "agents,claude"])
    assert res.exit_code == 0, res.output


# ---------------------------------------------------------------------------
# MCP health — hctl on PATH + mcpServers.holoctl registration
# ---------------------------------------------------------------------------


def test_mcp_health_ok_after_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """After init (which compiles), MCP section reports hctl resolvable + registered."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    # `hctl` is on PATH in the test environment (invoked via the runner), but
    # the real binary may not be.  Patch shutil.which to always return a fake
    # path so the test is deterministic regardless of the CI environment.
    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0, res.output
    # MCP resolvable line must appear.
    assert "hctl resolvable" in res.output
    # Registration line must appear.
    assert "mcpServers.holoctl registered" in res.output
    # No MCP issues → "All checks passed" path.
    assert "All checks passed" in res.output


def test_mcp_health_missing_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Removing mcpServers.holoctl from settings.json is reported as an issue."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    # Strip the holoctl MCP registration from settings.
    settings_path = tmp_path / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["mcpServers"].pop("holoctl", None)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    res = runner.invoke(app, ["doctor"])
    # Must flag the missing registration.
    assert "mcpServers.holoctl missing" in res.output
    # The issue counter must be non-zero.
    assert "issue(s) found" in res.output


def test_mcp_health_hctl_not_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When shutil.which can't find hctl, doctor flags it as an issue."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: None)

    res = runner.invoke(app, ["doctor"])
    assert "hctl not on PATH" in res.output
    assert "issue(s) found" in res.output


# ---------------------------------------------------------------------------
# Ecosystem — managed vs foreign classification
# ---------------------------------------------------------------------------


def test_ecosystem_all_managed_after_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """After a clean init+compile, all agents/commands/skills are managed (no foreign)."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0, res.output
    # Ecosystem section must appear.
    assert "Ecosystem" in res.output
    # No foreign items → no "hctl adopt" hint.
    assert "hctl adopt" not in res.output


def test_ecosystem_foreign_agent_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A .claude/agents/*.md not in the manifest is listed as foreign."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    # Drop a foreign agent — NOT in the manifest.
    foreign_agent = tmp_path / ".claude" / "agents" / "handmade.md"
    foreign_agent.parent.mkdir(parents=True, exist_ok=True)
    foreign_agent.write_text(
        "---\nname: handmade\ndescription: hand-crafted agent\n---\n",
        encoding="utf-8",
    )

    res = runner.invoke(app, ["doctor"])
    assert "foreign agent: handmade.md" in res.output
    assert "hctl adopt" in res.output
    # Foreign items must NOT cause a non-zero issue count on their own.
    assert "issue(s) found" not in res.output
    assert "All checks passed" in res.output


def test_ecosystem_foreign_command_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A .claude/commands/*.md not in the manifest (and not a bootstrap cmd) is foreign."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    foreign_cmd = tmp_path / ".claude" / "commands" / "my-custom-cmd.md"
    foreign_cmd.parent.mkdir(parents=True, exist_ok=True)
    foreign_cmd.write_text("# My custom command\n\nDoes something.", encoding="utf-8")

    res = runner.invoke(app, ["doctor"])
    assert "foreign command: my-custom-cmd.md" in res.output
    assert "hctl adopt" in res.output
    assert "All checks passed" in res.output


def test_ecosystem_foreign_skill_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A .claude/skills/<name>/ dir whose SKILL.md is absent from the manifest is foreign."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    foreign_skill = tmp_path / ".claude" / "skills" / "my-skill"
    foreign_skill.mkdir(parents=True, exist_ok=True)
    (foreign_skill / "SKILL.md").write_text("# My skill\n\nContent.", encoding="utf-8")

    res = runner.invoke(app, ["doctor"])
    assert "foreign skill: my-skill" in res.output
    assert "hctl adopt" in res.output
    assert "All checks passed" in res.output


def test_ecosystem_bootstrap_commands_not_foreign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The holoctl bootstrap commands (holoctl.md, hctl-upgrade.md) are NOT listed as foreign."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    res = runner.invoke(app, ["doctor"])
    # holoctl.md and hctl-upgrade.md must not appear in foreign list.
    assert "foreign command: holoctl.md" not in res.output
    assert "foreign command: hctl-upgrade.md" not in res.output


def test_ecosystem_foreign_mcp_server_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A third-party MCP server in .mcp.json appears as third-party in the Ecosystem section."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"filesystem": {"command": "npx", "args": []}}}),
        encoding="utf-8",
    )

    res = runner.invoke(app, ["doctor"])
    assert "filesystem" in res.output
    # Foreign MCP servers must NOT cause issues.
    assert "All checks passed" in res.output


def test_ecosystem_foreign_items_no_issue_increment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Foreign ecosystem items (all kinds) must not increment the issue counter."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    # Plant one of each foreign item type.
    agent_f = tmp_path / ".claude" / "agents" / "foreign-agent.md"
    agent_f.write_text("---\nname: foreign-agent\ndescription: x\n---\n", encoding="utf-8")

    cmd_f = tmp_path / ".claude" / "commands" / "foreign-cmd.md"
    cmd_f.write_text("# Foreign cmd\n", encoding="utf-8")

    skill_f = tmp_path / ".claude" / "skills" / "foreign-skill"
    skill_f.mkdir(parents=True, exist_ok=True)
    (skill_f / "SKILL.md").write_text("# Foreign skill\n", encoding="utf-8")

    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"third-party": {}}}), encoding="utf-8"
    )

    res = runner.invoke(app, ["doctor"])
    # All foreign items listed.
    assert "foreign-agent.md" in res.output
    assert "foreign-cmd.md" in res.output
    assert "foreign-skill" in res.output
    assert "third-party" in res.output
    # Adopt hint present.
    assert "hctl adopt" in res.output
    # No issue bump — health stays green.
    assert "All checks passed" in res.output
    assert "issue(s) found" not in res.output


def test_ecosystem_managed_agents_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Managed agents are counted and NOT listed as foreign."""
    monkeypatch.chdir(tmp_path)
    _init_compile(tmp_path)

    import holoctl.cli.doctor as doctor_mod
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _name: "/usr/local/bin/hctl")

    # Count how many .claude/agents/*.md exist (all should be managed after compile).
    claude_agents = list((tmp_path / ".claude" / "agents").glob("*.md"))
    assert len(claude_agents) > 0, "Expected compiled agents"

    res = runner.invoke(app, ["doctor"])
    # The managed count should be non-zero and no "foreign agent" hint.
    assert f"Agents: {len(claude_agents)} managed, 0 foreign" in res.output
    assert "foreign agent" not in res.output
