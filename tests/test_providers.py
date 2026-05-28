"""Tests for v0.17 provider catalog — defaults, CLI, config-show MCP tool."""
from __future__ import annotations
import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.cli.init_ import app as init_app
from holoctl.cli.provider import app as provider_app
from holoctl.lib.config import (
    _apply_provider_defaults,
    _default_providers,
    get_defaults,
    load_config,
    save_config,
)


def test_default_providers_has_six_known():
    """Linear, GitHub, Trello, Azure DevOps, Jira, Slack — all shipped."""
    defaults = _default_providers()
    assert set(defaults.keys()) == {
        "linear", "github", "trello", "azure_devops", "jira", "slack"
    }
    for name, entry in defaults.items():
        assert "url_pattern" in entry, f"{name} missing url_pattern"
        assert "mcp_fetch_tool" in entry, f"{name} missing mcp_fetch_tool"
        assert entry["enabled"] in ("auto", "always", "disabled")
        # URL pattern has the required `ref` named group.
        compiled = re.compile(entry["url_pattern"])
        assert "ref" in compiled.groupindex, f"{name} pattern missing (?P<ref>...)"


def test_default_provider_patterns_match_real_urls():
    """Each pattern matches a real-shaped URL of that provider."""
    samples = {
        "linear": "https://linear.app/eng/issue/ENG-42",
        "github": "https://github.com/holoctl/holoctl/issues/123",
        "trello": "https://trello.com/c/ABC123XYZ",
        "azure_devops": "https://dev.azure.com/contoso/Project/_workitems/edit/4567",
        "jira": "https://acme.atlassian.net/browse/PROJ-99",
        "slack": "https://acme.slack.com/archives/C0ABC123/p1709925000000000",
    }
    defaults = _default_providers()
    for name, url in samples.items():
        compiled = re.compile(defaults[name]["url_pattern"])
        m = compiled.match(url)
        assert m, f"{name} pattern failed to match {url}"
        assert m.group("ref"), f"{name} match has no ref capture"


def test_apply_provider_defaults_is_additive():
    """Existing entries (custom or already-known) are not overwritten."""
    config = {
        "providers": {
            "linear": {"enabled": "disabled", "url_pattern": "custom"},
            "acme": {"enabled": "auto", "url_pattern": r"^https://acme\.io/(?P<ref>\d+)$"},
        }
    }
    _apply_provider_defaults(config)
    # Custom entry preserved.
    assert config["providers"]["acme"]["url_pattern"] == r"^https://acme\.io/(?P<ref>\d+)$"
    # User override of a known provider preserved (not clobbered with shipped default).
    assert config["providers"]["linear"]["enabled"] == "disabled"
    assert config["providers"]["linear"]["url_pattern"] == "custom"
    # Missing providers filled in.
    assert "github" in config["providers"]
    assert "jira" in config["providers"]


def test_apply_provider_defaults_creates_empty_section_if_missing():
    config = {}
    _apply_provider_defaults(config)
    assert "providers" in config
    assert "linear" in config["providers"]


def test_get_defaults_includes_providers():
    """`get_defaults()` returns a config with providers populated."""
    config = get_defaults()
    assert "providers" in config
    assert len(config["providers"]) >= 6


def test_load_config_v016_workspace_gets_providers(tmp_path: Path):
    """A workspace created on v0.16 (no providers section) gets defaults on load."""
    # Simulate a v0.16 config (no providers).
    (tmp_path / ".holoctl").mkdir()
    legacy = {
        "version": 1,
        "holoctlVersion": "0.16.0",
        "project": {"name": "X", "prefix": "X"},
        "board": {"statuses": ["backlog", "doing", "done"], "priorities": ["p0", "p1"]},
    }
    (tmp_path / ".holoctl" / "config.json").write_text(
        json.dumps(legacy), encoding="utf-8"
    )
    config = load_config(tmp_path)
    assert "providers" in config
    assert "linear" in config["providers"]
    assert config["providers"]["linear"]["mcp_fetch_tool"] == "mcp__linear__get_issue"


def test_custom_provider_persists_across_save_load(tmp_path: Path):
    """Adding a custom provider survives save_config + load_config cycle."""
    config = get_defaults()
    config["project"]["name"] = "X"
    config["providers"]["acme"] = {
        "enabled": "auto",
        "url_pattern": r"^https://acme\.io/cards/(?P<ref>\d+)$",
        "mcp_fetch_tool": "mcp__acme__get_card",
        "label_template": "{ref}: {title}",
    }
    save_config(tmp_path, config)

    loaded = load_config(tmp_path)
    assert "acme" in loaded["providers"]
    assert loaded["providers"]["acme"]["mcp_fetch_tool"] == "mcp__acme__get_card"
    # Shipped defaults still present.
    assert "linear" in loaded["providers"]


# ---------------------------------------------------------------------------
# CLI tests — provider list / add / doctor with MCP awareness
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace initialized via `hctl init` with CWD set inside it."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(init_app, ["--name", "X", "--prefix", "X", "--skip-compile"])
    assert result.exit_code == 0, result.output
    return tmp_path


def test_provider_list_shows_connected_when_mcp_json_has_server(cli_workspace: Path):
    """`provider list` shows `✓ connected` for linear when .mcp.json has `linear`."""
    mcp_json = cli_workspace / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"linear": {"command": "npx", "args": []}}}),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(provider_app, ["list"])
    assert result.exit_code == 0, result.output
    # Linear should be connected.
    assert "connected" in result.output
    # The linear entry should show connected.
    lines = result.output.splitlines()
    linear_lines = [l for l in lines if "linear" in l.lower()]
    assert any("connected" in l for l in linear_lines), (
        f"Expected 'connected' near linear entry. Output:\n{result.output}"
    )


