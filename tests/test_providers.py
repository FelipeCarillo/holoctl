"""Tests for v0.17 provider catalog — defaults, CLI, config-show MCP tool."""
from __future__ import annotations
import json
import re
from pathlib import Path


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
