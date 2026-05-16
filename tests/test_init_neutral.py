"""Tests for the neutral init flow — only boardmaster materializes by default."""
from __future__ import annotations

from pathlib import Path

from holoctl.lib.config import get_defaults
from holoctl.lib.templates import get_templates


def test_get_templates_does_not_include_opinionated_personas():
    """The 4 seed personas (developer/reviewer/architect/researcher) live in
    the latent library — they MUST NOT be in get_templates() output, otherwise
    `hctl init` would auto-activate them and break the agnostic principle."""
    config = get_defaults()
    config["project"]["name"] = "Foo"
    config["project"]["prefix"] = "FOO"

    out = get_templates(config)
    paths = set(out.keys())

    forbidden = {
        ".holoctl/agents/developer.md",
        ".holoctl/agents/reviewer.md",
        ".holoctl/agents/architect.md",
        ".holoctl/agents/researcher.md",
    }
    assert forbidden.isdisjoint(paths), (
        f"init would auto-materialize opinionated personas: "
        f"{sorted(forbidden & paths)}"
    )


def test_get_templates_still_includes_boardmaster():
    """boardmaster is the single always-essential persona. Without it, the
    board CLI vocabulary has no agent persona to dispatch into."""
    config = get_defaults()
    out = get_templates(config)
    assert ".holoctl/agents/boardmaster.md" in out
    body = out[".holoctl/agents/boardmaster.md"]
    assert "boardmaster" in body
    # Placeholders fully resolved by materialize_agent.
    assert "{{project.name}}" not in body
    assert "{{board.statusesJoined}}" not in body


def test_get_templates_returns_essential_scaffolding():
    """Sanity — the essentials (commands, context, workflow, instructions)
    are still emitted."""
    config = get_defaults()
    out = get_templates(config)
    expected = {
        ".holoctl/board/WORKFLOW.md",
        ".holoctl/board/tickets/_template.md",
        ".holoctl/agents/boardmaster.md",
        ".holoctl/commands/status.md",
        ".holoctl/commands/ticket.md",
        ".holoctl/commands/spec.md",
        ".holoctl/commands/board.md",
        ".holoctl/commands/sprint.md",
        ".holoctl/commands/decision.md",
        ".holoctl/commands/close.md",
        ".holoctl/context/objective.md",
        ".holoctl/context/architecture.md",
        ".holoctl/context/conventions.md",
        ".holoctl/instructions.md",
    }
    assert expected.issubset(set(out.keys()))


def test_instructions_mentions_agent_library_workflow():
    """instructions.md should point users toward `hctl agent list/add` so they
    discover the latent library, since init no longer materializes personas."""
    config = get_defaults()
    out = get_templates(config)
    instructions = out[".holoctl/instructions.md"]
    assert "agent list" in instructions
    assert "agent add" in instructions
    # Library is mentioned so the user knows it exists.
    assert "library" in instructions.lower()
