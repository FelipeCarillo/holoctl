from __future__ import annotations
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.agent_library import (
    list_library_agents,
    load_library_agent,
    materialize_agent,
)
from ..lib.config import find_project_root, load_config
from ..lib.markdown import parse_frontmatter

app = typer.Typer(help="Manage agent definitions")


def _require_root() -> Path:
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `hctl init` first.[/red]")
        raise typer.Exit(1)
    return root


def _active_agent_names(agents_dir: Path) -> list[str]:
    if not agents_dir.exists():
        return []
    return sorted(p.stem for p in agents_dir.glob("*.md"))


def _summary_line(name: str, body: str) -> str:
    """Return a single padded line summarizing an agent .md body."""
    data, _ = parse_frontmatter(body)
    model = str(data.get("model", "standard"))
    trigger = str(data.get("trigger", "ticket"))
    desc = str(data.get("description", "")).strip().strip('"').strip("'")
    color = (
        "magenta" if model == "reasoning"
        else "dim" if model == "fast"
        else "cyan"
    )
    return (
        f"  [bold]{name:<16}[/bold] [{color}]{model:<10}[/{color}] "
        f"[dim]{trigger:<12}[/dim] {desc}"
    )


@app.command("list")
def agent_list():
    """List active personas in the workspace and the latent library catalog."""
    root = _require_root()
    agents_dir = root / ".holoctl" / "agents"
    active = _active_agent_names(agents_dir)
    library = list_library_agents()

    console.print("\n  [bold]Active[/bold]  [dim](.holoctl/agents/)[/dim]")
    if not active:
        console.print("  [dim](none)[/dim]")
    else:
        for name in active:
            body = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
            console.print(_summary_line(name, body))

    library_only = [n for n in library if n not in active]
    console.print(
        "\n  [bold]Library[/bold]  [dim](latent — `hctl agent add <name>` to "
        "activate)[/dim]"
    )
    if not library_only:
        console.print("  [dim](all library personas already active)[/dim]")
    else:
        for name in library_only:
            body = load_library_agent(name) or ""
            console.print(_summary_line(name, body))
    console.print("")


@app.command("add")
def agent_add(
    name: str = typer.Argument(..., help="Agent name"),
    from_template: Optional[str] = typer.Option(
        None,
        "--from",
        help="Base on an existing active agent (instead of the library entry).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing .holoctl/agents/<name>.md"
    ),
):
    """Activate a persona — either from the latent library or seeded blank.

    Resolution order:
      1. ``--from <other>`` — copy from an already-active agent.
      2. Library entry matching ``<name>`` — materialized with placeholders
         resolved against current config (``board.statusesJoined`` etc).
      3. Blank scaffold — used when the name doesn't exist in the library.
    """
    root = _require_root()
    agents_dir = root / ".holoctl" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    target_path = agents_dir / f"{name}.md"

    if target_path.exists() and not force:
        console.print(
            f"[yellow]Agent {name} already exists.[/yellow] "
            f"Pass --force to overwrite."
        )
        raise typer.Exit(1)

    if from_template:
        source = agents_dir / f"{from_template}.md"
        if not source.exists():
            console.print(
                f"[red]Template agent {from_template} not found in active "
                f".holoctl/agents/.[/red]"
            )
            raise typer.Exit(1)
        import re
        content = source.read_text(encoding="utf-8")
        content = re.sub(
            r"^(name:\s*).*$", rf"\g<1>{name}", content, flags=re.MULTILINE
        )
        target_path.write_text(content, encoding="utf-8")
        console.print(
            f"[green]Activated[/green] [bold]{name}[/bold] "
            f"[dim](copied from {from_template})[/dim]"
        )
        return

    config = load_config(root)
    library_body = materialize_agent(name, config)
    if library_body is not None:
        target_path.write_text(library_body, encoding="utf-8")
        console.print(
            f"[green]Activated[/green] [bold]{name}[/bold] "
            f"[dim](from library)[/dim]"
        )
        return

    target_path.write_text(_blank_agent_scaffold(name), encoding="utf-8")
    console.print(
        f"[green]Created[/green] [bold]{name}[/bold] "
        f"[dim](blank — fill in body)[/dim]"
    )


