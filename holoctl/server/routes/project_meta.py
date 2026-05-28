"""Per-project meta pages (agents, commands, context, repos) + the global
agent registry. All four project routes share the same shell: project lookup,
breadcrumbs, project tabs."""
from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..jinja import render
from ..views.meta import (
    agents_context, commands_context, context_context, repos_context,
)
from .project_board import _PROJECT_TABS

router = APIRouter()


def _project_breadcrumbs(project: dict, label: str) -> list[dict]:
    return [
        {"label": "holoctl", "href": "/"},
        {"label": project["name"], "href": f"/project/{project['alias']}/board"},
        {"label": label},
    ]


@router.get("/project/{alias}/agents", response_class=HTMLResponse)
def project_agents(alias: str):
    from ..projects import get_project, read_agents, read_foreign_agents

    project = get_project(alias)
    if not project:
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Not found")),
            status_code=404,
        )
    agents = read_agents(Path(project["path"])) + read_foreign_agents(Path(project["path"]))
    ctx = agents_context(agents, alias)
    return render(
        "project/agents.html",
        title=project["name"],
        current_alias=alias,
        current_tab="agents",
        breadcrumbs=_project_breadcrumbs(project, "Agents"),
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        **ctx,
    )


@router.get("/project/{alias}/commands", response_class=HTMLResponse)
def project_commands(alias: str):
    from ..projects import get_project, read_commands, read_foreign_commands

    project = get_project(alias)
    if not project:
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Not found")),
            status_code=404,
        )
    commands = read_commands(Path(project["path"])) + read_foreign_commands(Path(project["path"]))
    ctx = commands_context(commands, alias)
    return render(
        "project/commands.html",
        title=project["name"],
        current_alias=alias,
        current_tab="commands",
        breadcrumbs=_project_breadcrumbs(project, "Commands"),
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        **ctx,
    )


@router.get("/project/{alias}/context", response_class=HTMLResponse)
def project_context(alias: str):
    from ..projects import get_project, read_context_docs

    project = get_project(alias)
    if not project:
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Not found")),
            status_code=404,
        )
    docs = read_context_docs(Path(project["path"]))
    ctx = context_context(docs, alias)
    return render(
        "project/context.html",
        title=project["name"],
        current_alias=alias,
        current_tab="context",
        breadcrumbs=_project_breadcrumbs(project, "Context"),
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        **ctx,
    )


@router.get("/project/{alias}/repos", response_class=HTMLResponse)
def project_repos(alias: str):
    from ..projects import get_project
    from ...lib.board import Board
    from ...lib.discover import discover_repos

    project = get_project(alias)
    if not project:
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Not found")),
            status_code=404,
        )
    # Dirty-flag check is opt-in via config.git.checkDirty (default false).
    # When on, each subrepo costs one `git status --porcelain` subprocess.
    check_dirty = project["config"].get("git", {}).get("checkDirty", False)
    repos = discover_repos(
        Path(project["path"]),
        include_manual=project["config"]["project"].get("repos", []),
        with_dirty=check_dirty,
    )
    board = Board(Path(project["path"]), project["config"])
    all_tickets = board.ls()
    for r in repos:
        r["ticketCount"] = sum(1 for t in all_tickets
                               if r["name"] in (t.get("projects") or []))
    ctx = repos_context(repos, alias)
    return render(
        "project/repos.html",
        title=project["name"],
        current_alias=alias,
        current_tab="repos",
        breadcrumbs=_project_breadcrumbs(project, "Repos"),
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        **ctx,
    )


@router.get("/agents", response_class=HTMLResponse)
def global_agents():
    from ..projects import get_projects, read_agents

    projects = get_projects()
    all_agents = []
    for p in projects:
        for a in read_agents(Path(p["path"])):
            all_agents.append({**a, "project": p["alias"]})
    ctx = agents_context(all_agents)
    return render(
        "project/agents.html",
        title="Agent Registry",
        projects=projects,
        breadcrumbs=[
            {"label": "holoctl", "href": "/"},
            {"label": "Agent Registry"},
        ],
        **ctx,
    )
