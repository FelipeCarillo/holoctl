"""Ecosystem scan — classify `.claude/` config as holoctl-managed vs foreign.

A file under `.claude/` whose POSIX rel-path is recorded in the manifest
(`.holoctl/.compiled.json`) is **managed** by holoctl. A file that is NOT in
the manifest is **foreign**: authored by the user, another plugin, or another
tool. ``hctl adopt`` brings foreign agents/skills/commands under holoctl
management.

This module is the single source of "what's foreign", used by ``hctl adopt``.
It mirrors the classification logic of ``cli/doctor.py:_check_ecosystem``
(including the bootstrap-command exemption) without importing it, so doctor
stays untouched.
"""
from __future__ import annotations

from pathlib import Path

from .compiler import manifest
from .mcp_config import read_mcp_servers

# Bootstrap commands the compiler writes directly (NOT ledger-tracked) — they
# are holoctl's own, never foreign. Kept in sync with
# ``cli/doctor.py:_HOLOCTL_BOOTSTRAP_COMMANDS``.
_BOOTSTRAP_COMMANDS: frozenset[str] = frozenset({"holoctl.md", "hctl-upgrade.md"})


def scan_unmanaged(root: Path) -> dict:
    """Return foreign (unmanaged) `.claude/` items grouped by type.

    Returns a dict::

        {"agents":      ["<name>", ...],   # .claude/agents/<name>.md not in manifest
         "commands":    ["<name>", ...],   # excluding bootstrap (holoctl.md, hctl-upgrade.md)
         "skills":      ["<name>", ...],   # .claude/skills/<name>/ whose SKILL.md rel not in manifest
         "mcp_servers": ["<name>", ...]}   # configured servers minus "holoctl" (report-only)

    ``agents``/``commands``/``skills`` are **adoptable**. ``mcp_servers`` is
    report-only (external transport, not adoptable). Names are the bare stem
    (no extension / no dir). Robust to missing `.claude/` dirs.
    """
    managed: set[str] = set(manifest.load(root).get("files", {}).keys())

    # ---- agents -------------------------------------------------------
    agents: list[str] = []
    claude_agents = root / ".claude" / "agents"
    if claude_agents.exists():
        for f in sorted(claude_agents.glob("*.md")):
            rel = f".claude/agents/{f.name}"
            if rel not in managed:
                agents.append(f.stem)

    # ---- commands -----------------------------------------------------
    commands: list[str] = []
    claude_commands = root / ".claude" / "commands"
    if claude_commands.exists():
        for f in sorted(claude_commands.glob("*.md")):
            rel = f".claude/commands/{f.name}"
            if rel in managed or f.name in _BOOTSTRAP_COMMANDS:
                continue
            commands.append(f.stem)

    # ---- skills -------------------------------------------------------
    skills: list[str] = []
    claude_skills = root / ".claude" / "skills"
    if claude_skills.exists():
        for skill_dir in sorted(d for d in claude_skills.iterdir() if d.is_dir()):
            skill_rel = f".claude/skills/{skill_dir.name}/SKILL.md"
            if skill_rel not in managed:
                skills.append(skill_dir.name)

    # ---- MCP servers (report-only) ------------------------------------
    mcp_servers = sorted(s for s in read_mcp_servers(root) if s != "holoctl")

    return {
        "agents": agents,
        "commands": commands,
        "skills": skills,
        "mcp_servers": mcp_servers,
    }
