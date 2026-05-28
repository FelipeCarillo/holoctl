"""`hctl handoff` — end-of-session persistence (1 line per session).

Reads the journal of the current session + git diff HEAD and appends
a single line to `.holoctl/memory/topics/session-trail.md`. Next
`hctl boot` reads the last 3 lines as part of the lazy memory.

Designed to be cheap (<200ms even on workspaces with 50+ tickets) so
hooks can call it on `Stop` / `SessionEnd` without slowing the user
down. Records a `handoff` event in the journal too.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root
from ..lib.journal import Journal
from ..lib.memory import Memory

app = typer.Typer()


@app.command("handoff")
def handoff_cmd(
    note: Optional[str] = typer.Option(
        None, "--note", "-m",
        help="Optional one-line note to append after the auto-summary.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
):
    """End-of-session persistence: append a session-trail line.

    Computes from journal + git diff:
      - duration of session (first to last journal record today)
      - tickets touched (extracted from board moves + journal events)
      - files changed (from git diff HEAD)
    Appends one line to .holoctl/memory/topics/session-trail.md.
    """
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found.[/red]")
        raise typer.Exit(1)

    j = Journal(root)
    mem = Memory(root)

    today_records = list(j.iter_records())
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_records = [r for r in today_records if r.get("ts", "").startswith(today_str)]

    # Compute duration as the time span of today's records.
    if today_records:
        ts_values = sorted(r.get("ts", "") for r in today_records)
        duration = _format_duration(ts_values[0], ts_values[-1])
    else:
        duration = "0min"

    # Tool usage summary from journal.
    tool_count = sum(1 for r in today_records if r.get("kind") in ("tool_use", "file_edit"))
    sources = sorted({r.get("source", "?") for r in today_records if r.get("source")})

    files_changed = _git_files_changed(root)
    files_brief = _format_files_brief(files_changed)

    line_parts = [
        f"- **{today_str}** ({duration})",
        f"sources: {','.join(sources) if sources else 'manual'}",
        f"events: {tool_count}",
    ]
    if files_changed:
        line_parts.append(f"changed: {files_brief}")
    if note:
        line_parts.append(f"note: {note}")
    summary_line = " · ".join(line_parts) + "\n"

    _append_session_trail(mem, summary_line)
    j.record(
        "handoff",
        source="manual",
        payload={
            "duration": duration,
            "events": tool_count,
            "files_changed": len(files_changed),
        },
    )

    if not quiet:
        console.print(
            "  [green]✓ session trail updated[/green] "
            f"[dim]({duration}, {tool_count} events, "
            f"{len(files_changed)} files)[/dim]"
        )
        console.print("  [dim]→ .holoctl/memory/topics/session-trail.md[/dim]")


def _append_session_trail(mem: Memory, line: str) -> None:
    """Append `line` to the lazy session-trail topic, creating it if absent."""
    topic = mem.get_topic("session-trail")
    if topic is None:
        # Create the topic with a header + this first line.
        body = (
            "# Session trail\n"
            "\n"
            "One-line summary per session. Most recent at the bottom. "
            "The boot command surfaces the last 1-3 lines.\n"
            "\n"
            f"{line}"
        )
        mem.add_topic(
            "session-trail",
            body=body,
            scope="lazy",
            description=(
                "Recent session activity log — what happened in past sessions, "
                "files touched, tickets closed. Read when the user asks 'what "
                "did we do last time?' or 'where did we stop?'."
            ),
        )
        return
    # Append in place.
    new_body = topic.body.rstrip("\n") + "\n" + line
    mem.add_topic(
        "session-trail",
        body=new_body,
        scope="lazy",
        description=topic.description,
        overwrite=True,
    )


def _format_duration(start: str, end: str) -> str:
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return "0min"
    secs = max(int((e - s).total_seconds()), 0)
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}min"
    hours = mins // 60
    rem = mins % 60
    return f"{hours}h{rem}min" if rem else f"{hours}h"


def _git_files_changed(root: Path) -> list[str]:
    git = shutil.which("git")
    if not git:
        return []
    try:
        # Files in working copy that differ from HEAD (staged + unstaged).
        # `encoding="utf-8"` is required on Windows: `text=True` alone falls
        # back to `locale.getpreferredencoding()` (cp1252), which mangles
        # filenames with accents (a common case for pt-BR repos).
        out = subprocess.check_output(
            [git, "-C", str(root), "diff", "--name-only", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _format_files_brief(files: list[str], limit: int = 5) -> str:
    if len(files) <= limit:
        return ", ".join(files)
    return ", ".join(files[:limit]) + f" (+{len(files) - limit} more)"
