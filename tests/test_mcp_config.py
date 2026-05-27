"""Unit tests for holoctl.lib.mcp_config."""
from __future__ import annotations

import json
from pathlib import Path

from holoctl.lib.mcp_config import is_tool_connected, read_mcp_servers, server_for_tool


# ---------------------------------------------------------------------------
# read_mcp_servers
# ---------------------------------------------------------------------------


def test_read_mcp_servers_from_mcp_json_only(tmp_path: Path):
    """Reads server names from .mcp.json when only that file exists."""
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"linear": {}, "github": {}}}),
        encoding="utf-8",
    )
    servers = read_mcp_servers(tmp_path)
    assert servers == {"linear", "github"}


def test_read_mcp_servers_from_settings_only(tmp_path: Path):
    """Reads server names from .claude/settings.json when only that file exists."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps({"mcpServers": {"holoctl": {}, "slack": {}}}),
        encoding="utf-8",
    )
    servers = read_mcp_servers(tmp_path)
    assert servers == {"holoctl", "slack"}


def test_read_mcp_servers_union_of_both_sources(tmp_path: Path):
    """Merges servers from both .mcp.json and .claude/settings.json."""
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"linear": {}, "github": {}}}),
        encoding="utf-8",
    )
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps({"mcpServers": {"holoctl": {}, "github": {}}}),
        encoding="utf-8",
    )
    servers = read_mcp_servers(tmp_path)
    assert servers == {"linear", "github", "holoctl"}


def test_read_mcp_servers_missing_files_returns_empty(tmp_path: Path):
    """Missing files contribute nothing — returns empty set."""
    servers = read_mcp_servers(tmp_path)
    assert servers == set()


def test_read_mcp_servers_corrupt_mcp_json_ignored(tmp_path: Path):
    """Corrupt .mcp.json doesn't raise — treated as empty."""
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text("not valid json {{{{", encoding="utf-8")
    servers = read_mcp_servers(tmp_path)
    assert servers == set()


def test_read_mcp_servers_corrupt_settings_ignored(tmp_path: Path):
    """Corrupt settings.json doesn't raise — treated as empty."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("[bad json", encoding="utf-8")
    servers = read_mcp_servers(tmp_path)
    assert servers == set()


def test_read_mcp_servers_empty_mcp_json_ignored(tmp_path: Path):
    """.mcp.json that is an empty file doesn't raise — returns empty set."""
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text("", encoding="utf-8")
    servers = read_mcp_servers(tmp_path)
    assert servers == set()


def test_read_mcp_servers_no_mcpservers_key_ignored(tmp_path: Path):
    """.mcp.json without mcpServers key contributes nothing."""
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(json.dumps({"otherKey": {}}), encoding="utf-8")
    servers = read_mcp_servers(tmp_path)
    assert servers == set()


def test_read_mcp_servers_mcpservers_not_a_dict_ignored(tmp_path: Path):
    """If mcpServers is not a dict (e.g. a list), it's ignored."""
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(json.dumps({"mcpServers": ["not", "a", "dict"]}), encoding="utf-8")
    servers = read_mcp_servers(tmp_path)
    assert servers == set()


# ---------------------------------------------------------------------------
# server_for_tool
# ---------------------------------------------------------------------------


def test_server_for_tool_valid_simple():
    assert server_for_tool("mcp__linear__get_issue") == "linear"


def test_server_for_tool_valid_underscore_in_server():
    """Server names can contain underscores (e.g. azure_devops)."""
    assert server_for_tool("mcp__azure_devops__get_work_item") == "azure_devops"


def test_server_for_tool_valid_multi_underscore_tool():
    assert server_for_tool("mcp__github__search_issues") == "github"


def test_server_for_tool_valid_short():
    assert server_for_tool("mcp__s__t") == "s"


def test_server_for_tool_no_mcp_prefix_returns_none():
    assert server_for_tool("not_an_mcp_tool") is None


def test_server_for_tool_empty_string_returns_none():
    assert server_for_tool("") is None


def test_server_for_tool_only_prefix_returns_none():
    assert server_for_tool("mcp__") is None


def test_server_for_tool_only_prefix_and_one_part_returns_none():
    """mcp__server (no second __) has no tool — returns None."""
    assert server_for_tool("mcp__linear") is None


def test_server_for_tool_double_underscore_only_after_mcp_returns_none():
    """mcp____ — server segment is empty (between first and second __)."""
    assert server_for_tool("mcp____tool") is None


def test_server_for_tool_plain_snake_case_returns_none():
    assert server_for_tool("linear__get_issue") is None


# ---------------------------------------------------------------------------
# is_tool_connected
# ---------------------------------------------------------------------------


def test_is_tool_connected_when_server_present():
    servers = {"linear", "github"}
    assert is_tool_connected("mcp__linear__get_issue", servers) is True


def test_is_tool_connected_when_server_absent():
    servers = {"github"}
    assert is_tool_connected("mcp__linear__get_issue", servers) is False


def test_is_tool_connected_empty_servers():
    assert is_tool_connected("mcp__linear__get_issue", set()) is False


def test_is_tool_connected_malformed_tool_returns_false():
    assert is_tool_connected("not_an_mcp_tool", {"linear"}) is False


def test_is_tool_connected_empty_tool_name_returns_false():
    assert is_tool_connected("", {"linear"}) is False


def test_is_tool_connected_azure_devops():
    """Server names with underscores (azure_devops) work correctly."""
    servers = {"azure_devops"}
    assert is_tool_connected("mcp__azure_devops__get_work_item", servers) is True
    assert is_tool_connected("mcp__azure_devops__get_work_item", set()) is False
