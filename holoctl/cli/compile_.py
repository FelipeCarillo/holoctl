from __future__ import annotations
import os
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from ..lib.compiler import compile_project

app = typer.Typer()


@app.command("compile")
def compile_cmd(
    target: Optional[str] = typer.Option(None, "--target", help="Target (agents, claude)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing files"),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite outputs even if they look hand-edited (header missing or content drifted)."
    ),
):
    """Compile .holoctl/ to tool-specific files.

    Generated files are emitted clean (no header) and tracked in the manifest
    `.holoctl/.compiled.json`. By default, holoctl refuses to overwrite outputs
    it doesn't own (foreign files, or ones you hand-edited after compiling —
    detected via content hash, not a header). Pass `--force` to overwrite
    anyway. The exception is `CLAUDE.md`: hand-edited files there are preserved
    by renaming to `CLAUDE.local.md` instead of being skipped.
    """
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `holoctl init` first.[/red]")
        raise typer.Exit(1)

    config = load_config(root)
    targets = [target] if target else config.get("targets", ["claude"])

    # Keep the env var in sync for any legacy reader, but the ledger now takes
    # `force` explicitly via `compile_project`.
    if force:
        os.environ["HOLOCTL_COMPILE_FORCE"] = "1"
    else:
        os.environ.pop("HOLOCTL_COMPILE_FORCE", None)

    for t in targets:
        try:
            result = compile_project(root, config, t, dry_run=dry_run, force=force)
            if dry_run:
                console.print(f"[dim][dry-run] {t}:[/dim]")
                for f in result["files"]:
                    console.print(f"  [dim]would write[/dim] {f}")
            else:
                n_files = len(result["files"])
                removed = result.get("removed") or []
                migrated = result.get("migrated") or []
                summary = f"{n_files} files"
                if removed:
                    summary += f", {len(removed)} pruned"
                if migrated:
                    summary += f", {len(migrated)} migrated"
                console.print(f"[green]✓ {t}[/green] [dim]({summary})[/dim]")
                for f in result["files"]:
                    console.print(f"  [dim]→[/dim] {f}")
                for rel in removed:
                    console.print(f"  [dim]pruned[/dim] {rel}")
                skipped = result.get("skipped") or []
                for s in skipped:
                    console.print(f"  [yellow]skipped[/yellow] {s['path']} [dim]({s['reason']})[/dim]")
        except ValueError as e:
            console.print(f"[red]✗ {t}: {e}[/red]")
