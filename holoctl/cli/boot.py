"""`hctl boot` — minimal session-zero context (<1KB target).

Output is structured to be the FIRST thing printed in a fresh session.
Goal: under 1KB so the assistant doesn't spend tokens loading CLAUDE.md
or the full memory index when the user just wants to get started.

Layout:
    ## <project> — sessão N
    Pendências p0/p1: <up to 3, each line ≤ 80 chars>
    Decisões recentes: <up to 2 dates+slugs>
    Topics: <names only, comma-separated>
    Personas ativas: <names only>
    [optional] ⚡ <K> sugestões do curador (PRJ-NNN, PRJ-NNN, …)

The full content is on disk; this is the *teaser* that points the agent
at what to load next. Lazy by design — every detail is a follow-up call
away (`hctl board get`, `hctl memory get <topic>`, `hctl curate show`).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from ..lib.memory import Memory
from ..lib.journal import Journal

app = typer.Typer()


@app.command("boot")
def boot_cmd(
    target: Optional[str] = typer.Option(
        None, "--target",
        help="Hint of which assistant is calling (claude|copilot|codex). Recorded in journal.",
    ),
    cwd: Optional[str] = typer.Option(
        None, "--cwd",
        help="Working subdir; topics/decisions filtering will prefer this path.",
    ),
    plain: bool = typer.Option(
        False, "--plain",
        help="ASCII-only output (no Rich color codes). Used by tooling.",
    ),
):
    """Print minimal session-zero context, target ≤ 1KB.

    Records a `boot` event in the journal so the curator can correlate
    sessions with later activity.
    """
    root = find_project_root()
    if not root:
        _print(plain, "[red]No .holoctl/ found. Run `hctl init` first.[/red]")
        raise typer.Exit(1)
    config = load_config(root)
    project_name = config.get("project", {}).get("name", root.name)
    prefix = config.get("project", {}).get("prefix", "PRJ")

    j = Journal(root)
    j.record("boot", source=target or "manual", payload={"cwd": cwd or ""})

    session_n = _session_number(j)

    pending = _top_pendings(root, prefix, limit=3)
    decisions = _recent_decisions(root, limit=2)
    topics = _topic_names(root)
    personas = _persona_names(root)
    curate_tickets = _open_curate_tickets(root, prefix, limit=3)

    lines = []
    lines.append(f"## {project_name} — sessão {session_n}")
    if pending:
        lines.append(
            "Pendências p0/p1: " + ", ".join(pending)
        )
    else:
        lines.append("Pendências p0/p1: nenhuma")
    if decisions:
        lines.append("Decisões recentes: " + ", ".join(decisions))
    if topics:
        lines.append(f"Topics: {', '.join(topics)}")
    if personas:
        lines.append(f"Personas ativas: {', '.join(personas)}")
    if curate_tickets:
        n = len(curate_tickets)
        ids = ", ".join(t["id"] for t in curate_tickets)
        lines.append(
            f"⚡ {n} sugestão{'ões' if n != 1 else ''} do curador ({ids}) — "
            f"`hctl curate show`"
        )

    out = "\n".join(lines) + "\n"
    # Soft cap at 1024 chars — truncate gracefully if exceeded.
    if len(out) > 1024:
        out = out[:1020] + "…\n"
    if plain:
        # Strip Rich tags if any leaked in (shouldn't, but defensive).
        import re
        out = re.sub(r"\[/?[^\]]+\]", "", out)
    print(out, end="")


def _print(plain: bool, text: str) -> None:
    if plain:
        import re
        console.print(re.sub(r"\[/?[^\]]+\]", "", text))
    else:
        console.print(text)


def _session_number(journal: Journal) -> int:
    """Approximate session number = count of distinct days the journal has + 1."""
    if not journal.dir.exists():
        return 0
    return sum(1 for _ in journal.dir.glob("*.jsonl"))


def _top_pendings(root: Path, prefix: str, limit: int = 3) -> list[str]:
    index_path = root / ".holoctl" / "board" / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    tickets = data.get("tickets", []) or []
    out: list[tuple[str, int, str]] = []
    for t in tickets:
        if t.get("status") in ("done", "cancelled"):
            continue
        if t.get("priority") not in ("p0", "p1"):
            continue
        title = (t.get("title") or "")[:55]
        rank = 0 if t.get("priority") == "p0" else 1
        tid = t.get("id") or ""
        if t.get("status") == "doing":
            rank -= 10  # surfaces in-flight first
        out.append((tid, rank, title))
    out.sort(key=lambda r: r[1])
    return [f"{tid} {title}" for tid, _, title in out[:limit]]


def _open_curate_tickets(root: Path, prefix: str, limit: int = 3) -> list[dict]:
    index_path = root / ".holoctl" / "board" / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for t in data.get("tickets", []) or []:
        tags = t.get("tags") or []
        if not isinstance(tags, list):
            continue
        if "meta:curate" not in tags:
            continue
        if t.get("status") in ("done", "cancelled"):
            continue
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _recent_decisions(root: Path, limit: int = 2) -> list[str]:
    decisions_dir = root / ".holoctl" / "context" / "decisions"
    if not decisions_dir.exists():
        return []
    files = sorted(
        decisions_dir.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]
    out = []
    for f in files:
        slug = f.stem
        out.append(slug)
    return out


def _topic_names(root: Path) -> list[str]:
    mem = Memory(root)
    return [t.name for t in mem.list_topics()]


def _persona_names(root: Path) -> list[str]:
    agents_dir = root / ".holoctl" / "agents"
    if not agents_dir.exists():
        return []
    return sorted(p.stem for p in agents_dir.glob("*.md"))
