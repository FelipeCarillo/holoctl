from __future__ import annotations
import json
import re
from pathlib import Path

import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from .. import __version__

app = typer.Typer()


_TARGET_OUTPUTS = {
    "claude": ["CLAUDE.md", ".claude/commands"],
    "cursor": [".cursor/rules/holoctl.md", ".cursor/commands"],
    "windsurf": [".windsurfrules", ".windsurf/workflows"],
    "copilot": [".github/copilot-instructions.md", ".github/prompts"],
    "devin": [".devin/skills"],
    "agents": ["AGENTS.md"],
}


def _semver_lt(a: str, b: str) -> bool:
    def t(v):
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(v).strip())
        return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)
    return t(a) < t(b)


@app.command("doctor")
def doctor_cmd(
    global_check: bool = typer.Option(
        False,
        "--global",
        help="Check global router installation drift across tools (Claude/Copilot/Devin).",
    ),
):
    """Check project health.

    First line of output is router-friendly:
      - `holoctl: not initialized`  → no .holoctl/ found
      - `holoctl: outdated`         → workspace below installed hctl version
      - `holoctl: ok`               → workspace healthy

    Slash command routers (Claude `/holoctl`, Devin `holoctl` skill, Copilot
    prompt) parse this line to choose init / upgrade / operate flow.

    Pass `--global` to check ~/.claude, ~/.copilot, ~/.config/devin install
    drift instead of project-level health.
    """
    if global_check:
        _doctor_global()
        return

    root = find_project_root()
    if not root:
        # Router-friendly first line.
        print("holoctl: not initialized")
        console.print(
            "[dim]No .holoctl/ found at or above the current directory. "
            "Run `hctl init` to start.[/dim]"
        )
        raise typer.Exit(1)

    # Detect outdated / ok before any other check (so router gets it fast).
    try:
        config_pre = load_config(root)
        ws_version = config_pre.get("holoctlVersion", "0.0.0")
    except Exception:
        ws_version = "0.0.0"
    if _semver_lt(ws_version, __version__):
        print("holoctl: outdated")
    else:
        print("holoctl: ok")

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


def _doctor_global() -> None:
    """Check that global routers are installed and current across all tools."""
    print("holoctl: global-check")
    console.print("\n  [bold]hctl doctor --global[/bold]\n")

    from ..lib.compiler.template import load_bootstrap

    issues = 0

    # Claude
    claude_path = Path.home() / ".claude" / "commands" / "holoctl.md"
    template = load_bootstrap("holoctl-claude.md")
    if not claude_path.exists():
        _check("Claude", "router missing — run `hctl setup-global --target claude`", False)
        issues += 1
    elif template and claude_path.read_text(encoding="utf-8") != template:
        _check("Claude", "router stale (drift) — run `hctl setup-global --target claude`", False)
        issues += 1
    else:
        _check("Claude", f"router up-to-date ({claude_path})", True)

    # Copilot
    copilot_path = Path.home() / ".copilot" / "AGENTS.md"
    if not copilot_path.exists():
        _check("Copilot", "no ~/.copilot/AGENTS.md — run `hctl setup-global --target copilot`", False)
        issues += 1
    else:
        existing = copilot_path.read_text(encoding="utf-8")
        if "<!-- holoctl:start -->" not in existing or "<!-- holoctl:end -->" not in existing:
            _check("Copilot", "AGENTS.md missing holoctl block — run `hctl setup-global --target copilot`", False)
            issues += 1
        else:
            _check("Copilot", f"holoctl block present ({copilot_path})", True)

    # Devin
    devin_path = Path.home() / ".config" / "devin" / "skills" / "holoctl" / "SKILL.md"
    template_d = load_bootstrap("holoctl-devin.md")
    if not devin_path.exists():
        _check("Devin", "skill missing — run `hctl setup-global --target devin`", False)
        issues += 1
    elif template_d and devin_path.read_text(encoding="utf-8") != template_d:
        _check("Devin", "skill stale (drift) — run `hctl setup-global --target devin`", False)
        issues += 1
    else:
        _check("Devin", f"skill up-to-date ({devin_path})", True)

    console.print("")
    if issues == 0:
        console.print("[green]  All global routers up-to-date.[/green]\n")
    else:
        console.print(
            f"[yellow]  {issues} issue(s). Run "
            f"[bold]hctl setup-global --target all[/bold] to fix.[/yellow]\n"
        )
