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


def test_emit_copilot_writes_vscode_mcp_json(tmp_path: Path):
    paths = mcp_emit.emit_copilot(tmp_path)
    assert paths == [".vscode/mcp.json"]
    # Copilot in VSCode uses `servers:` key, not `mcpServers:`.
    data = json.loads((tmp_path / ".vscode/mcp.json").read_text(encoding="utf-8"))
    assert "servers" in data
    assert "holoctl" in data["servers"]


def test_emit_codex_writes_dot_codex_config_toml(tmp_path: Path):
    paths = mcp_emit.emit_codex(tmp_path)
    assert paths == [".codex/config.toml"]
    text = (tmp_path / ".codex/config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.holoctl]" in text
    assert 'args = ["serve", "--mcp"]' in text


def test_emit_codex_preserves_other_tables(tmp_path: Path):
    """User has other [mcp_servers.X] / config — merge must preserve them."""
    cfg_path = tmp_path / ".codex/config.toml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        '[mcp_servers.filesystem]\n'
        'command = "npx"\n'
        'args = ["-y", "@modelcontextprotocol/server-filesystem"]\n'
        '\n'
        '[telemetry]\n'
        'enabled = false\n',
        encoding="utf-8",
    )
    mcp_emit.emit_codex(tmp_path)
    text = cfg_path.read_text(encoding="utf-8")
    assert "[mcp_servers.filesystem]" in text
    assert "[mcp_servers.holoctl]" in text
    assert "[telemetry]" in text


def test_emit_codex_idempotent(tmp_path: Path):
    mcp_emit.emit_codex(tmp_path)
    first = (tmp_path / ".codex/config.toml").read_text(encoding="utf-8")
    mcp_emit.emit_codex(tmp_path)
    second = (tmp_path / ".codex/config.toml").read_text(encoding="utf-8")
    assert first == second
    # Single block (no duplication).
    assert second.count("[mcp_servers.holoctl]") == 1
