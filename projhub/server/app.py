from __future__ import annotations
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..lib.workspace import list_workspace
from ..lib.config import load_config
from ..lib.board import Board
from ..lib.markdown import parse_frontmatter
from ..lib.git import get_git_info
from ..lib.filetree import scan_dir

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="projhub dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# ── helpers ──────────────────────────────────────────────────────────────────

def _get_projects() -> list[dict]:
    projects = []
    for p in list_workspace():
        try:
            config = load_config(Path(p["path"]))
            board = Board(Path(p["path"]), config)
            stats = board.stat()
            agents_dir = Path(p["path"]) / ".projhub" / "agents"
            agents = [f.stem for f in agents_dir.glob("*.md")] if agents_dir.exists() else []
            all_tickets = board.ls()
            raw_repos = config["project"].get("repos", [])
            enriched_repos = []
            for r in raw_repos:
                abs_r = Path(p["path"]) / r["path"]
                git = get_git_info(abs_r)
                ticket_count = sum(1 for t in all_tickets if t.get("scope") == r["name"])
                enriched_repos.append({**r, "git": git, "ticketCount": ticket_count})

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
    return [p for p in projects if p["valid"]]


def _get_project(alias: str) -> dict | None:
    return next((p for p in _get_projects() if p["alias"] == alias), None)


def _read_agents(project_path: Path) -> list[dict]:
    d = project_path / ".projhub" / "agents"
    if not d.exists():
        return []
    result = []
    for f in sorted(d.glob("*.md")):
        data, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        result.append({**data, "file": f.name})
    return result


def _read_commands(project_path: Path) -> list[dict]:
    d = project_path / ".projhub" / "commands"
    if not d.exists():
        return []
    result = []
    for f in sorted(d.glob("*.md")):
        data, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        result.append({**data, "file": f.name})
    return result


def _read_context_docs(project_path: Path) -> list[dict]:
    d = project_path / ".projhub" / "context"
    if not d.exists():
        return []
    items = []
    for entry in sorted(d.iterdir()):
        if entry.is_dir():
            items.append({"name": entry.name + "/", "isDir": True, "description": f"{entry.name} folder"})
        elif entry.suffix == ".md":
            content = entry.read_text(encoding="utf-8")
            first_h1 = next((l.removeprefix("# ") for l in content.splitlines() if l.startswith("# ")), "")
            items.append({"name": entry.name, "isDir": False, "description": first_h1})
    return items


# ── layout ───────────────────────────────────────────────────────────────────

