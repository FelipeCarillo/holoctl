from __future__ import annotations

import typer
from ._console import console

from .. import __version__
from ..lib.board import Board
from ..lib.changelog import load_changelog, slice_between
from ..lib.compiler import compile_project
from ..lib.config import find_project_root, load_config, save_config
from ..lib.templates import SYNC_TARGETS, get_templates

app = typer.Typer()


@app.command("upgrade")
def upgrade_cmd(
    check: bool = typer.Option(False, "--check", help="Show old/new versions and CHANGELOG diff without modifying anything"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run sync/compile in preview mode and skip rebuild-index/save"),
    no_changelog: bool = typer.Option(False, "--no-changelog", help="Skip the CHANGELOG slice in the output"),
):
    """Sync this workspace to the installed holoctl version.

    Pipeline:
      1. sync (templates + agents)
      2. compile for every configured target
      3. board rebuild-index (migrates ticket schemas)
      4. doctor
      5. bump holoctlVersion in config.json
    """
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `holoctl init` first.[/red]")
        raise typer.Exit(1)

    config = load_config(root)
    workspace_version = config.get("holoctlVersion", "0.0.0")
    installed_version = __version__

    console.print("\n  [bold]hctl upgrade[/bold]\n")
    console.print(f"  workspace_version:  [cyan]{workspace_version}[/cyan]")
    console.print(f"  installed_version:  [cyan]{installed_version}[/cyan]\n")

    if not no_changelog:
        cl = load_changelog()
        if cl:
            slice_text = slice_between(cl, workspace_version, installed_version)
            if slice_text.strip():
                console.print("[bold]Changes since your last sync:[/bold]\n")
                console.print(slice_text)
                console.print("")

    if workspace_version == installed_version:
        console.print("[green]  ✓ Already in sync. Nothing to do.[/green]\n")
        return

    if _semver_lt(installed_version, workspace_version):
        console.print(
            f"[yellow]  ! Installed version ({installed_version}) is older than the workspace "
            f"({workspace_version}). Refusing to auto-downgrade.[/yellow]\n"
            f"  If you really want to roll back, edit "
            f".holoctl/config.json:holoctlVersion manually.\n"
        )
        raise typer.Exit(2)

    if check:
        console.print(
            "  [dim]--check: skipping sync/compile/rebuild-index. "
            "Run `hctl upgrade` (no flags) to apply.[/dim]\n"
        )
        return

    # 1. Sync templates (always include agents during upgrade — agent personas
    # often change between releases and the user's existing agent files are
    # template-managed once they exist).
    _sync(root, config, dry_run=dry_run)

    # 2. Compile every configured target.
    targets = config.get("targets", ["claude"])
    for t in targets:
        try:
            result = compile_project(root, config, t, dry_run=dry_run)
            count = len(result.get("files", []))
            prefix = "[dim][dry-run][/dim] " if dry_run else ""
            console.print(f"  {prefix}[green]✓ compiled[/green] [bold]{t}[/bold] [dim]({count} files)[/dim]")
        except ValueError as e:
            console.print(f"  [red]✗ compile {t}: {e}[/red]")

    # 3. Rebuild board index (migrates old ticket schemas — scope→projects,
    # date-only → ISO 8601, etc — handled inside Board.rebuild_index).
    if not dry_run:
        try:
            board = Board(root, config)
            result = board.rebuild_index()
            console.print(
                f"  [green]✓ rebuilt index[/green] "
                f"[dim]({result['ticketCount']} tickets, nextId: {result['nextId']})[/dim]"
            )
        except Exception as e:
            console.print(f"  [red]✗ rebuild-index: {e}[/red]")
            console.print(
                "    [dim]Workspace partially upgraded. Fix the ticket and re-run "
                "`hctl board rebuild-index`.[/dim]"
            )
            raise typer.Exit(3)
    else:
        console.print("  [dim][dry-run] would rebuild board index[/dim]")

    # 4. Bump holoctlVersion (skip on dry-run to avoid lying about a state change).
    if not dry_run:
        config["holoctlVersion"] = installed_version
        save_config(root, config)
        console.print(
            f"  [green]✓ bumped[/green] [dim]holoctlVersion → {installed_version}[/dim]"
        )

    console.print("")
    if dry_run:
        console.print("  [dim]Dry-run complete. No files written, no version bumped.[/dim]\n")
    else:
        console.print("  [green]✓ Upgrade complete.[/green] Run `hctl doctor` to confirm health.\n")


def _sync(root, config, dry_run: bool) -> None:
    """Inline sync (templates + agents). Mirrors `cli.sync_.sync_cmd` but
    always includes agents and reports a tighter summary."""
    templates = get_templates(config)
    targets = set(SYNC_TARGETS)
    for key in templates:
        if key.startswith(".holoctl/agents/"):
            targets.add(key)

    updated = 0
    added = 0
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
            updated += 1
        else:
            added += 1

    prefix = "[dim][dry-run][/dim] " if dry_run else ""
    if added or updated:
        console.print(
            f"  {prefix}[green]✓ synced[/green] [dim]({added} added, {updated} updated)[/dim]"
        )
    else:
        console.print(f"  {prefix}[dim]✓ templates already in sync[/dim]")


def _semver_lt(a: str, b: str) -> bool:
    return _semver_tuple(a) < _semver_tuple(b)


def _semver_tuple(v: str) -> tuple[int, int, int]:
    import re
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", v.strip())
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
