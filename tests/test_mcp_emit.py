"""Tests for compiler/mcp_emit — per-target MCP config emission."""
from __future__ import annotations

import json
from pathlib import Path

from holoctl.lib.compiler import mcp_emit


def test_emit_claude_writes_settings(tmp_path: Path):
    paths = mcp_emit.emit_claude(tmp_path)
    assert paths == [".claude/settings.json"]
    settings = json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))
    assert "mcpServers" in settings
    assert "holoctl" in settings["mcpServers"]
    cmd = settings["mcpServers"]["holoctl"]["command"]
    args = settings["mcpServers"]["holoctl"]["args"]
    assert "{{HCTL_BIN}}" not in cmd
    assert args == ["serve", "--mcp"]


def test_emit_claude_preserves_user_mcp_servers(tmp_path: Path):
    """User's existing MCP servers must stay untouched on merge."""
    settings_path = tmp_path / ".claude/settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({
        "mcpServers": {
            "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]}
        },
        "model": "opus",
    }), encoding="utf-8")

    mcp_emit.emit_claude(tmp_path)
    merged = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "filesystem" in merged["mcpServers"]
    assert "holoctl" in merged["mcpServers"]
    assert merged["model"] == "opus"


def test_emit_cursor_writes_dot_cursor_mcp_json(tmp_path: Path):
    paths = mcp_emit.emit_cursor(tmp_path)
    assert paths == [".cursor/mcp.json"]
    data = json.loads((tmp_path / ".cursor/mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["holoctl"]["args"] == ["serve", "--mcp"]


def test_emit_copilot_writes_vscode_mcp_json(tmp_path: Path):
    paths = mcp_emit.emit_copilot(tmp_path)
    assert paths == [".vscode/mcp.json"]
    # Copilot in VSCode uses `servers:` key, not `mcpServers:`.
    data = json.loads((tmp_path / ".vscode/mcp.json").read_text(encoding="utf-8"))
    assert "servers" in data
    assert "holoctl" in data["servers"]


def test_emit_windsurf_writes_dot_windsurf_mcp_json(tmp_path: Path):
    paths = mcp_emit.emit_windsurf(tmp_path)
    assert paths == [".windsurf/mcp.json"]
    data = json.loads((tmp_path / ".windsurf/mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["holoctl"]["args"] == ["serve", "--mcp"]


def test_emit_devin_writes_dot_devin_mcp_json(tmp_path: Path):
    paths = mcp_emit.emit_devin(tmp_path)
    assert paths == [".devin/mcp.json"]
    data = json.loads((tmp_path / ".devin/mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["holoctl"]["args"] == ["serve", "--mcp"]


def test_idempotent_does_not_duplicate(tmp_path: Path):
    mcp_emit.emit_cursor(tmp_path)
    mcp_emit.emit_cursor(tmp_path)
    data = json.loads((tmp_path / ".cursor/mcp.json").read_text(encoding="utf-8"))
    # Should still be exactly one holoctl entry (not duplicated).
    assert list(data["mcpServers"].keys()).count("holoctl") == 1
