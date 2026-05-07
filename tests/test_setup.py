"""Tests for `hctl setup` — global /holoctl install."""
from __future__ import annotations

from pathlib import Path

import pytest

from holoctl.cli import setup as setup_mod


def test_resolve_hctl_bin_respects_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOLOCTL_BIN", "/custom/bin/hctl")
    assert setup_mod._resolve_hctl_bin() == "/custom/bin/hctl"


def test_resolve_hctl_bin_falls_back_to_which(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HOLOCTL_BIN", raising=False)
    monkeypatch.setattr(
        setup_mod.shutil, "which",
        lambda name: "/usr/local/bin/hctl" if name == "hctl" else None,
    )
    assert setup_mod._resolve_hctl_bin() == "/usr/local/bin/hctl"


def test_resolve_hctl_bin_last_resort_is_python_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HOLOCTL_BIN", raising=False)
    monkeypatch.setattr(setup_mod.shutil, "which", lambda name: None)
    out = setup_mod._resolve_hctl_bin()
    assert out.endswith("-m holoctl")


def test_skill_body_includes_three_flow_routes():
    body = setup_mod._skill_body("hctl", "claude")
    assert "Flow A" in body
    assert "Flow B" in body
    assert "Flow C" in body
    assert "hctl doctor" in body
    assert "hctl init" in body
    assert "hctl upgrade" in body
    assert "hctl boot" in body


def test_skill_body_resolves_bin_into_commands():
    body = setup_mod._skill_body("/custom/path/hctl", "claude")
    assert "/custom/path/hctl doctor" in body
    assert "/custom/path/hctl init" in body


def test_frontmatter_per_target_includes_required_fields():
    claude_fm = setup_mod._frontmatter("claude")
    assert "name: holoctl" in claude_fm
    assert "allowed-tools" in claude_fm

    cursor_fm = setup_mod._frontmatter("cursor")
    assert "alwaysApply: false" in cursor_fm

    windsurf_fm = setup_mod._frontmatter("windsurf")
    assert "name: holoctl" in windsurf_fm

    devin_fm = setup_mod._frontmatter("devin")
    assert "triggers:" in devin_fm
    assert "user" in devin_fm
    assert "model" in devin_fm


def test_targets_lists_five_assistants():
    targets = setup_mod._targets()
    keys = {t["key"] for t in targets}
    assert keys == {"claude", "cursor", "windsurf", "copilot", "devin"}