def test_provider_list_shows_not_configured_when_no_mcp_json(cli_workspace: Path):
    """`provider list` shows `✗ MCP not configured` when no .mcp.json exists."""
    runner = CliRunner()
    result = runner.invoke(provider_app, ["list"])
    assert result.exit_code == 0, result.output
    # At least one provider should be shown as not configured.
    assert "MCP not configured" in result.output


def test_provider_list_connected_via_settings_json(cli_workspace: Path):
    """`provider list` shows connected for github when .claude/settings.json has `github`."""
    settings = cli_workspace / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps({"mcpServers": {"github": {}}}),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(provider_app, ["list"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    github_lines = [l for l in lines if "github" in l.lower()]
    assert any("connected" in l for l in github_lines), (
        f"Expected 'connected' near github entry. Output:\n{result.output}"
    )


def test_provider_add_without_mcp_fetch_lists_servers_and_exits_nonzero(cli_workspace: Path):
    """`provider add` without --mcp-fetch lists detected servers and exits 1."""
    # Plant a .mcp.json so there are servers to list.
    mcp_json = cli_workspace / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"acme": {}}}),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        provider_app,
        [
            "add", "myboard",
            "--url-pattern", r"^https://myboard\.io/(?P<ref>\d+)$",
        ],
    )
    assert result.exit_code == 1
    # Must list detected server name.
    assert "acme" in result.output
    # Must show --mcp-fetch guidance.
    assert "--mcp-fetch" in result.output


def test_provider_add_without_mcp_fetch_no_servers_exits_nonzero(cli_workspace: Path):
    """`provider add` without --mcp-fetch exits 1 even when no servers detected."""
    runner = CliRunner()
    result = runner.invoke(
        provider_app,
        [
            "add", "myboard",
            "--url-pattern", r"^https://myboard\.io/(?P<ref>\d+)$",
        ],
    )
    assert result.exit_code == 1
    assert "--mcp-fetch" in result.output


def test_provider_add_with_mcp_fetch_server_not_configured_prints_warning(cli_workspace: Path):
    """`provider add --mcp-fetch` warns when the server is not configured, but still adds."""
    # No .mcp.json — server not configured.
    runner = CliRunner()
    result = runner.invoke(
        provider_app,
        [
            "add", "myboard",
            "--url-pattern", r"^https://myboard\.io/(?P<ref>\d+)$",
            "--mcp-fetch", "mcp__myserver__get_card",
        ],
    )
    # Should succeed (provider is saved) with a warning.
    assert result.exit_code == 0, result.output
    assert "Warning" in result.output or "warning" in result.output.lower()
    assert "myserver" in result.output
    # Provider should actually be saved.
    config = load_config(cli_workspace)
    assert "myboard" in config["providers"]
    assert config["providers"]["myboard"]["mcp_fetch_tool"] == "mcp__myserver__get_card"


def test_provider_add_with_mcp_fetch_server_configured_no_warning(cli_workspace: Path):
    """`provider add --mcp-fetch` does NOT warn when the server IS configured."""
    mcp_json = cli_workspace / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"myserver": {}}}),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        provider_app,
        [
            "add", "myboard",
            "--url-pattern", r"^https://myboard\.io/(?P<ref>\d+)$",
            "--mcp-fetch", "mcp__myserver__get_card",
        ],
    )
    assert result.exit_code == 0, result.output
    # No warning expected.
    assert "Warning" not in result.output
    assert "not configured" not in result.output.lower()


def test_provider_doctor_reports_connected_and_missing(cli_workspace: Path):
    """`provider doctor` reports per-provider connected/missing status."""
    # Only linear is configured.
    mcp_json = cli_workspace / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"linear": {}}}),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(provider_app, ["doctor"])
    assert result.exit_code == 0, result.output
    # Linear should be connected.
    assert "connected" in result.output
    # At least some providers should be missing MCP.
    assert "MCP not configured" in result.output
    # Summary should be present.
    assert "Summary" in result.output or "summary" in result.output.lower()


def test_provider_doctor_no_providers_exits_one(cli_workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """`provider doctor` exits 1 when no providers are configured."""
    # Wipe providers from config.
    config = load_config(cli_workspace)
    config["providers"] = {}
    save_config(cli_workspace, config)
    # Also patch _apply_provider_defaults so load_config doesn't re-populate defaults.
    import holoctl.lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_apply_provider_defaults", lambda c: c)
    runner = CliRunner()
    result = runner.invoke(provider_app, ["doctor"])
    assert result.exit_code == 1


def test_provider_doctor_all_connected_summary(cli_workspace: Path):
    """`provider doctor` summary counts match when all default servers are configured."""
    defaults = _default_providers()
    # Determine which server names are used by the 6 defaults.
    from holoctl.lib.mcp_config import server_for_tool
    server_names = {
        server_for_tool(entry["mcp_fetch_tool"])
        for entry in defaults.values()
        if entry.get("mcp_fetch_tool")
    }
    mcp_json = cli_workspace / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {s: {} for s in server_names if s}}),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(provider_app, ["doctor"])
    assert result.exit_code == 0, result.output
    # Every provider with an mcp_fetch_tool should now be connected — no "MCP not configured".
    assert "MCP not configured" not in result.output
