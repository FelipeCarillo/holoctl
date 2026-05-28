"""`hctl curate` — run the curator and inspect/silence its suggestions."""
from __future__ import annotations

import json
import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from ..lib.curator import (
    apply_curator_action,
    run_curator,
    silence_pattern,
    SUPPRESSION_DAYS,
    _load_ticket_meta,
)

app = typer.Typer(help="Curator — propose extractions / activations from journal patterns")


def _root():
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found.[/red]")
        raise typer.Exit(1)
    return root


@app.command("run")
def curate_run(
    auto: bool = typer.Option(
        False, "--auto",
        help="Materialize new suggestions as meta:curate tickets (default: dry-run, print only).",
    ),
    bypass_cooldown: bool = typer.Option(
        False, "--bypass-cooldown",
        help="Run even if last run was <30min ago (default cooldown). Used by tests.",
    ),
):
    """Run all curator rules; emit new suggestions (rate-limited per day).

    Without --auto this is a dry run: prints what would be created.
    With --auto materializes meta:curate tickets on the board (1 per
    calendar day per workspace, deduplicated against open tickets and
    14-day silence list).
    """
    root = _root()
    suggestions = run_curator(root, auto=auto, bypass_cooldown=bypass_cooldown)
    if not suggestions:
        console.print(
            "  [dim]No new suggestions[/dim] "
            "[dim](rate limit, cooldown, or nothing matched)[/dim]"
        )
        return
    for s in suggestions:
        console.print(
            f"  [bold]{s.title}[/bold]\n"
            f"  [dim]rule={s.rule}  pattern_id={s.pattern_id}  action={s.action}[/dim]"
        )
    if auto:
        console.print(
            f"\n  [green]✓ created {len(suggestions)} ticket(s) "
            f"with tag `meta:curate`[/green]"
        )
    else:
        console.print("\n  [dim]Dry run — pass --auto to materialize.[/dim]")


@app.command("show")
def curate_show():
    """List open meta:curate tickets and their proposed actions."""
    root = _root()
    index_path = root / ".holoctl" / "board" / "index.json"
    if not index_path.exists():
        console.print("[dim](no board)[/dim]")
        return
    data = json.loads(index_path.read_text(encoding="utf-8"))
    tickets = data.get("tickets") or []
    open_curate = [
        t for t in tickets
        if "meta:curate" in (t.get("tags") or [])
        and t.get("status") not in ("done", "cancelled")
    ]
    if not open_curate:
        console.print("[dim](no open curator suggestions)[/dim]")
        return
    for t in open_curate:
        meta = _load_ticket_meta(root, t.get("id", "")) or {}
        action = meta.get("curator_action", "?")
        pattern_id = meta.get("curator_pattern_id", "?")
        rule = meta.get("curator_rule", "?")
        console.print(
            f"  [bold]{t.get('id')}[/bold]  {t.get('title')}\n"
            f"  [dim]action={action}  rule={rule}  pattern={pattern_id}[/dim]"
        )
    console.print(
        "\n  [dim]Approve: `hctl board move <ID> done` "
        "(boardmaster auto-executes the action).[/dim]\n"
        "  [dim]Reject:  `hctl board move <ID> cancelled` or "
        "`hctl curate silence <pattern_id>`.[/dim]"
    )


@app.command("silence")
def curate_silence(
    pattern_id: str = typer.Argument(..., help="Pattern ID printed by `curate show` or `curate run`"),
    days: int = typer.Option(
        SUPPRESSION_DAYS, "--days",
        help=f"Days to suppress (default {SUPPRESSION_DAYS}).",
    ),
):
    """Suppress a curator pattern from re-suggesting for N days."""
    root = _root()
    silence_pattern(root, pattern_id, days=days)
    console.print(
        f"  [green]✓ silenced[/green] [bold]{pattern_id}[/bold] "
        f"[dim]for {days} days[/dim]"
    )


@app.command("apply")
def curate_apply(
    ticket_id: str = typer.Argument(..., help="Ticket ID (e.g. PRJ-042)"),
):
    """Manually execute a meta:curate ticket's action.

    Normally the boardmaster runs this automatically when you move the
    ticket to ``done``. Use this command if the ticket was created by
    hand or if you skipped the board flow.
    """
    root = _root()
    config = load_config(root)
    from ..lib.board import Board
    board = Board(root, config)
    ticket = board.get(ticket_id)
    if ticket is None:
        console.print(f"[red]Ticket {ticket_id} not found[/red]")
        raise typer.Exit(1)
    result = apply_curator_action(root, ticket)
    if result is None:
        console.print(
            f"[yellow]Ticket {ticket_id} has no curator metadata — nothing to apply.[/yellow]"
        )
        return
    if result.get("ok"):
        console.print(
            f"  [green]✓ applied[/green] [bold]{result.get('action')}[/bold] "
            f"[dim]→ {result.get('result')}[/dim]"
        )
    else:
        console.print(
            f"  [red]✗ {result.get('action')}[/red] "
            f"[dim]({result.get('reason')})[/dim]"
        )