@app.command("suggest")
def agent_suggest(
    json_out: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of pretty output."
    ),
):
    """Inspect the codebase and suggest specialist personas to activate.

    Heuristic — detects the tech stack from package files and patterns in the
    workspace, then maps to library personas (`developer`, `reviewer`,
    `architect`, `researcher`). Output is non-destructive — prints the
    suggested `hctl agent add ...` commands without running them.

    Used by the `/holoctl` slash command in Step 5 of the init flow.
    """
    root = _require_root()
    suggestions = _detect_suggestions(root)
    active = _active_agent_names(root / ".holoctl" / "agents")
    library = list_library_agents()

    if json_out:
        import json as _json
        payload = {
            "suggestions": [
                {"name": s["name"], "reason": s["reason"], "active": s["name"] in active}
                for s in suggestions
            ],
            "active": list(active),
            "library": list(library),
        }
        print(_json.dumps(payload, indent=2))
        return

    console.print("\n  [bold]Persona suggestions[/bold] [dim](based on codebase)[/dim]")
    if not suggestions:
        console.print("  [dim]No specific signals detected — `boardmaster` is enough.[/dim]\n")
        return

    new_personas = [s for s in suggestions if s["name"] not in active]
    if not new_personas:
        console.print(
            "  [dim](all suggested personas already active)[/dim]\n"
        )
        return

    for s in new_personas:
        in_lib = s["name"] in library
        marker = "[green]✓[/green]" if in_lib else "[yellow]?[/yellow]"
        console.print(
            f"  {marker} [bold]{s['name']:<14}[/bold] [dim]{s['reason']}[/dim]"
        )

    console.print("\n  [bold]Apply?[/bold] copy/paste:")
    for s in new_personas:
        console.print(f"    [dim]$[/dim] hctl agent add {s['name']}")
    console.print("")


def _detect_suggestions(root: Path) -> list[dict]:
    """Return [{name, reason}] of personas to activate based on workspace signals."""
    out = []
    has_code = False
    has_tests = False
    has_adrs = False
    has_interfaces = False
    has_research = False
    is_monorepo = False

    # Tech stack signals.
    for marker in ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml"):
        if (root / marker).exists():
            has_code = True
            break

    # Tests presence.
    for tests_marker in ("tests", "test", "spec", "__tests__"):
        if (root / tests_marker).is_dir():
            has_tests = True
            break
    if (root / "pyproject.toml").exists():
        try:
            content = (root / "pyproject.toml").read_text(encoding="utf-8")
            if "pytest" in content:
                has_tests = True
        except OSError:
            pass

    # Architecture signals.
    docs = root / "docs"
    if docs.exists():
        for f in docs.rglob("*.md"):
            name_lower = f.name.lower()
            if "adr" in name_lower or "decision" in name_lower:
                has_adrs = True
                break
    for pattern in ("**/interface*.py", "**/interface*.ts", "**/*Interface.java"):
        if any(root.glob(pattern)):
            has_interfaces = True
            break

    # Monorepo signal.
    sub_packages = 0
    skip = {"node_modules", ".venv", "venv", "dist", "build", "target", "__pycache__"}
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith(".") or child.name in skip:
            continue
        for marker in ("package.json", "pyproject.toml", "Cargo.toml", "go.mod"):
            if (child / marker).exists():
                sub_packages += 1
                break
    is_monorepo = sub_packages >= 2

    # Research signal: papers/notebooks.
    if (root / "notebooks").is_dir() or any(root.glob("*.ipynb")):
        has_research = True
    readme = root / "README.md"
    if readme.exists():
        try:
            text = readme.read_text(encoding="utf-8").lower()
            if "paper" in text or "research" in text or "ml" in text or "machine learning" in text:
                has_research = True
        except OSError:
            pass

    # M17.5 signals: dba / devops / security-auditor / tech-writer.
    dba_signals = _detect_dba_signals(root)
    devops_signals = _detect_devops_signals(root)
    security_signals = _detect_security_signals(root)
    docs_signals = _detect_docs_signals(root)

    # Map signals → personas.
    if has_code:
        out.append({"name": "developer", "reason": "code package detected"})
    if has_code and has_tests:
        out.append({"name": "reviewer", "reason": "tests present — code review fits"})
    if has_adrs or has_interfaces or is_monorepo:
        reasons = []
        if has_adrs:
            reasons.append("ADRs in docs/")
        if has_interfaces:
            reasons.append("interface*.{py,ts,java}")
        if is_monorepo:
            reasons.append(f"monorepo ({sub_packages} sub-packages)")
        out.append({"name": "architect", "reason": " · ".join(reasons)})
    if has_research:
        out.append({"name": "researcher", "reason": "research signals (notebooks/papers)"})
    if dba_signals:
        out.append({"name": "dba", "reason": " · ".join(dba_signals)})
    if devops_signals:
        out.append({"name": "devops", "reason": " · ".join(devops_signals)})
    if security_signals:
        out.append({"name": "security-auditor", "reason": " · ".join(security_signals)})
    if docs_signals:
        out.append({"name": "tech-writer", "reason": " · ".join(docs_signals)})

    return out


