"""Tests for holoctl.lib.agent_library — latent persona catalog."""
from __future__ import annotations

import pytest

from holoctl.lib.agent_library import (
    list_library_agents,
    load_library_agent,
    materialize_agent,
)
from holoctl.lib.config import get_defaults
from holoctl.lib.markdown import parse_frontmatter


def test_library_lists_seed_personas():
    names = set(list_library_agents())
    expected = {"boardmaster", "developer", "reviewer", "architect", "researcher"}
    assert expected.issubset(names), (
        f"library missing seed personas. Got: {sorted(names)}"
    )


def test_load_library_agent_returns_raw_body_with_placeholders():
    body = load_library_agent("developer")
    assert body is not None
    # Body uses {{project.name}} placeholders that are resolved at materialize time.
    assert "{{project.name}}" in body
    # Frontmatter is well-formed.
    data, _ = parse_frontmatter(body)
    assert data.get("name") == "developer"
    assert "description" in data


def test_load_library_agent_unknown_returns_none():
    assert load_library_agent("does-not-exist-XYZ") is None


def test_materialize_agent_resolves_project_placeholders():
    config = get_defaults()
    config["project"]["name"] = "Acme"
    config["project"]["prefix"] = "ACM"

    body = materialize_agent("developer", config)
    assert body is not None
    assert "{{project.name}}" not in body
    assert "Acme" in body

    # boardmaster references {{project.prefix}} in its report format examples
    bm = materialize_agent("boardmaster", config)
    assert bm is not None
    assert "{{project.prefix}}" not in bm
    assert "ACM-001" in bm


def test_materialize_agent_resolves_board_joined_fields():
    """boardmaster body references {{board.statusesJoined}}."""
    config = get_defaults()
    body = materialize_agent("boardmaster", config)
    assert body is not None
    assert "{{board.statusesJoined}}" not in body
    # Default statuses joined with " | "
    assert "backlog | doing | review | done | cancelled" in body


def test_materialize_agent_resolves_cli_bin():
    """boardmaster references {{commands.boardCliBin}} for `agent list` calls."""
    config = get_defaults()
    body = materialize_agent("boardmaster", config)
    assert body is not None
    assert "{{commands.boardCliBin}}" not in body
    assert "hctl agent list" in body


def test_materialize_agent_unknown_returns_none():
    config = get_defaults()
    assert materialize_agent("nope", config) is None


def test_seed_personas_have_when_to_suggest_frontmatter():
    """Every seed persona declares heuristic for the curator (0.14 dependency).

    Note: holoctl's ``parse_frontmatter`` is deliberately a no-deps line parser
    that doesn't understand nested YAML lists. We assert textual presence here
    — full structured parsing arrives with the curator in 0.14.
    """
    for name in ("developer", "reviewer", "architect", "researcher"):
        body = load_library_agent(name)
        assert body is not None
        # Extract just the frontmatter block.
        assert body.startswith("---\n")
        end = body.find("\n---\n", 4)
        assert end > 0, f"{name}: malformed frontmatter"
        front = body[4:end]
        assert "when_to_suggest:" in front, (
            f"{name} missing when_to_suggest frontmatter — required for curator"
        )


def test_boardmaster_marked_always_essential():
    """boardmaster declares always_essential — never auto-removable by curator."""
    body = load_library_agent("boardmaster")
    assert body is not None
    end = body.find("\n---\n", 4)
    front = body[4:end]
    assert "when_to_suggest:" in front
    assert "kind: always_essential" in front
