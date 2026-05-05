from __future__ import annotations
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from ..lib.compiler import compile_project

app = typer.Typer()


@app.command("compile")
def compile_cmd(
    target: Optional[str] = typer.Option(None, "--target", help="Target (claude, cursor, windsurf, copilot, generic)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing files"),
):
    """Compile .holoctl/ to tool-specific files."""
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `holoctl init` first.[/red]")
        raise typer.Exit(1)

    config = load_config(root)
    targets = [target] if target else config.get("targets", ["claude"])

    for t in targets:
        try:
            result = compile_project(root, config, t, dry_run=dry_run)
            if dry_run:
                console.print(f"[dim][dry-run] {t}:[/dim]")
                for f in result["files"]:
                    console.print(f"  [dim]would write[/dim] {f}")
            else:
                console.print(f"[green]✓ {t}[/green] [dim]({len(result['files'])} files)[/dim]")
                for f in result["files"]:
                    console.print(f"  [dim]→[/dim] {f}")
        except ValueError as e:
            console.print(f"[red]✗ {t}: {e}[/red]")
