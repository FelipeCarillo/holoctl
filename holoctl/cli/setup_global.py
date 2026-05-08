"""`hctl setup-global` — install the holoctl router globally for each AI tool.

Materializes idempotent, marker-fenced blocks in each tool's user-level config
so `/holoctl` (or equivalent) works in *any* directory, even before
`hctl init` has been run.

Targets:
  - claude  → ~/.claude/commands/holoctl.md   (full router, replaces marker block)
  - copilot → ~/.copilot/AGENTS.md            (appends `<!-- holoctl:start ... end -->`)
  - devin   → ~/.config/devin/skills/holoctl/SKILL.md   (Devin skill format)
  - all     → all of the above

Cursor and Windsurf have no official user-level installation surface — they're
covered by per-project compile (`hctl compile --target {cursor,windsurf}`).

Idempotent: re-running produces no diff if templates haven't changed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import typer

from ._console import console
from ..lib.compiler.template import load_bootstrap

app = typer.Typer()

_MARK_START = "<!-- holoctl:start -->"
_MARK_END = "<!-- holoctl:end -->"

_VALID_TARGETS = ("claude", "copilot", "devin", "all")


@app.command("setup-global")
def setup_global_cmd(
    target: str = typer.Option(
        "all",
        "--target",
        "-t",
        help="Which tool to install for: claude, copilot, devin, or all.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print what would change without writing."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite even if the file is non-empty without our marker."
    ),
):
    """Install holoctl's global router into each AI tool's user config."""
    if target not in _VALID_TARGETS:
        console.print(
            f"[red]Unknown target:[/red] {target}. "
            f"Valid: {', '.join(_VALID_TARGETS)}."
        )
        raise typer.Exit(2)

    targets = ("claude", "copilot", "devin") if target == "all" else (target,)

    handlers = {
        "claude": _install_claude,
        "copilot": _install_copilot,
        "devin": _install_devin,
    }

    any_change = False
    for t in targets:
        try:
            changed = handlers[t](dry_run=dry_run, force=force)
            any_change = any_change or changed
        except Exception as e:
            console.print(f"[red]✗ {t}:[/red] {e}")

    console.print("")
    if dry_run:
        console.print("[dim](dry-run — no files written)[/dim]")
    elif any_change:
        console.print(
            "[green]✓ done[/green]. Run "
            "[bold]hctl doctor --global[/bold] to verify."
        )
    else:
        console.print(
            "[dim]No changes — global routers already up-to-date.[/dim]"
        )


# ---------------------------------------------------------------------------
# Per-target installers


def _install_claude(*, dry_run: bool, force: bool) -> bool:
    """Install the Claude Code router at ~/.claude/commands/holoctl.md."""
    target_path = Path.home() / ".claude" / "commands" / "holoctl.md"
    content = load_bootstrap("holoctl-claude.md")
    if not content:
        console.print("[red]claude:[/red] holoctl-claude.md template not found in package.")
        return False
    return _write_full_file(target_path, content, label="claude", dry_run=dry_run, force=force)


def _install_copilot(*, dry_run: bool, force: bool) -> bool:
    """Append a holoctl block to ~/.copilot/AGENTS.md (preserves user content)."""
    target_path = Path.home() / ".copilot" / "AGENTS.md"
    block = _holoctl_agents_block()
    return _append_marker_block(
        target_path, block, label="copilot", dry_run=dry_run, force=force
    )


def _install_devin(*, dry_run: bool, force: bool) -> bool:
    """Install Devin skill at ~/.config/devin/skills/holoctl/SKILL.md."""
    target_path = (
        Path.home() / ".config" / "devin" / "skills" / "holoctl" / "SKILL.md"
    )
    content = load_bootstrap("holoctl-devin.md")
    if not content:
        console.print("[red]devin:[/red] holoctl-devin.md template not found in package.")
        return False
    return _write_full_file(target_path, content, label="devin", dry_run=dry_run, force=force)


# ---------------------------------------------------------------------------
# File-writing helpers


def _write_full_file(
    path: Path,
    content: str,
    *,
    label: str,
    dry_run: bool,
    force: bool,
) -> bool:
    """Write the entire file with `content`. Idempotent if content matches.

    If file exists with different content and lacks our marker, refuse unless
    --force (preserves user's hand-edited skills).
    """
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            console.print(f"[dim]{label}:[/dim] [dim]{path}[/dim] [dim](unchanged)[/dim]")
            return False
        # Detect prior holoctl-installed file: holoctl-generated files start with our pattern.
        is_ours = (
            existing.startswith("---\nname: holoctl")
            or "<!-- Generated by holoctl" in existing[:200]
        )
        if not is_ours and not force:
            console.print(
                f"[yellow]{label}:[/yellow] {path} exists with hand-edited content. "
                f"Pass [bold]--force[/bold] to overwrite."
            )
            return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    console.print(f"[green]{label}:[/green] {path} {'(would write)' if dry_run else 'written'}")
    return True


def _append_marker_block(
    path: Path,
    block: str,
    *,
    label: str,
    dry_run: bool,
    force: bool,
) -> bool:
    """Append (or update) a `<!-- holoctl:start --> ... <!-- holoctl:end -->`
    block in the file, preserving content outside the markers."""
    fenced = f"{_MARK_START}\n{block.rstrip()}\n{_MARK_END}\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(
        re.escape(_MARK_START) + r".*?" + re.escape(_MARK_END) + r"\n?",
        re.DOTALL,
    )
    if pattern.search(existing):
        new = pattern.sub(fenced, existing)
        if new == existing:
            console.print(f"[dim]{label}:[/dim] [dim]{path}[/dim] [dim](unchanged)[/dim]")
            return False
    else:
        # Append (preserve trailing newline behavior).
        suffix = "" if (existing.endswith("\n") or not existing) else "\n"
        new = existing + suffix + ("\n" if existing else "") + fenced
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
    console.print(f"[green]{label}:[/green] {path} {'(would update)' if dry_run else 'updated'}")
    return True


def _holoctl_agents_block() -> str:
    """The block to append to ~/.copilot/AGENTS.md."""
    return """## Holoctl

When the working directory (or any ancestor) contains a `.holoctl/` folder,
this project is managed by **holoctl** — a multi-assistant project operating
system. The CLI is `hctl` (in PATH).

Common lifecycle:

| Need | Command |
|---|---|
| Detect state | `hctl doctor` |
| Initialize project | `hctl init` |
| Read project state | `hctl boot` |
| Inspect everything | `hctl overview` |
| Manage tickets | `hctl board <ls\\|add\\|move\\|set>` |
| Manage personas | `hctl agent <list\\|add\\|remove>` |
| Search memory | `hctl memory search <q>` |
| End-of-session save | `hctl handoff` |

**Hard rules:**

- Never edit `.holoctl/board/index.json` or `.holoctl/memory/MEMORY.md` by
  hand. Always via `hctl <subcommand>`.
- Project-level `AGENTS.md` (root) is generated by `hctl compile --target agents`
  and contains build/test/conventions specific to that repo.

If you need the full router workflow (init with discovery, persona suggestion,
context seeding), the `holoctl` skill in `.devin/skills/` or the per-project
`.github/prompts/holoctl.prompt.md` cover it. If neither is present, suggest
the user runs `hctl setup-global --target <this-tool>` once.
"""
