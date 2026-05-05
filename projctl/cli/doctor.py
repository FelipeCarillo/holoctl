from __future__ import annotations
import json

import typer
from ._console import console

from ..lib.config import find_project_root, load_config

app = typer.Typer()


@app.command("doctor")
def doctor_cmd():
    """Check project health."""
    root = find_project_root()
    if not root:
        console.print("[red]No .projctl/ found. Run `projctl init` first.[/red]")
        raise typer.Exit(1)

    console.print("\n  [bold]projctl doctor[/bold]\n")
    issues = 0

    try:
        load_config(root)
        _check("Config", ".projctl/config.json is valid", True)
    except Exception as e:
        _check("Config", f".projctl/config.json: {e}", False)
        issues += 1

    index_path = root / ".projctl" / "board" / "index.json"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            count = len(data.get("tickets", []))
            _check("Board", f"index.json valid ({count} tickets)", True)
        except Exception as e:
            _check("Board", f"index.json parse error: {e}", False)
            issues += 1
    else:
        _check("Board", "index.json exists", False)
        issues += 1

    agents_dir = root / ".projctl" / "agents"
    if agents_dir.exists():
        agent_count = len(list(agents_dir.glob("*.md")))
        ok = agent_count > 0
        _check("Agents", f"{agent_count} agent(s) defined", ok)
        if not ok:
            issues += 1
    else:
        _check("Agents", "agents/ directory exists", False)
        issues += 1

    commands_dir = root / ".projctl" / "commands"
    if commands_dir.exists():
        cmd_count = len(list(commands_dir.glob("*.md")))
        ok = cmd_count > 0
        _check("Commands", f"{cmd_count} command(s) defined", ok)
        if not ok:
            issues += 1
    else:
        _check("Commands", "commands/ directory exists", False)
        issues += 1

    instructions_path = root / ".projctl" / "instructions.md"
    ok = instructions_path.exists()
    _check("Instructions", "instructions.md exists", ok)
    if not ok:
        issues += 1

    context_dir = root / ".projctl" / "context"
    ok = context_dir.exists()
    _check("Context", "context/ directory exists", ok)
    if not ok:
        issues += 1

    console.print("")
    if issues == 0:
        console.print("[green]  All checks passed. Project is healthy.[/green]\n")
    else:
        console.print(f"[yellow]  {issues} issue(s) found.[/yellow]\n")


def _check(category: str, message: str, ok: bool) -> None:
    icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
    console.print(f"  {icon} [dim]{category:<14}[/dim] {message}")
