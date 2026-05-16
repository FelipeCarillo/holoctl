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
    kind: Optional[str] = typer.Option(None, "--kind", help="Filter by kind (task, story, bug, spec, epic, ...)"),
    parent: Optional[str] = typer.Option(None, "--parent", help="Filter by parent ID (children of a spec/story/epic)"),
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
    if kind:
        filters["kind"] = kind
    if parent:
        filters["parent"] = parent

    tickets = board.ls(filters)
    if not tickets:
        console.print("[dim]No tickets match the filters.[/dim]")
        return

    for t in tickets:
        dep = f" [dim][dep: {', '.join(t['depends'])}][/dim]" if t.get("depends") else ""
        agents = ", ".join(t["agent"]) if t.get("agent") else "—"
        agents_str = f"[green]{agents}[/green]"
        kind_str = t.get("kind") or "task"
        kind_disp = f"[magenta]{kind_str[:6]:<6}[/magenta]"
        console.print(
            f"[bold]{t['id']}[/bold]  {kind_disp}  {_priority_color(t['priority'])}  "
            f"{_status_color(t['status'])}  {(t.get('sprint') or '—'):<12}  "
            f"{agents_str:<20}  {t['title'][:50]}{dep}"
        )


@app.command("children")
def children_cmd(
    parent_id: str = typer.Argument(..., help="Parent work item ID (spec/story/epic)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show direct children of a work item + aggregate DoD progress.

    Useful for inspecting a spec/story/epic: lists each child task with status,
    plus a roll-up of how many acceptance items are checked vs total.
    """
    board, _, _ = _get_board()
    try:
        result = board.children(parent_id)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return

    parent = result["parent"]
    kind = parent.get("kind") or "task"
    console.print(
        f"[bold]{parent['id']}[/bold] [magenta]{kind}[/magenta] "
        f"{_status_color(parent['status'])} {parent.get('title', '')[:60]}"
    )
    total = result["total_acceptance"]
    acked = result["acked"]
    pct = int(100 * acked / total) if total else 0
    console.print(
        f"  [dim]DoD progress:[/dim] {acked}/{total} ({pct}%)  "
        f"[dim]by_status:[/dim] {result['by_status'] or '(none)'}"
    )
    if not result["children"]:
        console.print("  [dim](no children)[/dim]")
        return
    for c in result["children"]:
        ckind = c.get("kind") or "task"
        kind_disp = f"[magenta]{ckind[:6]:<6}[/magenta]"
        console.print(
            f"  [bold]{c['id']}[/bold]  {kind_disp}  {_priority_color(c['priority'])}  "
            f"{_status_color(c['status'])}  {c['title'][:55]}"
        )


@app.command("move")
def move_cmd(
    ticket_id: str = typer.Argument(..., help="Ticket ID (or comma-separated list for batch move)"),
    status: str = typer.Argument(...),
):
    """Move a ticket (or multiple, comma-separated) to a new status."""
    board, _, _ = _get_board()
    ids = [t.strip() for t in ticket_id.split(",") if t.strip()]
    if len(ids) == 1:
        try:
            result = board.move(ids[0], status)
            console.print(f"{result['id']}: {result['from']} → [bold]{result['to']}[/bold]")
        except (ValueError, KeyError) as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        return
    result = board.batch_move(ids, status)
    for r in result["moved"]:
        console.print(f"{r['id']}: {r['from']} → [bold]{r['to']}[/bold]")
    for err in result["errors"]:
        console.print(f"[red]{err['id']}: {err['error']}[/red]")
    if result["errors"]:
        raise typer.Exit(1)


@app.command("set")
def set_cmd(
    ticket_id: str = typer.Argument(..., help="Ticket ID (or comma-separated list for batch set)"),
    field: str = typer.Argument(...),
    value: list[str] = typer.Argument(...),
):
    """Set a field on one ticket — or many, comma-separated."""
    board, _, _ = _get_board()
    ids = [t.strip() for t in ticket_id.split(",") if t.strip()]
    raw_value = " ".join(value)
    if len(ids) == 1:
        try:
            result = board.set(ids[0], field, raw_value)
            console.print(f"{result['id']}.{result['field']} = {json.dumps(result['value'])}")
        except (KeyError, ValueError) as e:
            msg = str(e).strip("'")
            console.print(f"[red]{msg}[/red]")
            raise typer.Exit(1)
        return
    result = board.batch_set(ids, field, raw_value)
    for r in result["updated"]:
        console.print(f"{r['id']}.{r['field']} = {json.dumps(r['value'])}")
    for err in result["errors"]:
        console.print(f"[red]{err['id']}: {err['error']}[/red]")
    if result["errors"]:
        raise typer.Exit(1)


@app.command("delete")
def delete_cmd(
    ticket_id: str = typer.Argument(..., help="Ticket ID (or comma-separated list)"),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Skip confirmation prompt. Required when running non-interactively.",
    ),
):
    """Hard-delete one or more tickets (removes .md file + index entry).

    For soft-delete that keeps the record, use `hctl board move <ID> cancelled`.
    Hard delete is irreversible — the .md file is removed from disk and the
    index entry is dropped. The id is NOT reused; nextId keeps incrementing.
    """
    import sys
    board, _, _ = _get_board()
    ids = [t.strip() for t in ticket_id.split(",") if t.strip()]
    if not ids:
        console.print("[red]No ticket IDs provided.[/red]")
        raise typer.Exit(1)

    if not force:
        if not sys.stdin.isatty():
            console.print("[red]Refusing to delete non-interactively without --force.[/red]")
            raise typer.Exit(1)
        plural = "tickets" if len(ids) > 1 else "ticket"
        console.print(
            f"[yellow]About to permanently delete {len(ids)} {plural}: "
            f"{', '.join(ids)}.[/yellow]"
        )
        answer = typer.prompt("Type 'yes' to confirm")
        if answer.strip().lower() != "yes":
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(1)

    if len(ids) == 1:
        try:
            result = board.delete(ids[0])
            console.print(f"[green]Deleted {result['id']}[/green]")
        except (KeyError, ValueError) as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        return

    result = board.batch_delete(ids)
    for r in result["deleted"]:
        console.print(f"[green]Deleted {r['id']}[/green]")
    for err in result["errors"]:
        console.print(f"[red]{err['id']}: {err['error']}[/red]")
    if result["errors"]:
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


@app.command("show")
def show_cmd(
    ticket_id: str = typer.Argument(..., help="Ticket ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    body_only: bool = typer.Option(False, "--body-only", help="Print only the body (no frontmatter)"),
):
    """Show full ticket — frontmatter + body — as the single source of truth.

    Replaces reading `.holoctl/board/tickets/<ID>-*.md` directly. Agents
    should always use this command instead of opening the file by hand.
    """
    board, _, _ = _get_board()
    try:
        rec = board.show(ticket_id)
    except (KeyError, FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if as_json:
        print(json.dumps({"id": rec["id"], "frontmatter": rec["frontmatter"], "body": rec["body"]}, indent=2, default=str))
        return
    if body_only:
        print(rec["body"])
        return
    print(rec["raw"])


@app.command("ack")
def ack_cmd(
    ticket_id: str = typer.Argument(...),
    idx: int = typer.Argument(..., help="Zero-based index of the DoD checkbox to toggle"),
):
    """Toggle a Definition-of-Done checkbox at index `idx` (zero-based).

    Counts checkboxes in document order across all sections. Agents call this
    instead of editing the .md by hand (which is blocked by permissions.deny).
    """
    board, _, _ = _get_board()
    try:
        result = board.ack(ticket_id, idx)
    except (KeyError, FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    mark = "[x]" if result["checked"] else "[ ]"
    console.print(f"[green]{result['id']}[/green] ack[{result['idx']}] {mark} {result['text']}")


@app.command("note")
def note_cmd(
    ticket_id: str = typer.Argument(...),
    text: list[str] = typer.Argument(..., help="Note text (joined with spaces)"),
):
    """Append a timestamped note to the ticket's # Notes section."""
    board, _, _ = _get_board()
    try:
        result = board.note(ticket_id, " ".join(text))
    except (KeyError, FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]{result['id']}[/green] note added [dim]({result['ts']})[/dim]")


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
