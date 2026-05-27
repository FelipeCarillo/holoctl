"""Project listing and lookup helpers for the holoctl dashboard.

Provides the shared project cache and the three public entry-points used by
routes and the API endpoints in app.py:

    get_projects(*, with_git=True) -> list[dict]
    get_project(alias)             -> dict | None
    list_workspace()               -> list[dict]

Reader helpers for per-project .holoctl/ artefacts:

    read_agents(project_path)      -> list[dict]
    read_commands(project_path)    -> list[dict]
    read_context_docs(project_path)-> list[dict]
"""
from __future__ import annotations

import time
from pathlib import Path

from ..lib.config import find_project_root, load_config
from ..lib.board import Board
from ..lib.discover import discover_repos
from ..lib.markdown import parse_frontmatter
from ..lib.ecosystem import scan_unmanaged
from ..lib.compiler import manifest

# Cache for get_projects() — git_info subprocess is slow with many repos.
# TTL is short so the dashboard still feels live.
PROJECTS_CACHE: dict = {"data": None, "ts": 0.0}
PROJECTS_CACHE_TTL = 5.0  # seconds


def list_workspace() -> list[dict]:
    """Return a single-element list for the workspace where the server was started.

    Replaces the old global-registry-based `list_workspace()`. The workspace is
    the directory containing `.holoctl/` discovered upwards from cwd.
    """
    root = find_project_root()
    if not root:
        return []
    return [{"path": str(root), "alias": root.name, "added": "", "lastSeen": ""}]


def get_projects(*, with_git: bool = True) -> list[dict]:
    """List all workspace projects with their config and stats.

    Setting `with_git=False` skips the git_info subprocess for each repo, which
    is the dominant cost when projects have many sub-repos. The 5-second cache
    above absorbs back-to-back requests for the same data.
    """
    now = time.monotonic()
    if with_git and PROJECTS_CACHE["data"] is not None and now - PROJECTS_CACHE["ts"] < PROJECTS_CACHE_TTL:
        return PROJECTS_CACHE["data"]

    projects = []
    for p in list_workspace():
        try:
            config = load_config(Path(p["path"]))
            board = Board(Path(p["path"]), config)
            stats = board.stat()
            agents_dir = Path(p["path"]) / ".holoctl" / "agents"
            agents = [f.stem for f in agents_dir.glob("*.md")] if agents_dir.exists() else []
            all_tickets = board.ls()
            discovered = discover_repos(
                Path(p["path"]),
                include_manual=config["project"].get("repos", []),
            )
            enriched_repos = []
            for r in discovered:
                ticket_count = sum(1 for t in all_tickets if r["name"] in (t.get("projects") or []))
                enriched_repos.append({**r, "ticketCount": ticket_count})

            ticket_count = sum(v for k, v in stats.items() if k != "nextId")
            projects.append({
                **p,
                "name": config["project"]["name"],
                "prefix": config["project"]["prefix"],
                "description": config["project"].get("description", ""),
                "counts": stats,
                "ticketCount": ticket_count,
                "agents": agents,
                "targets": config.get("targets", []),
                "repos": enriched_repos,
                "config": config,
                "valid": True,
            })
        except Exception:
            projects.append({**p, "valid": False, "counts": {}, "ticketCount": 0, "agents": [], "targets": []})

    result = [p for p in projects if p["valid"]]
    if with_git:
        PROJECTS_CACHE["data"] = result
        PROJECTS_CACHE["ts"] = now
    return result


def get_project(alias: str) -> dict | None:
    return next((p for p in get_projects() if p["alias"] == alias), None)


def read_agents(project_path: Path) -> list[dict]:
    d = project_path / ".holoctl" / "agents"
    if not d.exists():
        return []
    result = []
    for f in sorted(d.glob("*.md")):
        data, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        result.append({**data, "file": f.name, "managed": True})
    return result


def read_commands(project_path: Path) -> list[dict]:
    d = project_path / ".holoctl" / "commands"
    if not d.exists():
        return []
    result = []
    for f in sorted(d.glob("*.md")):
        data, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        result.append({**data, "file": f.name, "managed": True})
    return result


def read_foreign_agents(project_path: Path) -> list[dict]:
    """Return agents in .claude/agents/ that are NOT tracked by the manifest.

    Guard: if the manifest does not exist (project was never compiled with the
    manifest-era holoctl), return [] — we cannot reliably distinguish managed
    from foreign without a manifest, so we emit nothing rather than reporting
    every .claude/ agent as foreign.
    """
    if not manifest.manifest_path(project_path).exists():
        return []
    foreign_names = scan_unmanaged(project_path).get("agents", [])
    result = []
    for name in foreign_names:
        f = project_path / ".claude" / "agents" / f"{name}.md"
        try:
            data, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        result.append({**data, "file": f"{name}.md", "managed": False})
    return result


def read_foreign_commands(project_path: Path) -> list[dict]:
    """Return commands in .claude/commands/ that are NOT tracked by the manifest.

    Guard: same as read_foreign_agents — requires an existing manifest.
    """
    if not manifest.manifest_path(project_path).exists():
        return []
    foreign_names = scan_unmanaged(project_path).get("commands", [])
    result = []
    for name in foreign_names:
        f = project_path / ".claude" / "commands" / f"{name}.md"
        try:
            data, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        result.append({**data, "file": f"{name}.md", "managed": False})
    return result


def read_context_docs(project_path: Path) -> list[dict]:
    d = project_path / ".holoctl" / "context"
    if not d.exists():
        return []
    items = []
    for entry in sorted(d.iterdir()):
        if entry.is_dir():
            items.append({"name": entry.name, "isDir": True, "description": f"{entry.name}/ folder"})
        elif entry.suffix == ".md":
            content = entry.read_text(encoding="utf-8")
            first_h1 = next((l.removeprefix("# ") for l in content.splitlines() if l.startswith("# ")), "")
            items.append({"name": entry.name, "isDir": False, "description": first_h1})
    return items
