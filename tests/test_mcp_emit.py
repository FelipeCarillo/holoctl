"""Tests for compiler/mcp_emit — Claude MCP config emission."""
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
