from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from ..lib.board import Board

app = typer.Typer(help="Manage the project board (tickets, statuses, sprints)")


def _get_board() -> tuple[Board, dict, Path]:
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `holoctl init` first.[/red]")
        raise typer.Exit(1)
    config = load_config(root)
    return Board(root, config), config, root


@app.command("stat")
def stat_cmd():
    """Show ticket counts by status."""
    board, _, _ = _get_board()
    print(json.dumps(board.stat(), indent=2))


@app.command("get")
def get_cmd(ticket_id: str = typer.Argument(..., help="Ticket ID")):
    """Get a single ticket by ID."""
    board, _, _ = _get_board()
    ticket = board.get(ticket_id)
    if not ticket:
        console.print(f"[red]Ticket {ticket_id} not found[/red]")
        raise typer.Exit(1)
    print(json.dumps(ticket, indent=2))


@app.command("ls")
def ls_cmd(
    priority: Optional[str] = typer.Argument(None, help="Filter by priority (p0, p1, p2, p3)"),
    sprint: Optional[str] = typer.Option(None, "--sprint"),
    status: Optional[str] = typer.Option(None, "--status"),
    agent: Optional[str] = typer.Option(None, "--agent"),
    tag: Optional[str] = typer.Option(None, "--tag"),
    project: Optional[str] = typer.Option(None, "--project", help="Filter by project (subdir name discovered in workspace)"),
):
    """List tickets with optional filters."""
    board, _, _ = _get_board()
    filters: dict = {}
    if sprint:
        filters["sprint"] = sprint
    if status:
        filters["status"] = status
    if agent:
        filters["agent"] = agent
    if tag:
        filters["tag"] = tag
    if project:
        filters["project"] = project
    if priority and priority.startswith("p") and len(priority) == 2:
        filters["priority"] = priority

    tickets = board.ls(filters)
    if not tickets:
        console.print("[dim]No tickets match the filters.[/dim]")
        return

    for t in tickets:
        dep = f" [dim][dep: {', '.join(t['depends'])}][/dim]" if t.get("depends") else ""
        agents = ", ".join(t["agent"]) if t.get("agent") else "—"
        agents_str = f"[green]{agents}[/green]"
        console.print(
            f"[bold]{t['id']}[/bold]  {_priority_color(t['priority'])}  "
            f"{_status_color(t['status'])}  {(t.get('sprint') or '—'):<12}  "
            f"{agents_str:<20}  {t['title'][:50]}{dep}"
        )


@app.command("move")
def move_cmd(
    ticket_id: str = typer.Argument(...),
    status: str = typer.Argument(...),
):
    """Move a ticket to a new status."""
    board, _, _ = _get_board()
    try:
        result = board.move(ticket_id, status)
        console.print(f"{result['id']}: {result['from']} → [bold]{result['to']}[/bold]")
    except (ValueError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command("set")
def set_cmd(
    ticket_id: str = typer.Argument(...),
    field: str = typer.Argument(...),
    value: list[str] = typer.Argument(...),
):
    """Set a field on a ticket."""
    board, _, _ = _get_board()
    try:
        result = board.set(ticket_id, field, " ".join(value))
        console.print(f"{result['id']}.{result['field']} = {json.dumps(result['value'])}")
    except (KeyError, ValueError) as e:
        msg = str(e).strip("'")
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)


@app.command("add")
def add_cmd(ticket_json: str = typer.Argument(..., help="JSON ticket data")):
    """Create a new ticket from JSON."""
    board, _, _ = _get_board()
    try:
        patch = json.loads(ticket_json)
        ticket = board.add(patch)
        console.print(f"[green]Created {ticket['id']}: {ticket['title']}[/green]")
        print(json.dumps(ticket, indent=2))
    except (json.JSONDecodeError, Exception) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command("batch")
def batch_cmd(
    payload: Optional[str] = typer.Argument(None, help="JSON: {\"shared\":{...},\"tickets\":[...]}"),
    from_file: Optional[str] = typer.Option(None, "--from-file", "-f", help="Read JSON from a file instead of argv"),
):
    """Create N parallel-safe tickets in one call.

    Validates that each ticket declares `files` and that file sets are
    disjoint between siblings (no two tickets touch the same path). Aborts
    atomically on any violation — no partial creation.
    """
    import sys
    from pathlib import Path as _Path
    board, _, _ = _get_board()

    if from_file:
        raw = _Path(from_file).read_text(encoding="utf-8")
    elif payload is not None:
        raw = payload
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        console.print(
            "[red]Pass JSON as argument, via --from-file <path>, or via stdin.[/red]\n"
            "[dim]Example: hctl board batch '{\"shared\":{\"tags\":[\"par:auth\"]},\"tickets\":[{...},{...}]}'[/dim]"
        )
        raise typer.Exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON: {e}[/red]")
        raise typer.Exit(1)

    if not isinstance(data, dict):
        console.print("[red]Expected an object with `shared` and `tickets` keys.[/red]")
        raise typer.Exit(1)

    try:
        result = board.batch_add(data.get("shared") or {}, data.get("tickets") or [])
    except (ValueError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Created {result['count']} parallel-safe ticket(s):[/green]")
    for t in result["tickets"]:
        agents = ",".join(t.get("agent") or []) or "—"
        console.print(f"  [bold]{t['id']}[/bold]  {t['title'][:50]}  [dim](agent={agents}, files={len(t.get('files') or [])})[/dim]")


@app.command("body")
def body_cmd(
    ticket_id: str = typer.Argument(...),
    from_file: Optional[str] = typer.Option(None, "--from-file", "-f", help="Read body from a file instead of stdin"),
):
    """Replace the body of a ticket .md (preserves frontmatter)."""
    import sys
    board, _, _ = _get_board()
    if from_file:
        from pathlib import Path
        body_text = Path(from_file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        body_text = sys.stdin.read()
    else:
        console.print(
            "[red]Pipe the new body via stdin or pass --from-file <path>.[/red]\n"
            "[dim]Example: echo '# Goal\\n- [ ] criterion' | hctl board body PRJ-001[/dim]"
        )
        raise typer.Exit(1)

    if not body_text.strip():
        console.print("[red]Body is empty. Refusing to overwrite ticket with nothing.[/red]")
        raise typer.Exit(1)

    try:
        result = board.set_body(ticket_id, body_text)
        console.print(f"[green]{result['id']} body updated[/green] [dim]({result['bytes']} bytes)[/dim]")
    except (KeyError, FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command("next-id")
def next_id_cmd():
    """Show the next available ticket ID."""
    board, _, _ = _get_board()
    print(board.next_id())


@app.command("rebuild-index")
def rebuild_index_cmd():
    """Rebuild index.json from ticket .md files."""
    board, _, _ = _get_board()
    result = board.rebuild_index()
    console.print(f"[green]Rebuilt index: {result['ticketCount']} tickets, nextId: {result['nextId']}[/green]")


def _priority_color(p: str) -> str:
    colors = {"p0": "red", "p1": "yellow", "p2": "blue", "p3": "dim"}
    color = colors.get(p, "white")
    return f"[{color}]{p:<2}[/{color}]"


def _status_color(s: str) -> str:
    colors = {"backlog": "dim", "doing": "cyan", "review": "yellow", "done": "green", "cancelled": "strike"}
    color = colors.get(s, "white")
    return f"[{color}]{s:<10}[/{color}]"
