from __future__ import annotations

import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from ..lib.templates import get_templates

app = typer.Typer()

_SYNC_TARGETS = {
    ".projctl/commands/status.md",
    ".projctl/commands/ticket.md",
    ".projctl/commands/board.md",
    ".projctl/commands/sprint.md",
    ".projctl/commands/decision.md",
    ".projctl/commands/close.md",
    ".projctl/board/WORKFLOW.md",
}


@app.command("sync")
def sync_cmd(
    include_agents: bool = typer.Option(False, "--agents", help="Also regenerate agent templates"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing files"),
):
    """Update template-managed files in .projctl/ after a projctl upgrade."""
    root = find_project_root()
    if not root:
        console.print("[red]No .projctl/ found. Run `projctl init` first.[/red]")
        raise typer.Exit(1)

    config = load_config(root)
    templates = get_templates(config)

    targets = set(_SYNC_TARGETS)
    if include_agents:
        for key in templates:
            if key.startswith(".projctl/agents/"):
                targets.add(key)

    console.print(f"\n  [bold]projctl sync[/bold]\n")

    updated, added = [], []

    for rel_path, content in templates.items():
        if rel_path not in targets:
            continue
        full_path = root / rel_path
        exists = full_path.exists()
        changed = (not exists) or full_path.read_text(encoding="utf-8") != content

        if not changed:
            continue

        if not dry_run:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

        if exists:
            updated.append(rel_path)
        else:
            added.append(rel_path)

    if not added and not updated:
        console.print("[dim]  Already up to date. Nothing to sync.[/dim]\n")
        return

    prefix = "[dim][dry-run][/dim] " if dry_run else ""
    for f in added:
        console.print(f"  {prefix}[green]+[/green] {f}")
    for f in updated:
        console.print(f"  {prefix}[cyan]~[/cyan] {f}")

    console.print("")
    total = len(added) + len(updated)
    if not dry_run:
        console.print(f"  [green]✓ Synced {total} file(s).[/green]\n")
        console.print("  Run [dim]projctl compile[/dim] to push changes to your AI tool.\n")
    else:
        console.print(f"  [dim]{total} file(s) would be updated.[/dim]\n")
