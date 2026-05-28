"""`hctl coverage` — show what's in `.holoctl/` and where each piece lands per target.

Useful for:
  - Understanding what each compile target consumes from `.holoctl/`.
  - Auditing cross-tool gaps in coverage.

Output is a matrix: rows = source items in `.holoctl/`, columns = compile
targets (agents, claude). holoctl maintains a deep compiler only for Claude;
`agents` emits the minimal AGENTS.md discovery shim that points non-Claude
assistants at the `holoctl-foreign-bootstrap` skill.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ._console import console
from ..lib.config import find_project_root, load_config
from ..lib.compiler import _COMPILERS

app = typer.Typer()


# (source rel path under .holoctl/, label) → which targets consume it.
# This is a static catalog of expected coverage, not introspected from the
# compilers — kept in sync manually but small enough to be obvious.
_COVERAGE: dict[str, dict[str, str | None]] = {
    # Source path under .holoctl/  : { target: rel_path under repo root | None }
    # `agents` no longer embeds source content — it emits a fixed discovery
    # shim (see the synthetic bootstrap row). Non-Claude assistants read these
    # sources directly via the holoctl-foreign-bootstrap skill.
    "instructions.md": {
        "claude":  "CLAUDE.md",
        "agents":  None,
    },
    "agents/*.md": {
        "claude":  ".claude/agents/<name>.md",
        "agents":  None,
    },
    "commands/*.md": {
        "claude":  ".claude/commands/<name>.md",
        "agents":  None,
    },
    "context/*.md": {
        "claude":  None,  # consumed via instructions.md / memory references
        "agents":  None,
    },
    "memory/topics/*.md": {
        "claude":  ".claude/skills/holoctl-memory-<topic>/SKILL.md",
        "agents":  None,
    },
    "hooks/*.json": {
        "claude":  ".claude/settings.json (merged)",
        "agents":  None,
    },
    "rules/*.md": {
        "claude":  ".claude/rules/<name>.md",
        "agents":  None,
    },
    "skills/*/SKILL.md": {
        "claude":  ".claude/skills/<name>/ (with references/scripts/)",
        "agents":  None,
    },
    "output_styles/*.md": {
        "claude":  ".claude/output_styles/<name>.md",
        "agents":  None,
    },
    "(MCP servers, defined in CLI/server)": {
        "claude":  ".claude/settings.json:mcpServers",
        "agents":  None,
    },
    "(foreign-assistant bootstrap)": {
        "claude":  None,
        "agents":  "AGENTS.md",
    },
}


@app.command("coverage")
def coverage_cmd(
    target_filter: Optional[str] = typer.Option(
        None, "--target", "-t",
        help="Only show coverage for one target (agents, claude).",
    ),
    only_present: bool = typer.Option(
        False, "--only-present",
        help="Only list source items that actually exist in .holoctl/.",
    ),
):
    """Show what's in .holoctl/ and where each piece materializes per target."""
    root = find_project_root()
    if not root:
        print("holoctl: not initialized")
        console.print("[red]No .holoctl/ found.[/red]")
        raise typer.Exit(1)

    config = load_config(root)
    active_targets = config.get("targets", []) or list(_COMPILERS.keys())
    columns = list(_COMPILERS.keys()) if not target_filter else [target_filter]

    console.print("\n  [bold]hctl coverage[/bold] [dim](source → per-target outputs)[/dim]")
    console.print(f"  [dim]workspace: {root}[/dim]")
    console.print(f"  [dim]active targets: {', '.join(active_targets)}[/dim]\n")

    # Header.
    header = "  Source".ljust(36) + " | " + " | ".join(c.ljust(12) for c in columns)
    console.print(f"  [bold]{header}[/bold]")
    console.print("  " + "─" * len(header))

    for src_label, mapping in _COVERAGE.items():
        if only_present:
            present = _source_exists(root, src_label)
            if not present:
                continue
        row = f"  {src_label}".ljust(36) + " | "
        cells = []
        for col in columns:
            dest = mapping.get(col)
            if dest is None:
                cells.append("[dim]—[/dim]".ljust(12))
            else:
                short = dest.replace(".claude/", ".cl/").replace(".holoctl/", ".ho/")
                cells.append(f"[green]✓[/green] {short[:10]}")
        row += " | ".join(cells)
        console.print(row)

    console.print("")
    console.print(
        "  [dim]Legend: ✓ = compiler emits this. — = not consumed by this target. "
        "Run `hctl compile --target X` to materialize.[/dim]\n"
    )


def _source_exists(root: Path, src_label: str) -> bool:
    """Best-effort check whether the source pattern has any matches."""
    holoctl_root = root / ".holoctl"
    if "*" not in src_label:
        return (holoctl_root / src_label).exists()
    # Glob-style.
    parts = src_label.split("/")
    base = holoctl_root
    for p in parts[:-1]:
        if "*" in p:
            return any(base.glob(src_label))
        base = base / p
    if not base.exists():
        return False
    pattern = parts[-1]
    return any(base.glob(pattern))
