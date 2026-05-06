from __future__ import annotations
import json

import typer
from ._console import console

from ..lib.config import find_project_root, load_config

app = typer.Typer()


_TARGET_OUTPUTS = {
    "claude": ["CLAUDE.md", ".claude/commands"],
    "cursor": [".cursor/rules/holoctl.md", ".cursor/commands"],
    "windsurf": [".windsurfrules", ".windsurf/workflows"],
    "copilot": [".github/copilot-instructions.md", ".github/prompts"],
    "devin": ["AGENTS.md", ".devin/skills"],
}


@app.command("doctor")
def doctor_cmd():
    """Check project health."""
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `holoctl init` first.[/red]")
        raise typer.Exit(1)

    console.print("\n  [bold]holoctl doctor[/bold]\n")
    issues = 0
    config = None

    try:
        config = load_config(root)
        _check("Config", ".holoctl/config.json is valid", True)
    except Exception as e:
        _check("Config", f".holoctl/config.json: {e}", False)
        issues += 1

    # Index <-> .md sync
    index_path = root / ".holoctl" / "board" / "index.json"
    tickets_dir = root / ".holoctl" / "board" / "tickets"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            indexed = {t["id"] for t in data.get("tickets", [])}
            on_disk = set()
            if tickets_dir.exists():
                from ..lib.markdown import parse_frontmatter
                for f in tickets_dir.glob("*.md"):
                    if f.name.startswith("_"):
                        continue
                    fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
                    if fm.get("id"):
                        on_disk.add(fm["id"])
            drift = indexed.symmetric_difference(on_disk)
            if drift:
                _check("Board", f"index.json out of sync ({len(drift)} drift) — run `holoctl board rebuild-index`", False)
                issues += 1
            else:
                _check("Board", f"index.json valid ({len(indexed)} tickets, in sync)", True)
        except Exception as e:
            _check("Board", f"index.json parse error: {e}", False)
            issues += 1
    else:
        _check("Board", "index.json exists", False)
        issues += 1

    # Agents
    agents_dir = root / ".holoctl" / "agents"
    if agents_dir.exists():
        agent_count = len(list(agents_dir.glob("*.md")))
        ok = agent_count > 0
        _check("Agents", f"{agent_count} agent(s) defined", ok)
        if not ok:
            issues += 1
    else:
        _check("Agents", "agents/ directory exists", False)
        issues += 1

    # Commands
    commands_dir = root / ".holoctl" / "commands"
    if commands_dir.exists():
        cmd_count = len(list(commands_dir.glob("*.md")))
        ok = cmd_count > 0
        _check("Commands", f"{cmd_count} command(s) defined", ok)
        if not ok:
            issues += 1
    else:
        _check("Commands", "commands/ directory exists", False)
        issues += 1

    # Instructions
    ok = (root / ".holoctl" / "instructions.md").exists()
    _check("Instructions", "instructions.md exists", ok)
    if not ok:
        issues += 1

    # Context
    ok = (root / ".holoctl" / "context").exists()
    _check("Context", "context/ directory exists", ok)
    if not ok:
        issues += 1

    # Compile targets
    if config:
        targets = config.get("targets", [])
        for tgt in targets:
            outputs = _TARGET_OUTPUTS.get(tgt, [])
            missing = [o for o in outputs if not (root / o).exists()]
            if missing:
                _check("Compile", f"target '{tgt}' missing: {', '.join(missing)} — run `holoctl compile`", False)
                issues += 1
            else:
                _check("Compile", f"target '{tgt}' compiled", True)

    console.print("")
    if issues == 0:
        console.print("[green]  All checks passed. Project is healthy.[/green]\n")
    else:
        console.print(f"[yellow]  {issues} issue(s) found.[/yellow]\n")


def _check(category: str, message: str, ok: bool) -> None:
    icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
    console.print(f"  {icon} [dim]{category:<14}[/dim] {message}")
