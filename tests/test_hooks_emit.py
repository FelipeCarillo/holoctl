"""Tests for compiler/hooks_emit — non-destructive merge into settings.json."""
from __future__ import annotations

import json
from pathlib import Path

from holoctl.lib.compiler import hooks_emit


def test_emit_claude_creates_settings_when_absent(tmp_path: Path):
    paths = hooks_emit.emit_claude(tmp_path)
    assert paths == [".claude/settings.json"]
    settings = json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))
    assert "hooks" in settings
    events = settings["hooks"]
    assert "SessionStart" in events
    assert "PostToolUse" in events
    assert "Stop" in events


def test_emit_claude_resolves_hctl_bin(tmp_path: Path):
    hooks_emit.emit_claude(tmp_path)
    settings = json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))
    cmd = settings["hooks"]["SessionStart"][0]["command"]
    # Placeholder must be substituted out (no template residue).
    assert "{{HCTL_BIN}}" not in cmd
    assert "journal record" in cmd


def test_emit_claude_does_not_overwrite_existing_user_hooks(tmp_path: Path):
    """User has their own hooks; merge must preserve them."""
    settings_path = tmp_path / ".claude/settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    user_settings = {
        "hooks": {
            "SessionStart": [
                {"type": "command", "command": "echo hello-from-user"}
            ],
            "OtherEvent": [
                {"type": "command", "command": "user-only"}
            ],
        },
        "permissions": {"allow": ["mcp__user_thing"]},
        "model": "opus",
    }
    settings_path.write_text(json.dumps(user_settings), encoding="utf-8")

    hooks_emit.emit_claude(tmp_path)
    merged = json.loads(settings_path.read_text(encoding="utf-8"))

    assert merged["model"] == "opus"
    assert {"type": "command", "command": "echo hello-from-user"} in merged["hooks"]["SessionStart"]
    assert any("journal record" in h["command"] for h in merged["hooks"]["SessionStart"])
    assert merged["hooks"]["OtherEvent"] == [{"type": "command", "command": "user-only"}]
    assert "mcp__user_thing" in merged["permissions"]["allow"]
    assert "mcp__holoctl__board_create" in merged["permissions"]["ask"]


def test_emit_claude_idempotent_no_duplicate_hooks(tmp_path: Path):
    """Re-running emit_claude must not duplicate any hook commands."""
    hooks_emit.emit_claude(tmp_path)
    first = json.loads(
        (tmp_path / ".claude/settings.json").read_text(encoding="utf-8")
    )
    hooks_emit.emit_claude(tmp_path)
    second = json.loads(
        (tmp_path / ".claude/settings.json").read_text(encoding="utf-8")
    )
    # Second run must produce the same shape (no duplicates).
    assert first == second
    # Each command appears exactly once per event.
    for event, hooks in second["hooks"].items():
        cmds = [h.get("command") for h in hooks if "command" in h]
        assert len(cmds) == len(set(cmds)), (
            f"duplicate command in {event}: {cmds}"
        )


def test_emit_claude_includes_write_tool_permissions(tmp_path: Path):
    """Write tools (item 2A) must land in permissions.ask."""
    hooks_emit.emit_claude(tmp_path)
    settings = json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))
    ask = settings["permissions"]["ask"]
    for write_tool in (
        "mcp__holoctl__board_create",
        "mcp__holoctl__board_move",
        "mcp__holoctl__memory_add",
        "mcp__holoctl__agent_add",
    ):
        assert write_tool in ask


def test_emit_cursor_creates_hooks_json(tmp_path: Path):
    paths = hooks_emit.emit_cursor(tmp_path)
    assert paths == [".cursor/hooks.json"]
    data = json.loads((tmp_path / ".cursor/hooks.json").read_text(encoding="utf-8"))
    assert "sessionStart" in data["hooks"]
    assert "afterFileEdit" in data["hooks"]


def test_emit_cursor_idempotent(tmp_path: Path):
    hooks_emit.emit_cursor(tmp_path)
    hooks_emit.emit_cursor(tmp_path)
    data = json.loads((tmp_path / ".cursor/hooks.json").read_text(encoding="utf-8"))
    assert len(data["hooks"]["sessionStart"]) == 1
