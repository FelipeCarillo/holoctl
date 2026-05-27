from __future__ import annotations
from datetime import datetime, timezone

import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from ..lib.board import Board
from ..lib.discover import discover_repos
from ..lib.markdown import parse_frontmatter

app = typer.Typer()


@app.command("overview")
def overview_cmd(
    check_dirty: bool = typer.Option(
        None,
        "--check-dirty/--no-check-dirty",
        help="Run `git status` per repo to show dirty flag (overrides config.git.checkDirty)",
    ),
):
    """One-screen project snapshot: board, repos, agents, commands, dashboard URL, suggested next."""
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `holoctl init` first.[/red]")
        raise typer.Exit(1)

    config = load_config(root)
    if check_dirty is None:
        check_dirty = config.get("git", {}).get("checkDirty", False)
    project = config["project"]
    name = project["name"]
    prefix = project["prefix"]

    try:
        from .. import __version__ as _v
    except Exception:
        _v = "?"

    console.print()
    console.print(f"  [bold]{name}[/bold]  [dim]·[/dim]  [cyan]{prefix}[/cyan]  [dim]·[/dim]  [dim]holoctl v{_v}[/dim]")
    console.print()

    # Objective
    obj = root / ".holoctl" / "context" / "objective.md"
    if obj.exists():
        text = obj.read_text(encoding="utf-8")
        first_para = _first_paragraph(text)
        if first_para:
            console.print("  [bold]🎯 Objective[/bold]")
            console.print(f"     [dim]{first_para}[/dim]")
            console.print()

    # Board
    board = Board(root, config)
    stats = board.stat()
    counts = {k: v for k, v in stats.items() if k != "nextId"}
    total = sum(counts.values())
    console.print(f"  [bold]🎫 Board[/bold]  [dim]({total} ticket{'s' if total != 1 else ''})[/dim]")
    console.print(
        f"     [dim]Backlog[/dim] [bold]{counts.get('backlog',0)}[/bold]  [dim]·[/dim]  "
        f"[blue]Doing[/blue] [bold]{counts.get('doing',0)}[/bold]  [dim]·[/dim]  "
        f"[yellow]Review[/yellow] [bold]{counts.get('review',0)}[/bold]  [dim]·[/dim]  "
        f"[green]Done[/green] [bold]{counts.get('done',0)}[/bold]  [dim]·[/dim]  "
        f"[red]Cancelled[/red] [bold]{counts.get('cancelled',0)}[/bold]"
    )
    console.print()

    # Projects (auto-discovered subdirs + manual overrides from config.project.repos[])
    repos = discover_repos(root, include_manual=project.get("repos", []), with_dirty=check_dirty)
    if repos:
        console.print("  [bold]📁 Projects[/bold]")
        all_tickets = board.ls()
        for r in repos:
            git = r.get("git") or {}
            branch = git.get("branch", "—") if git.get("isGit") else "no git"
            dirty = "[yellow] *[/yellow]" if git.get("dirty") else ""
            ticket_count = sum(1 for t in all_tickets if r["name"] in (t.get("projects") or []))
            console.print(f"     [dim]•[/dim] [bold]{r['name']:<14}[/bold] [cyan][{branch}][/cyan]{dirty}  [dim]{ticket_count} ticket{'s' if ticket_count != 1 else ''}[/dim]")
        console.print()

    # Agents
    agents_dir = root / ".holoctl" / "agents"
    if agents_dir.exists():
        agents = sorted(f.stem for f in agents_dir.glob("*.md"))
        if agents:
            console.print("  [bold]🤖 Agents[/bold]")
            console.print(f"     [dim]{' · '.join(agents)}[/dim]")
            console.print()

    # Commands
    commands_dir = root / ".holoctl" / "commands"
    if commands_dir.exists():
        cmds = []
        for f in sorted(commands_dir.glob("*.md")):
            fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
            cmds.append("/" + fm.get("name", f.stem))
        if cmds:
            console.print("  [bold]📋 Slash commands[/bold]")
            console.print(f"     [dim]{' · '.join(cmds)} · /holoctl[/dim]")
            console.print()

    # Dashboard
    console.print("  [bold]🌐 Dashboard[/bold]")
    console.print("     [cyan]http://127.0.0.1:4242[/cyan]  [dim](run `holoctl serve`)[/dim]")
    console.print()

    # Suggested next
    suggestion = _suggest_next(board, counts)
    if suggestion:
        console.print("  [bold]🎯 Suggested next[/bold]")
        console.print(f"     {suggestion}")
        console.print()


def _first_paragraph(text: str) -> str:
    body_lines: list[str] = []
    in_paragraph = False
    skip_frontmatter = False
    for line in text.splitlines():
        if line.strip() == "---":
            skip_frontmatter = not skip_frontmatter
            continue
        if skip_frontmatter:
            continue
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            if in_paragraph:
                break
            continue
        body_lines.append(stripped)
        in_paragraph = True
    return " ".join(body_lines)[:240]


def _suggest_next(board: Board, counts: dict) -> str:
    now = datetime.now(timezone.utc)
    doing = board.ls({"status": "doing"})

    # Stalled tickets (>5 days in doing).
    # `updated` may be a date-only string (`2026-05-04`) on legacy tickets or
    # a full ISO 8601 timestamp on new ones — both parse via fromisoformat
    # in 3.11+.
    for t in doing:
        upd = t.get("updated")
        if not upd:
            continue
        try:
            parsed = datetime.fromisoformat(upd.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age = (now - parsed).days
            if age > 5:
                return f"[yellow]⚠[/yellow] [bold]{t['id']}[/bold] [dim]has been in `doing` for {age} days — review or unblock?[/dim]"
        except (ValueError, TypeError):
            pass

    if counts.get("backlog", 0) == 0 and counts.get("doing", 0) == 0:
        return "[dim]No tickets yet. Create one with[/dim] [bold]/ticket <title>[/bold]"

    # Next p1 from backlog
    backlog_p1 = [t for t in board.ls({"status": "backlog", "priority": "p1"})]
    if backlog_p1:
        t = backlog_p1[0]
        return f"[dim]Next p1:[/dim] [bold]{t['id']}[/bold] [dim]{t['title'][:50]}[/dim]"

    backlog_p0 = [t for t in board.ls({"status": "backlog", "priority": "p0"})]
    if backlog_p0:
        t = backlog_p0[0]
        return f"[red]p0:[/red] [bold]{t['id']}[/bold] [dim]{t['title'][:50]}[/dim]"

    if counts.get("doing", 0) > 0:
        return "[dim]Keep moving on tickets in[/dim] [blue]doing[/blue]"

    return "[dim]No urgent work. Review the backlog with[/dim] [bold]/board[/bold]"
