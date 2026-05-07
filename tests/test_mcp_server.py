"""Tests for the MCP stdio server (server/mcp.py).

Tests use the in-process `handle()` function rather than spawning a
subprocess — covers the protocol logic + tool dispatch without paying
the Python startup cost per test.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from holoctl.server import mcp
from holoctl.lib.config import get_defaults, save_config


def _seed_workspace(tmp_path: Path) -> None:
    cfg = get_defaults()
    cfg["project"]["name"] = "MCPTest"
    cfg["project"]["prefix"] = "MC"
    save_config(tmp_path, cfg)
    (tmp_path / ".holoctl" / "board" / "tickets").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".holoctl" / "board" / "index.json").write_text(
        json.dumps({"meta": {"nextId": 1}, "tickets": []}),
        encoding="utf-8",
    )
    (tmp_path / ".holoctl" / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".holoctl" / "agents" / "boardmaster.md").write_text(
        "---\nname: boardmaster\n---\n", encoding="utf-8",
    )


def test_initialize_returns_protocol_version():
    resp = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION
    assert resp["result"]["serverInfo"]["name"] == "holoctl"
    assert "tools" in resp["result"]["capabilities"]


def test_tools_list_returns_all_tools():
    resp = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    # Read tools
    assert "holoctl.board_list" in names
    assert "holoctl.memory_list_topics" in names
    assert "holoctl.journal_recent" in names
    assert "holoctl.agent_list_available" in names
    assert "holoctl.curate_suggestions" in names
    # Write tools
    assert "holoctl.board_create" in names
    assert "holoctl.memory_add" in names
    assert "holoctl.agent_add" in names


def test_tools_list_includes_input_schema():
    resp = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    for t in resp["result"]["tools"]:
        assert "inputSchema" in t
        assert "description" in t


def test_unknown_method_returns_error():
    resp = mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "nope"})
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_unknown_tool_returns_error():
    resp = mcp.handle({
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {"name": "holoctl.does_not_exist", "arguments": {}},
    })
    assert "error" in resp


def test_tool_call_board_list_returns_json_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    resp = mcp.handle({
        "jsonrpc": "2.0", "id": 6, "method": "tools/call",
        "params": {"name": "holoctl.board_list", "arguments": {}},
    })
    content = resp["result"]["content"]
    assert content[0]["type"] == "text"
    parsed = json.loads(content[0]["text"])
    assert parsed["tickets"] == []


def test_tool_call_board_create_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    resp = mcp.handle({
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {
            "name": "holoctl.board_create",
            "arguments": {"title": "MCP-created", "agent": "boardmaster", "priority": "p1"},
        },
    })
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["title"] == "MCP-created"
    assert content["id"].startswith("MC-")


def test_tool_call_memory_add_then_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    mcp.handle({
        "jsonrpc": "2.0", "id": 8, "method": "tools/call",
        "params": {
            "name": "holoctl.memory_add",
            "arguments": {
                "name": "policies", "body": "no secrets in logs",
                "scope": "lazy", "description": "Security policies",
            },
        },
    })
    resp = mcp.handle({
        "jsonrpc": "2.0", "id": 9, "method": "tools/call",
        "params": {"name": "holoctl.memory_list_topics", "arguments": {}},
    })
    parsed = json.loads(resp["result"]["content"][0]["text"])
    names = {t["name"] for t in parsed["topics"]}
    assert "policies" in names


def test_tool_call_agent_list_shows_active_and_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    resp = mcp.handle({
        "jsonrpc": "2.0", "id": 10, "method": "tools/call",
        "params": {"name": "holoctl.agent_list_available", "arguments": {}},
    })
    parsed = json.loads(resp["result"]["content"][0]["text"])
    assert "boardmaster" in parsed["active"]
    assert "developer" in parsed["library"]


def test_tool_call_agent_add_materializes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    mcp.handle({
        "jsonrpc": "2.0", "id": 11, "method": "tools/call",
        "params": {"name": "holoctl.agent_add", "arguments": {"name": "developer"}},
    })
    assert (tmp_path / ".holoctl" / "agents" / "developer.md").exists()


def test_tool_call_missing_required_arg_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    resp = mcp.handle({
        "jsonrpc": "2.0", "id": 12, "method": "tools/call",
        "params": {"name": "holoctl.board_get", "arguments": {}},
    })
    assert "error" in resp


def test_initialized_notification_returns_none():
    resp = mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None


def test_write_tools_have_write_flag():
    write_tools = mcp.list_tools(write=True)
    write_names = {t["name"] for t in write_tools}
    assert "holoctl.board_create" in write_names
    assert "holoctl.board_move" in write_names
    assert "holoctl.memory_add" in write_names
    assert "holoctl.agent_add" in write_names
    # Read tools should NOT be in write list
    assert "holoctl.board_list" not in write_names


def test_curate_suggestions_returns_open_curate_tickets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """0.14: curate_suggestions reads open meta:curate tickets from the board."""
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    # Empty workspace: no meta:curate tickets → empty list.
    resp = mcp.handle({
        "jsonrpc": "2.0", "id": 13, "method": "tools/call",
        "params": {"name": "holoctl.curate_suggestions", "arguments": {}},
    })
    parsed = json.loads(resp["result"]["content"][0]["text"])
    assert parsed["suggestions"] == []


def test_curate_silence_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    resp = mcp.handle({
        "jsonrpc": "2.0", "id": 14, "method": "tools/call",
        "params": {
            "name": "holoctl.curate_silence",
            "arguments": {"pattern_id": "abc123"},
        },
    })
    parsed = json.loads(resp["result"]["content"][0]["text"])
    assert parsed["silenced"] is True
    assert parsed["pattern_id"] == "abc123"
