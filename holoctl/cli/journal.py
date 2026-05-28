"""`hctl journal` — record/show events in the workspace journal.

The journal is the input the curator (0.14) reads to detect repeated
patterns and propose extractions. Hooks emitted by `hctl init` /
`hctl setup` call into `hctl journal record` with small payloads on
SessionStart / PostToolUse / Stop. Manual ingestion (`import`) is also
supported for assistants without hook APIs.
"""
from __future__ import annotations

import json
import sys
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root
from ..lib.journal import Journal

app = typer.Typer(help="Record and inspect workspace events (curator input)")


def _journal() -> Journal:
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `hctl init` first.[/red]")
        raise typer.Exit(1)
    return Journal(root)


@app.command("record")
def journal_record(
    kind: str = typer.Argument(
        ..., help="Event kind (e.g. tool_use, session_start, file_edit)",
    ),
    source: str = typer.Option(
        "manual", "--source",
        help="Origin of the event: claude | copilot | codex | manual",
    ),
    payload: Optional[str] = typer.Option(
        None, "--payload",
        help="JSON object payload (defaults to '{}')",
    ),
    payload_from_stdin: bool = typer.Option(
        False, "--stdin",
        help="Read payload JSON from stdin instead of --payload",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q",
        help="Suppress the confirmation line (hooks call this hot)",
    ),
):
    """Append one event to today's journal file."""
    j = _journal()
    if payload_from_stdin:
        raw = sys.stdin.read().strip()
        data = json.loads(raw) if raw else {}
    elif payload:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON in --payload:[/red] {e}")
            raise typer.Exit(1)
    else:
        data = {}
    rec = j.record(kind, source=source, payload=data)
    if not quiet:
        console.print(
            f"[dim]journaled[/dim] [bold]{rec['kind']}[/bold] "
            f"[dim]from[/dim] [cyan]{rec['source']}[/cyan] "
            f"[dim]@ {rec['ts']}[/dim]"
        )


@app.command("show")
def journal_show(
    limit: int = typer.Option(20, "--limit", "-n"),
    kind: Optional[str] = typer.Option(None, "--kind"),
    source: Optional[str] = typer.Option(None, "--source"),
    since: Optional[str] = typer.Option(
        None, "--since", help="ISO timestamp (e.g. 2026-05-07T00:00:00Z)",
    ),
):
    """Print recent journal records."""
    j = _journal()
    records = j.recent(limit=limit, since=since, kind=kind, source=source)
    if not records:
        console.print("[dim](no records)[/dim]")
        return
    for r in records:
        payload_brief = json.dumps(r.get("payload", {}), separators=(",", ":"))
        if len(payload_brief) > 60:
            payload_brief = payload_brief[:57] + "..."
        console.print(
            f"  [dim]{r.get('ts', '')}[/dim] "
            f"[cyan]{r.get('source', '?'):<8}[/cyan] "
            f"[bold]{r.get('kind', '?'):<14}[/bold] "
            f"{payload_brief}"
        )


@app.command("count")
def journal_count(
    since: Optional[str] = typer.Option(None, "--since"),
):
    """Print event counts by kind (since optional ISO timestamp)."""
    j = _journal()
    counts = j.count_by_kind(since=since)
    if not counts:
        console.print("[dim](no records)[/dim]")
        return
    for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        console.print(f"  {n:>5}  {kind}")


@app.command("import")
def journal_import(
    file: str = typer.Argument(..., help="Path to a JSONL file to ingest"),
    source: str = typer.Option("imported", "--source"),
):
    """Bulk-ingest records from a JSONL file (one record per line)."""
    j = _journal()
    n = 0
    with open(file, "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            j.record(
                kind=data.get("kind", "imported"),
                source=data.get("source", source),
                payload=data.get("payload", {}),
                ts=data.get("ts"),
            )
            n += 1
    console.print(
        f"[green]imported {n} record{'s' if n != 1 else ''}[/green] "
        f"[dim]from {file}[/dim]"
    )