def _detect_dba_signals(root: Path) -> list[str]:
    """Migration dirs, *.sql files, ORM schema files."""
    reasons: list[str] = []
    skip = {"node_modules", ".venv", "venv", "dist", "build", "target", "__pycache__"}

    def _walk_count(glob: str, *, limit: int = 6) -> int:
        n = 0
        for f in root.glob(glob):
            if any(part in skip for part in f.parts):
                continue
            if f.is_file():
                n += 1
                if n >= limit:
                    break
        return n

    sql_count = _walk_count("**/*.sql")
    if sql_count >= 3:
        reasons.append(f"{'>=' if sql_count >= 6 else ''}{sql_count} *.sql files")
    if any((root / d).is_dir() for d in ("migrations", "alembic", "db/migrate")):
        reasons.append("migrations dir present")
    for prisma in root.glob("**/schema.prisma"):
        if any(part in skip for part in prisma.parts):
            continue
        reasons.append("prisma schema")
        break
    return reasons


def _detect_devops_signals(root: Path) -> list[str]:
    """Workflows, Dockerfiles, terraform, k8s."""
    reasons: list[str] = []
    if (root / ".github" / "workflows").is_dir():
        reasons.append("GitHub Actions workflows")
    if (root / ".gitlab-ci.yml").exists() or (root / ".circleci").is_dir():
        reasons.append("CI config")
    for df in root.glob("**/Dockerfile*"):
        if "node_modules" in df.parts:
            continue
        reasons.append("Dockerfile present")
        break
    if (root / "terraform").is_dir() or any(root.glob("**/*.tf")):
        reasons.append("Terraform IaC")
    if (root / "k8s").is_dir() or (root / "kubernetes").is_dir() or (root / "helm").is_dir():
        reasons.append("k8s/helm manifests")
    return reasons


def _detect_security_signals(root: Path) -> list[str]:
    """SECURITY.md or audit configs."""
    reasons: list[str] = []
    if (root / "SECURITY.md").exists() or (root / ".github" / "SECURITY.md").exists():
        reasons.append("SECURITY.md present")
    audit_configs = (".snyk", "bandit.yaml", ".bandit", "audit-ci.json")
    for cfg in audit_configs:
        if (root / cfg).exists():
            reasons.append(f"{cfg} present")
            break
    return reasons


def _detect_docs_signals(root: Path) -> list[str]:
    """A docs/ directory with substantial md content, or an active CHANGELOG."""
    reasons: list[str] = []
    docs = root / "docs"
    if docs.is_dir():
        md_count = 0
        for f in docs.rglob("*.md"):
            md_count += 1
            if md_count > 10:
                break
        if md_count > 10:
            reasons.append("docs/ with >10 markdown files")
        elif md_count >= 5:
            reasons.append(f"docs/ with {md_count} markdown files")
    if (root / "CHANGELOG.md").exists():
        try:
            size = (root / "CHANGELOG.md").stat().st_size
            if size > 2000:
                reasons.append("active CHANGELOG.md")
        except OSError:
            pass
    return reasons


@app.command("remove")
def agent_remove(
    name: str = typer.Argument(..., help="Agent name to deactivate"),
):
    """Remove an active persona from .holoctl/agents/.

    Refuses to remove ``boardmaster`` (always-essential — board CLI relies on
    it). Other personas can be re-activated later via ``hctl agent add``.
    """
    if name == "boardmaster":
        console.print(
            "[red]Refusing to remove `boardmaster` — it's marked "
            "always_essential.[/red]"
        )
        raise typer.Exit(1)
    root = _require_root()
    target = root / ".holoctl" / "agents" / f"{name}.md"
    if not target.exists():
        console.print(f"[yellow]Agent {name} is not active.[/yellow]")
        raise typer.Exit(1)
    target.unlink()
    console.print(
        f"[green]Removed[/green] [bold]{name}[/bold] "
        f"[dim](still available in library — `hctl agent add {name}` to "
        f"re-activate)[/dim]"
    )


def _blank_agent_scaffold(name: str) -> str:
    return f"""---
name: {name}
description: "(describe what this agent does)"
model: standard
tools: [read, search, edit, write, shell]
trigger: ticket
---

# Identity

You are the **{name}** agent. (Define identity and purpose)

# Guard Rail

(Define when this agent should refuse to work)

# Scope

(Define what this agent does and does NOT do)

# Work Order

1. (Step-by-step work process)

# Report Format

- **Done**: bullets with file:line references.
- **Definition of Done**: each Goal item marked `[x]` or `[ ]`.
- **Suggested next step**: 1 line.
"""
