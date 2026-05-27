"""Task 24 — `hctl adopt`: bring foreign Claude config under holoctl management.

Covers:
  1. `scan_unmanaged` finds foreign agent/command/skill, excludes managed +
     bootstrap commands, reports foreign MCP servers.
  2. `hctl adopt` (no args) previews and adopts nothing.
  3. Adopt a foreign agent → reverse-mapped `.holoctl/agents/<name>.md`,
     recorded in the manifest; THEN compile takes over (round-trip).
  4. Adopt a foreign skill (with support file) → copied + manifest records
     SKILL.md + support file; compile takes over.
  5. Adopt refuses when `.holoctl/<type>/<name>` already exists (no --force).
  6. Reverse-map unit tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.__main__ import app
from holoctl.cli.adopt import _reverse_model, _reverse_tools
from holoctl.lib.compiler import compile_project, manifest
from holoctl.lib.config import load_config
from holoctl.lib.ecosystem import scan_unmanaged
from holoctl.lib.markdown import parse_frontmatter

runner = CliRunner()


def _init() -> None:
    res = runner.invoke(
        app, ["init", "--name", "AdoptTest", "--prefix", "AT", "--targets", "agents,claude"]
    )
    assert res.exit_code == 0, res.output


def _write_foreign_agent(root: Path, name: str = "handmade") -> Path:
    p = root / ".claude" / "agents" / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\n"
        f"name: {name}\n"
        "description: a hand-crafted subagent\n"
        "tools: Read, Grep, Glob, Edit, Write, Bash\n"
        "model: sonnet\n"
        "---\n"
        "# Hand-crafted body\n\nDoes things.\n",
        encoding="utf-8",
    )
    return p


def _write_foreign_command(root: Path, name: str = "mycmd") -> Path:
    p = root / ".claude" / "commands" / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# My custom command\n\nRun stuff.\n", encoding="utf-8")
    return p


def _write_foreign_skill(root: Path, name: str = "myskill") -> Path:
    d = root / ".claude" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "---\nname: myskill\ndescription: a skill\n---\n# Skill body\n", encoding="utf-8"
    )
    (d / "references").mkdir(exist_ok=True)
    (d / "references" / "notes.md").write_text("# reference notes\n", encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# 6. Reverse-map unit tests
# ---------------------------------------------------------------------------


def test_reverse_tools_full_set():
    assert _reverse_tools(["Read", "Grep", "Glob", "Edit", "Write", "Bash"]) == [
        "read",
        "search",
        "edit",
        "write",
        "shell",
    ]


def test_reverse_tools_comma_string():
    assert _reverse_tools("Read, Grep, Glob") == ["read", "search"]


def test_reverse_tools_unknown_passthrough():
    assert _reverse_tools(["Read", "MysteryTool"]) == ["read", "MysteryTool"]


def test_reverse_model():
    assert _reverse_model("sonnet") == "standard"
    assert _reverse_model("haiku") == "fast"
    assert _reverse_model("opus") == "reasoning"
    # Unknown passes through.
    assert _reverse_model("gpt-9") == "gpt-9"
    assert _reverse_model(None) is None


# ---------------------------------------------------------------------------
# 1. scan_unmanaged classification
# ---------------------------------------------------------------------------


def test_scan_unmanaged_classifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init()

    _write_foreign_agent(tmp_path)
    _write_foreign_command(tmp_path)
    _write_foreign_skill(tmp_path)
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"filesystem": {}, "holoctl": {}}}), encoding="utf-8"
    )

    found = scan_unmanaged(tmp_path)
    assert "handmade" in found["agents"]
    assert "mycmd" in found["commands"]
    assert "myskill" in found["skills"]
    # Bootstrap commands are never foreign.
    assert "holoctl" not in found["commands"]
    assert "hctl-upgrade" not in found["commands"]
    # holoctl-managed agents (compiled) are not foreign.
    compiled_agents = [p.stem for p in (tmp_path / ".claude" / "agents").glob("*.md")]
    managed = [a for a in compiled_agents if a != "handmade"]
    for a in managed:
        assert a not in found["agents"]
    # MCP: holoctl excluded, foreign reported.
    assert found["mcp_servers"] == ["filesystem"]


def test_scan_unmanaged_robust_to_missing_dirs(tmp_path: Path):
    # No .claude/ at all → empty groups, no raise.
    found = scan_unmanaged(tmp_path)
    assert found == {"agents": [], "commands": [], "skills": [], "mcp_servers": []}


# ---------------------------------------------------------------------------
# 2. Preview adopts nothing
# ---------------------------------------------------------------------------


def test_adopt_preview_adopts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init()
    _write_foreign_agent(tmp_path)

    manifest_before = manifest.load(tmp_path)["files"]
    holoctl_agents_before = sorted((tmp_path / ".holoctl" / "agents").glob("*.md"))

    res = runner.invoke(app, ["adopt"])
    assert res.exit_code == 0, res.output
    assert "preview" in res.output.lower()
    assert "handmade" in res.output

    # Nothing changed.
    assert manifest.load(tmp_path)["files"] == manifest_before
    assert sorted((tmp_path / ".holoctl" / "agents").glob("*.md")) == holoctl_agents_before
    assert not (tmp_path / ".holoctl" / "agents" / "handmade.md").exists()


# ---------------------------------------------------------------------------
# 3. Adopt agent → reverse-mapped source + manifest record + compile round-trip
# ---------------------------------------------------------------------------


def test_adopt_agent_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init()
    foreign = _write_foreign_agent(tmp_path)
    foreign_before = foreign.read_text(encoding="utf-8")

    res = runner.invoke(app, ["adopt", "--type", "agent", "--name", "handmade"])
    assert res.exit_code == 0, res.output
    assert "adopted" in res.output.lower()

    # .holoctl/agents/handmade.md created with reverse-mapped frontmatter.
    src = tmp_path / ".holoctl" / "agents" / "handmade.md"
    assert src.exists()
    data, body = parse_frontmatter(src.read_text(encoding="utf-8"))
    assert data["name"] == "handmade"
    # tools reverse-mapped to categories.
    tools = [t.strip() for t in str(data["tools"]).split(",")]
    assert tools == ["read", "search", "edit", "write", "shell"]
    # model reverse-mapped to tier.
    assert data["model"] == "standard"
    assert "Hand-crafted body" in body

    # The .claude/ file is now recorded in the manifest (as the current content).
    rel = ".claude/agents/handmade.md"
    tracked = manifest.load(tmp_path)["files"]
    assert rel in tracked
    assert tracked[rel]["sha256"] == manifest.sha256_text(foreign_before)
    assert tracked[rel]["source"] == ".holoctl/agents/handmade.md"
    assert tracked[rel]["target"] == "claude"

    # NOW compile — the file must be regenerated/owned (NOT preserved-as-foreign).
    config = load_config(tmp_path)
    result = compile_project(tmp_path, config, "claude")
    assert rel in result["files"]
    # Not skipped as foreign/hand-edited.
    skipped_paths = {s["path"] for s in result.get("skipped", [])}
    assert rel not in skipped_paths

    # Round-trip: the compiled .claude tools forward-map back correctly.
    compiled_text = (tmp_path / rel).read_text(encoding="utf-8")
    cdata, _ = parse_frontmatter(compiled_text)
    compiled_tools = [t.strip() for t in str(cdata["tools"]).split(",")]
    assert compiled_tools == ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]
    assert cdata["model"] == "sonnet"


# ---------------------------------------------------------------------------
# 4. Adopt skill (with support file) → copied + manifest + compile takeover
# ---------------------------------------------------------------------------


def test_adopt_skill_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init()
    _write_foreign_skill(tmp_path)

    res = runner.invoke(app, ["adopt", "--type", "skill", "--name", "myskill"])
    assert res.exit_code == 0, res.output

    # Copied into .holoctl/skills/myskill/.
    src_dir = tmp_path / ".holoctl" / "skills" / "myskill"
    assert (src_dir / "SKILL.md").exists()
    assert (src_dir / "references" / "notes.md").exists()

    tracked = manifest.load(tmp_path)["files"]
    skill_rel = ".claude/skills/myskill/SKILL.md"
    support_rel = ".claude/skills/myskill/references/notes.md"
    assert skill_rel in tracked
    assert support_rel in tracked

    # Compile takes over (SKILL.md owned, not preserved as foreign).
    config = load_config(tmp_path)
    result = compile_project(tmp_path, config, "claude")
    assert skill_rel in result["files"]
    skipped_paths = {s["path"] for s in result.get("skipped", [])}
    assert skill_rel not in skipped_paths
    assert support_rel not in skipped_paths


def test_adopt_command_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init()
    _write_foreign_command(tmp_path, "mycmd")
    foreign_before = (tmp_path / ".claude" / "commands" / "mycmd.md").read_text(encoding="utf-8")

    res = runner.invoke(app, ["adopt", "--type", "command"])
    assert res.exit_code == 0, res.output

    src = tmp_path / ".holoctl" / "commands" / "mycmd.md"
    assert src.exists()
    # Verbatim copy.
    assert src.read_text(encoding="utf-8") == foreign_before

    rel = ".claude/commands/mycmd.md"
    tracked = manifest.load(tmp_path)["files"]
    assert rel in tracked

    config = load_config(tmp_path)
    result = compile_project(tmp_path, config, "claude")
    assert rel in result["files"]
    skipped_paths = {s["path"] for s in result.get("skipped", [])}
    assert rel not in skipped_paths


# ---------------------------------------------------------------------------
# 5. Refuse when source already exists (no --force)
# ---------------------------------------------------------------------------


def test_adopt_refuses_existing_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init()
    _write_foreign_agent(tmp_path)

    # Pre-create a .holoctl source so adoption must refuse.
    existing = tmp_path / ".holoctl" / "agents" / "handmade.md"
    existing.write_text("---\nname: handmade\n---\n# pre-existing\n", encoding="utf-8")
    before = existing.read_text(encoding="utf-8")

    res = runner.invoke(app, ["adopt", "--type", "agent", "--name", "handmade"])
    assert res.exit_code == 0, res.output
    assert "skip" in res.output.lower()
    # Source untouched.
    assert existing.read_text(encoding="utf-8") == before
    # Not recorded in manifest.
    assert ".claude/agents/handmade.md" not in manifest.load(tmp_path)["files"]

    # With --force, it adopts (clobbers source).
    res2 = runner.invoke(app, ["adopt", "--type", "agent", "--name", "handmade", "--force"])
    assert res2.exit_code == 0, res2.output
    assert "adopted" in res2.output.lower()
    assert ".claude/agents/handmade.md" in manifest.load(tmp_path)["files"]


def test_adopt_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    _init()
    _write_foreign_agent(tmp_path)
    _write_foreign_command(tmp_path)
    _write_foreign_skill(tmp_path)

    res = runner.invoke(app, ["adopt", "--all"])
    assert res.exit_code == 0, res.output
    assert (tmp_path / ".holoctl" / "agents" / "handmade.md").exists()
    assert (tmp_path / ".holoctl" / "commands" / "mycmd.md").exists()
    assert (tmp_path / ".holoctl" / "skills" / "myskill" / "SKILL.md").exists()
    tracked = manifest.load(tmp_path)["files"]
    assert ".claude/agents/handmade.md" in tracked
    assert ".claude/commands/mycmd.md" in tracked
    assert ".claude/skills/myskill/SKILL.md" in tracked