def _layout(title: str, body: str, *, sidebar: str = "", topbar: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — projhub</title>
  <link rel="stylesheet" href="/static/projhub.css">
</head>
<body>
  <div class="layout">
    <aside class="sidebar">{sidebar}</aside>
    <div class="main">
      <div class="topbar">{topbar}</div>
      <div class="content-wrap">{body}</div>
    </div>
  </div>
  <script src="/static/projhub-ui.js"></script>
</body>
</html>"""


def _sidebar(projects: list[dict], current_alias: str = "", current_tab: str = "") -> str:
    links = ""
    for p in projects:
        active = "active" if p["alias"] == current_alias else ""
        links += f'<a href="/project/{p["alias"]}/board" class="sidebar-project {active}">{p["name"]}</a>'
    return f"""
<div class="sidebar-header"><a href="/" class="sidebar-logo">projhub</a></div>
<nav class="sidebar-nav">{links}</nav>
<div class="sidebar-footer">
  <a href="/agents">Agents</a>
</div>"""


def _topbar(title: str, breadcrumbs: list[dict] = None, actions: str = "") -> str:
    crumbs = ""
    for b in (breadcrumbs or []):
        if b.get("href"):
            crumbs += f'<a href="{b["href"]}">{b["label"]}</a><span class="sep">/</span>'
        else:
            crumbs += f'<span>{b["label"]}</span>'
    return f'<div class="breadcrumbs">{crumbs}</div><div class="topbar-actions">{actions}</div>'


def _tabs(tabs: list[dict], current: str, base: str) -> str:
    html = '<div class="tabs">'
    for t in tabs:
        active = "active" if t["id"] == current else ""
        html += f'<a href="{base}/{t["id"]}" class="tab {active}">{t.get("icon","")}{t["label"]}</a>'
    html += "</div>"
    return html


_PROJECT_TABS = [
    {"id": "board", "label": "Board"},
    {"id": "repos", "label": "Repos"},
    {"id": "files", "label": "Files"},
    {"id": "agents", "label": "Agents"},
    {"id": "commands", "label": "Commands"},
    {"id": "context", "label": "Context"},
]


def _render(title: str, content: str, *, projects: list[dict] | None = None,
            current_alias: str = "", current_tab: str = "",
            breadcrumbs: list[dict] | None = None,
            tabs: list[dict] | None = None, tab_base: str = "",
            actions: str = "") -> str:
    all_projects = projects if projects is not None else _get_projects()
    sidebar = _sidebar(all_projects, current_alias, current_tab)
    topbar = _topbar(title, breadcrumbs or [], actions)
    tabs_html = _tabs(tabs, current_tab, tab_base) if tabs else ""
    return _layout(title, tabs_html + content, sidebar=sidebar, topbar=topbar)


def _not_found_html(msg: str = "Not found") -> str:
    return f'<div class="content"><div class="empty-state"><h3>{msg}</h3></div></div>'


# ── pages ────────────────────────────────────────────────────────────────────

def _home_page(projects: list[dict]) -> str:
    cards = ""
    for p in projects:
        counts = p.get("counts", {})
        doing = counts.get("doing", 0)
        backlog = counts.get("backlog", 0)
        done = counts.get("done", 0)
        cards += f"""
<a href="/project/{p['alias']}/board" class="project-card">
  <div class="project-card-name">{p['name']}</div>
  <div class="project-card-stats">
    <span>{backlog} backlog</span>
    <span class="doing">{doing} doing</span>
    <span>{done} done</span>
  </div>
  <div class="project-card-targets">{' '.join(p.get('targets', []))}</div>
</a>"""
    if not projects:
        cards = '<div class="empty-state"><h3>No projects yet</h3><p>Run <code>projhub init</code> in a directory to get started.</p></div>'
    return f'<div class="content"><div class="project-grid">{cards}</div></div>'


def _board_page(project: dict, tickets: list[dict], config: dict) -> str:
    statuses = config["board"]["statuses"]
    cols = ""
    for status in statuses:
        col_tickets = [t for t in tickets if t["status"] == status]
        cards = ""
        for t in col_tickets:
            agents = ", ".join(t.get("agent") or []) or "—"
            prio = t.get("priority", "p2")
            cards += f"""
<a href="/project/{project['alias']}/board/{t['id']}" class="ticket-card priority-{prio}">
  <div class="ticket-id">{t['id']} <span class="prio">{prio}</span></div>
  <div class="ticket-title">{t['title'][:60]}</div>
  <div class="ticket-meta">{agents}</div>
</a>"""
        cols += f"""
<div class="board-col">
  <div class="board-col-header">{status.upper()} <span class="count">{len(col_tickets)}</span></div>
  <div class="board-col-cards">{cards}</div>
</div>"""
    return f'<div class="content"><div class="board">{cols}</div></div>'


def _agents_page(agents: list[dict], alias: str = "") -> str:
    rows = ""
    for a in agents:
        name = a.get("name", a.get("file", "?"))
        model = a.get("model", "standard")
        trigger = a.get("trigger", "ticket")
        desc = a.get("description", "")
        link = f"/project/{alias}/agents/{a.get('file','').replace('.md','')}" if alias else "#"
        rows += f'<a href="{link}" class="list-row"><span class="name">{name}</span><span class="badge">{model}</span><span class="dim">{trigger}</span><span>{desc}</span></a>'
    if not rows:
        rows = '<div class="empty-state"><p>No agents defined.</p></div>'
    return f'<div class="content"><div class="list">{rows}</div></div>'


def _commands_page(commands: list[dict], alias: str) -> str:
    rows = ""
    for c in commands:
        name = c.get("name", c.get("file", "?").replace(".md", ""))
        desc = c.get("description", "")
        link = f"/project/{alias}/commands/{c.get('file','').replace('.md','')}"
        rows += f'<a href="{link}" class="list-row"><span class="name">/{name}</span><span>{desc}</span></a>'
    if not rows:
        rows = '<div class="empty-state"><p>No commands defined.</p></div>'
    return f'<div class="content"><div class="list">{rows}</div></div>'


def _context_page(docs: list[dict], alias: str) -> str:
    rows = ""
    for d in docs:
        icon = "📁" if d["isDir"] else "📄"
        link = f"/project/{alias}/context/{d['name']}" if not d["isDir"] else "#"
        rows += f'<a href="{link}" class="list-row"><span>{icon} {d["name"]}</span><span class="dim">{d["description"]}</span></a>'
    if not rows:
        rows = '<div class="empty-state"><p>No context documents.</p></div>'
    return f'<div class="content"><div class="list">{rows}</div></div>'


def _ticket_detail_page(ticket: dict, body: str, back_link: str) -> str:
    agents = ", ".join(ticket.get("agent") or []) or "—"
    import html as _html
    safe_body = _html.escape(body)
    return f"""
<div class="content">
  {back_link}
  <div class="detail-header">
    <h1>{ticket['id']}: {ticket['title']}</h1>
    <div class="meta-row">
      <span class="badge priority-{ticket.get('priority','p2')}">{ticket.get('priority','p2')}</span>
      <span class="badge status-{ticket.get('status','backlog')}">{ticket.get('status','backlog')}</span>
      <span>Agent: {agents}</span>
      <span>Sprint: {ticket.get('sprint') or '—'}</span>
    </div>
  </div>
  <pre class="ticket-body">{safe_body}</pre>
</div>"""


def _repos_page(repos: list[dict], alias: str) -> str:
    rows = ""
    for r in repos:
        git = r.get("git", {})
        branch = git.get("branch", "—") if git.get("isGit") else "no git"
        dirty = " *" if git.get("dirty") else ""
        rows += f"""
<div class="list-row">
  <span class="name">{r['name']}</span>
  <span class="dim">{r.get('path','')}</span>
  <span class="badge">{branch}{dirty}</span>
  <span>{r.get('ticketCount',0)} tickets</span>
</div>"""
    if not rows:
        rows = '<div class="empty-state"><p>No repos registered.</p></div>'
    return f'<div class="content"><div class="list">{rows}</div></div>'


def _files_page(alias: str, entries: list[dict]) -> str:
    def render_entries(items: list[dict]) -> str:
        html = ""
        for e in items:
            if e["type"] == "dir":
                badges = " ".join(f'<span class="badge">{b["label"]}</span>' for b in e.get("badges", []))
                html += f'<div class="file-dir" data-alias="{alias}" data-path="{e["path"]}">📁 {e["name"]} {badges}</div>'
            else:
                html += f'<div class="file-file">📄 {e["name"]}</div>'
        return html

    return f'<div class="content"><div class="file-tree" id="file-tree">{render_entries(entries)}</div></div>'


# ── routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home():
    projects = _get_projects()
    return _render("Home", _home_page(projects), projects=projects,
                   breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": "Home"}])


@app.get("/project/{alias}/board", response_class=HTMLResponse)
def project_board(alias: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    board = Board(Path(project["path"]), project["config"])
    tickets = board.ls()
    return _render(
        project["name"], _board_page(project, tickets, project["config"]),
        current_alias=alias, current_tab="board",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Board"}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/agents", response_class=HTMLResponse)
def project_agents(alias: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    agents = _read_agents(Path(project["path"]))
    return _render(
        project["name"], _agents_page(agents, alias),
        current_alias=alias, current_tab="agents",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Agents"}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/commands", response_class=HTMLResponse)
def project_commands(alias: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    commands = _read_commands(Path(project["path"]))
    return _render(
        project["name"], _commands_page(commands, alias),
        current_alias=alias, current_tab="commands",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Commands"}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/context", response_class=HTMLResponse)
def project_context(alias: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    docs = _read_context_docs(Path(project["path"]))
    return _render(
        project["name"], _context_page(docs, alias),
        current_alias=alias, current_tab="context",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Context"}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/board/{ticket_id}", response_class=HTMLResponse)
def project_ticket(alias: str, ticket_id: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    board = Board(Path(project["path"]), project["config"])
    ticket = board.get(ticket_id)
    if not ticket:
        return HTMLResponse(_render("Not Found", _not_found_html("Ticket not found")), status_code=404)
    ticket_file = Path(project["path"]) / ".projhub" / "board" / ticket["file"]
    _, body = parse_frontmatter(ticket_file.read_text(encoding="utf-8")) if ticket_file.exists() else ({}, "")
    back = f'<a class="back-link" href="/project/{alias}/board">← Back to Board</a>'
    return _render(
        f"{ticket_id} — {project['name']}", _ticket_detail_page(ticket, body, back),
        current_alias=alias, current_tab="board",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Board", "href": f"/project/{alias}/board"}, {"label": ticket_id}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/repos", response_class=HTMLResponse)
def project_repos(alias: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    return _render(
        project["name"], _repos_page(project.get("repos", []), alias),
        current_alias=alias, current_tab="repos",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Repos"}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/files", response_class=HTMLResponse)
def project_files(alias: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    entries = scan_dir(Path(project["path"]), max_depth=1)
    return _render(
        project["name"], _files_page(alias, entries),
        current_alias=alias, current_tab="files",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Files"}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}")
def project_redirect(alias: str):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/project/{alias}/board")


@app.get("/agents", response_class=HTMLResponse)
def global_agents():
    projects = _get_projects()
    all_agents = []
    for p in projects:
        for a in _read_agents(Path(p["path"])):
            all_agents.append({**a, "project": p["alias"]})
    return _render(
        "Agent Registry", _agents_page(all_agents),
        projects=projects,
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": "Agent Registry"}],
    )


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/projects")
def api_projects():
    return {"projects": _get_projects()}


@app.get("/api/project/{alias}/board")
def api_board(alias: str):
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Not found")
    index_path = Path(project["path"]) / ".projhub" / "board" / "index.json"
    if index_path.exists():
        return json.loads(index_path.read_text(encoding="utf-8"))
    return {"meta": {}, "tickets": []}


@app.get("/api/project/{alias}/files")
def api_files(alias: str, path: str = ""):
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Not found")
    safe = path.replace("..", "").lstrip("/\\")
    abs_path = Path(project["path"]) / safe if safe else Path(project["path"])
    if not str(abs_path).startswith(project["path"]):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"entries": scan_dir(abs_path, max_depth=1)}


@app.get("/api/project/{alias}/events")
async def api_events(alias: str):
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Not found")

    index_path = Path(project["path"]) / ".projhub" / "board" / "index.json"

    async def event_stream():
        last_mtime = None
        while True:
            try:
                if index_path.exists():
                    mtime = index_path.stat().st_mtime
                    if mtime != last_mtime:
                        last_mtime = mtime
                        data = index_path.read_text(encoding="utf-8")
                        yield f"event: board-update\ndata: {data}\n\n"
            except Exception:
                pass
            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
