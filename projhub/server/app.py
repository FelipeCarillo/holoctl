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

# Cache for _get_projects() — git_info subprocess is slow with many repos.
# TTL is short so the dashboard still feels live.
_PROJECTS_CACHE: dict = {"data": None, "ts": 0.0}
_PROJECTS_CACHE_TTL = 5.0  # seconds

# ── SVG icons ─────────────────────────────────────────────────────────────────

_SVG_ATTRS = 'width="16" height="16" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'

_ICON_FOLDER = f'<svg viewBox="0 0 24 24" {_SVG_ATTRS}><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/></svg>'
_ICON_DOC = f'<svg viewBox="0 0 24 24" {_SVG_ATTRS}><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>'
_ICON_CMD = f'<svg viewBox="0 0 24 24" {_SVG_ATTRS}><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>'
_ICON_REPO = f'<svg viewBox="0 0 24 24" {_SVG_ATTRS}><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 00-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0020 4.77 5.07 5.07 0 0019.91 1S18.73.65 16 2.48a13.38 13.38 0 00-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 005 4.77a5.44 5.44 0 00-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 009 18.13V22"/></svg>'
_ICON_SUN = f'<svg viewBox="0 0 24 24" {_SVG_ATTRS}><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
_ICON_MOON = f'<svg viewBox="0 0 24 24" {_SVG_ATTRS}><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>'
_ICON_MENU = f'<svg viewBox="0 0 24 24" {_SVG_ATTRS}><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>'

# ── helpers ──────────────────────────────────────────────────────────────────

def _get_projects(*, with_git: bool = True) -> list[dict]:
    """List all workspace projects with their config and stats.

    Setting `with_git=False` skips the git_info subprocess for each repo, which
    is the dominant cost when projects have many sub-repos. The 5-second cache
    above absorbs back-to-back requests for the same data.
    """
    import time
    now = time.monotonic()
    if with_git and _PROJECTS_CACHE["data"] is not None and now - _PROJECTS_CACHE["ts"] < _PROJECTS_CACHE_TTL:
        return _PROJECTS_CACHE["data"]

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
                git = get_git_info(abs_r) if with_git else {"isGit": False}
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

    result = [p for p in projects if p["valid"]]
    if with_git:
        _PROJECTS_CACHE["data"] = result
        _PROJECTS_CACHE["ts"] = now
    return result


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
            items.append({"name": entry.name, "isDir": True, "description": f"{entry.name}/ folder"})
        elif entry.suffix == ".md":
            content = entry.read_text(encoding="utf-8")
            first_h1 = next((l.removeprefix("# ") for l in content.splitlines() if l.startswith("# ")), "")
            items.append({"name": entry.name, "isDir": False, "description": first_h1})
    return items


# ── layout ───────────────────────────────────────────────────────────────────

def _layout(title: str, body: str, *, sidebar: str = "", topbar: str = "") -> str:
    # Inline script in <head> applies theme + sidebar state BEFORE first paint to
    # avoid the dark→light flash on navigation.
    boot_script = (
        "<script>(function(){try{"
        "var t=localStorage.getItem('projhub-theme')||'dark';"
        "document.documentElement.setAttribute('data-theme',t);"
        "if(localStorage.getItem('projhub-sidebar')==='collapsed'){"
        "document.documentElement.setAttribute('data-sidebar','collapsed');"
        "}"
        "}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();</script>"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — projhub</title>
  {boot_script}
  <link rel="stylesheet" href="/static/projhub.css">
</head>
<body>
  <div class="app" id="app">
    <aside class="sidebar" id="sidebar">{sidebar}</aside>
    <div class="main">
      <div class="topbar">{topbar}</div>
      <div class="content-wrap">{body}</div>
    </div>
  </div>
  <script src="/static/projhub-ui.js"></script>
</body>
</html>"""


def _sidebar(projects: list[dict], current_alias: str = "") -> str:
    links = ""
    for p in projects:
        active = "active" if p["alias"] == current_alias else ""
        doing = p.get("counts", {}).get("doing", 0)
        badge = f'<span class="badge">{doing}</span>' if doing > 0 else ""
        initial = (p.get("prefix") or p["name"][:2] or "?")[:2].upper()
        links += (
            f'<a href="/project/{p["alias"]}/board" class="nav-item {active}" title="{p["name"]}">'
            f'<span class="nav-icon">{initial}</span>'
            f'<span class="nav-item-text">{p["name"]}</span>'
            f'{badge}</a>'
        )

    theme_btn = f"""<button class="icon-btn" onclick="__toggleTheme()" title="Toggle theme">
      <span class="theme-icon-dark">{_ICON_MOON}</span>
      <span class="theme-icon-light">{_ICON_SUN}</span>
    </button>"""
    collapse_btn = f'<button class="icon-btn" onclick="__toggleSidebar()" title="Toggle sidebar">{_ICON_MENU}</button>'

    empty_nav = '<div class="nav-item" style="opacity:.5"><span class="nav-icon">?</span><span class="nav-item-text">No projects</span></div>'
    return f"""
<div class="sidebar-header">
  <a href="/" class="sidebar-brand" title="projhub home">
    <span class="logo">P</span>
    <span class="sidebar-brand-name">projhub</span>
  </a>
  <div class="sidebar-header-actions">{theme_btn}{collapse_btn}</div>
</div>
<nav class="sidebar-nav">
  <div class="nav-group">
    <div class="nav-group-label">Projects</div>
    {links if links else empty_nav}
  </div>
</nav>
<div class="sidebar-footer">
  <a href="/agents" class="nav-item" title="Agents"><span class="nav-icon">★</span><span class="nav-item-text">Agents</span></a>
</div>"""


def _topbar(title: str, breadcrumbs: list[dict] = None, actions: str = "") -> str:
    crumbs = ""
    for b in (breadcrumbs or []):
        if b.get("href"):
            crumbs += f'<a href="{b["href"]}">{b["label"]}</a><span class="sep">/</span>'
        else:
            crumbs += f'<span>{b["label"]}</span>'
    return f'<div class="topbar-breadcrumb">{crumbs}</div><div class="topbar-actions">{actions}</div>'


def _tabs(tabs: list[dict], current: str, base: str) -> str:
    html = '<div class="tabs">'
    for t in tabs:
        active = "active" if t["id"] == current else ""
        html += f'<a href="{base}/{t["id"]}" class="tab {active}">{t["label"]}</a>'
    html += "</div>"
    return html


_PROJECT_TABS = [
    {"id": "board", "label": "Board"},
    {"id": "repos", "label": "Repos"},
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
    sidebar = _sidebar(all_projects, current_alias)
    topbar = _topbar(title, breadcrumbs or [], actions)
    tabs_html = _tabs(tabs, current_tab, tab_base) if tabs else ""
    return _layout(title, tabs_html + f'<div class="content">{content}</div>', sidebar=sidebar, topbar=topbar)


def _not_found_html(msg: str = "Not found") -> str:
    return f'<div class="empty-state"><h3>{msg}</h3></div>'


# ── page generators ───────────────────────────────────────────────────────────

def _home_page(projects: list[dict]) -> str:
    if not projects:
        return '<div class="empty-state"><h3>No projects yet</h3><p>Run <code>projhub init</code> in a directory to get started.</p></div>'
    cards = ""
    for p in projects:
        counts = p.get("counts", {})
        doing = counts.get("doing", 0)
        backlog = counts.get("backlog", 0)
        done = counts.get("done", 0)
        total = max(p.get("ticketCount", 0), 1)
        prefix = p.get("prefix", "")
        targets = "".join(f'<span class="chip chip-target">{t}</span>' for t in p.get("targets", []))
        progress = f"""<div class="progress-bar">
  <div class="progress-segment done" style="width:{done/total*100:.0f}%"></div>
  <div class="progress-segment doing" style="width:{doing/total*100:.0f}%"></div>
  <div class="progress-segment backlog" style="width:{backlog/total*100:.0f}%"></div>
</div>"""
        cards += f"""<a href="/project/{p['alias']}/board" class="project-card">
  <div class="project-card-header">
    <div class="project-card-icon">{prefix[:2]}</div>
    <div>
      <div class="project-card-name">{p['name']}</div>
      <div class="project-card-sub">{p['alias']}</div>
    </div>
  </div>
  {progress}
  <div class="project-card-stats">
    <span class="stat-mini"><span class="stat-dot backlog"></span>{backlog} backlog</span>
    <span class="stat-mini"><span class="stat-dot doing"></span>{doing} doing</span>
    <span class="stat-mini"><span class="stat-dot done"></span>{done} done</span>
  </div>
  <div class="project-card-meta">{targets}</div>
</a>"""
    return f'<div class="project-grid">{cards}</div>'


def _board_page(project: dict, tickets: list[dict], config: dict) -> str:
    statuses = config["board"]["statuses"]
    alias = project["alias"]
    path_display = project.get("path", "")
    cols = ""
    for status in statuses:
        col_tickets = [t for t in tickets if t["status"] == status]
        cards = ""
        for t in col_tickets:
            agents = ", ".join(t.get("agent") or []) or "—"
            prio = t.get("priority", "p2")
            sprint = t.get("sprint") or ""
            sprint_chip = f'<span class="chip chip-sprint">{sprint}</span>' if sprint else ""
            cards += f"""<a href="/project/{alias}/board/{t['id']}" class="kanban-card" data-p="{prio}" data-scope="{t.get('scope','src')}">
  <div class="kanban-card-top">
    <span class="kanban-card-id">{t['id']}</span>
    <span class="p-badge {prio}">{prio}</span>
  </div>
  <div class="kanban-card-title">{t['title'][:60]}</div>
  <div class="kanban-card-meta">
    <span class="chip chip-agent">{agents}</span>{sprint_chip}
  </div>
</a>"""
        if not cards:
            cards = '<div class="kanban-empty">No tickets</div>'
        cols += f"""<div class="kanban-col" data-status="{status}">
  <div class="kanban-col-header">
    <span class="col-label">{status.upper()}</span>
    <span class="count">{len(col_tickets)}</span>
  </div>
  <div class="kanban-cards">{cards}</div>
</div>"""

    live = '<span class="live-indicator"><span class="pulse"></span>LIVE</span>'
    path_el = f'<span class="board-path">{path_display}</span>'
    header = f'<div class="board-header">{live}{path_el}</div>'
    return f'{header}<div class="kanban" id="kanban">{cols}</div>'


def _agents_page(agents: list[dict], alias: str = "") -> str:
    if not agents:
        return '<div class="empty-state"><p>No agents defined.</p></div>'
    cards = ""
    for a in agents:
        name = a.get("name", a.get("file", "?").replace(".md", ""))
        model = a.get("model", "standard")
        trigger = a.get("trigger", "ticket")
        desc = a.get("description", "")
        tools = a.get("tools", [])
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",")]
        tool_chips = "".join(f'<span class="tool-chip">{t}</span>' for t in tools)
        link = f"/project/{alias}/agents/{a.get('file','').replace('.md','')}" if alias else "#"
        cards += f"""<a href="{link}" class="agent-card">
  <div class="agent-card-header">
    <span class="agent-card-name">{name}</span>
    <span class="trigger-badge">{trigger}</span>
    <span class="model-badge {model}">{model}</span>
  </div>
  <div class="agent-card-desc">{desc}</div>
  <div class="agent-card-meta">{tool_chips}</div>
</a>"""
    return f'<div class="agent-grid">{cards}</div>'


def _commands_page(commands: list[dict], alias: str) -> str:
    if not commands:
        return '<div class="empty-state"><p>No commands defined.</p></div>'
    items = ""
    for c in commands:
        name = c.get("name", c.get("file", "?").replace(".md", ""))
        desc = c.get("description", "")
        link = f"/project/{alias}/commands/{c.get('file','').replace('.md','')}"
        items += f"""<a href="{link}" class="context-item">
  <div class="context-item-icon command">{_ICON_CMD}</div>
  <div>
    <div class="context-item-name">/{name}</div>
    <div class="context-item-desc">{desc}</div>
  </div>
</a>"""
    return f'<div class="context-list">{items}</div>'


def _context_page(docs: list[dict], alias: str) -> str:
    if not docs:
        return '<div class="empty-state"><p>No context documents.</p></div>'
    _icon_map = {
        "objective": "objective", "architecture": "architecture",
        "conventions": "conventions", "decisions": "folder",
        "documents": "folder",
    }
    items = ""
    for d in docs:
        stem = d["name"].replace(".md", "").lower()
        if d["isDir"]:
            icon_cls = _icon_map.get(stem, "folder")
            icon_svg = _ICON_FOLDER
        else:
            icon_cls = _icon_map.get(stem, "doc")
            icon_svg = _ICON_DOC
        link = f"/project/{alias}/context/{d['name']}" if not d["isDir"] else "#"
        items += f"""<a href="{link}" class="context-item">
  <div class="context-item-icon {icon_cls}">{icon_svg}</div>
  <div>
    <div class="context-item-name">{d['name']}</div>
    <div class="context-item-desc">{d['description']}</div>
  </div>
</a>"""
    return f'<div class="context-list">{items}</div>'


def _repos_page(repos: list[dict], alias: str) -> str:
    if not repos:
        return '<div class="empty-state"><p>No repos registered. Run <code>projhub repo add &lt;path&gt;</code>.</p></div>'
    items = ""
    for r in repos:
        git = r.get("git", {})
        branch = git.get("branch", "—") if git.get("isGit") else "no git"
        dirty = " *" if git.get("dirty") else ""
        items += f"""<div class="context-item">
  <div class="context-item-icon doc">{_ICON_REPO}</div>
  <div style="flex:1">
    <div class="context-item-name">{r['name']}</div>
    <div class="context-item-desc">{r.get('path','')}</div>
  </div>
  <div style="display:flex;gap:6px;align-items:center">
    <span class="chip chip-agent">{branch}{dirty}</span>
    <span class="chip chip-sprint">{r.get('ticketCount',0)} tickets</span>
  </div>
</div>"""
    return f'<div class="context-list">{items}</div>'


def _files_page(alias: str, entries: list[dict]) -> str:
    def render_entries(items: list[dict]) -> str:
        html = ""
        for e in items:
            if e["type"] == "dir":
                badges = "".join(f'<span class="tree-badge" style="color:{b.get("color","var(--text-2)")}">{b["label"]}</span>' for b in e.get("badges", []))
                html += f'<details class="tree-dir"><summary class="tree-row tree-dir-row" data-path="{e["path"]}"><span class="tree-chevron">▶</span><span class="tree-icon">📁</span><span class="tree-name">{e["name"]}</span>{badges}</summary><div class="tree-children tree-lazy" id="children-{e["path"].replace("/","-")}" data-path="{e["path"]}" data-loaded="false" style="display:none"></div></details>'
            else:
                html += f'<div class="tree-row tree-file-row"><span class="tree-icon">📄</span><span class="tree-name tree-file-name" data-path="{e.get("path",e["name"])}">{e["name"]}</span></div>'
        return html
    return f'<div class="file-tree" id="file-tree" data-alias="{alias}">{render_entries(entries)}</div>'


def _render_markdown(body: str) -> str:
    """Minimal markdown renderer for ticket bodies. Handles h1-h3, ul, ol, [ ]/[x], code, bold."""
    import html as _html
    import re
    if not body.strip():
        return '<span class="detail-empty">No description</span>'

    lines = body.splitlines()
    out: list[str] = []
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>"); in_ul = False
        if in_ol:
            out.append("</ol>"); in_ol = False

    def inline(s: str) -> str:
        s = _html.escape(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        return s

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_lists()
            continue
        if m := re.match(r"^### (.+)$", line):
            close_lists(); out.append(f"<h3>{inline(m.group(1))}</h3>"); continue
        if m := re.match(r"^## (.+)$", line):
            close_lists(); out.append(f"<h3>{inline(m.group(1))}</h3>"); continue
        if m := re.match(r"^# (.+)$", line):
            close_lists(); out.append(f'<div class="detail-section-title" style="margin-top:18px">{inline(m.group(1))}</div>'); continue
        if m := re.match(r"^[-*] \[([ xX])\] (.+)$", line):
            close_lists()
            done = m.group(1).lower() == "x"
            check_class = "check done" if done else "check"
            box = "✓" if done else ""
            out.append(f'<div class="{check_class}"><span class="check-box">{box}</span><span>{inline(m.group(2))}</span></div>')
            continue
        if m := re.match(r"^[-*] (.+)$", line):
            if not in_ul:
                close_lists(); out.append("<ul>"); in_ul = True
            out.append(f'<li class="md-li">{inline(m.group(1))}</li>')
            continue
        if m := re.match(r"^\d+\. (.+)$", line):
            if not in_ol:
                close_lists(); out.append("<ol>"); in_ol = True
            out.append(f'<li class="md-li md-ol">{inline(m.group(1))}</li>')
            continue
        close_lists()
        out.append(f"<p>{inline(line)}</p>")
    close_lists()
    return "\n".join(out)


def _ticket_detail_page(ticket: dict, body: str, alias: str) -> str:
    agents = ", ".join(ticket.get("agent") or []) or "—"
    status = ticket.get("status", "backlog")
    status_color = {"doing": "blue", "done": "green", "review": "yellow", "cancelled": "red"}.get(status, "muted")
    prio = ticket.get("priority", "p2")
    sprint = ticket.get("sprint") or "—"
    created = ticket.get("created", "—")
    updated = ticket.get("updated", "—")
    back = f'<a class="back-link" href="/project/{alias}/board"><svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg> Back to Board</a>'
    body_html = _render_markdown(body)
    return f"""{back}
<div class="detail-page">
  <div class="detail-header">
    <div class="detail-header-top">
      <span class="detail-id">{ticket['id']}</span>
      <span class="status-badge {status_color}">{status}</span>
      <span class="p-badge {prio}">{prio}</span>
    </div>
    <div class="detail-title">{ticket['title']}</div>
  </div>
  <div class="detail-grid">
    <div class="detail-main">
      <div class="detail-section">
        <div class="detail-section-title">Description</div>
        <div class="detail-section-body">{body_html}</div>
      </div>
    </div>
    <div class="detail-sidebar">
      <div><div class="detail-field-label">Agent</div><div class="detail-field-value">{agents}</div></div>
      <hr class="detail-divider">
      <div><div class="detail-field-label">Sprint</div><div class="detail-field-value mono">{sprint}</div></div>
      <hr class="detail-divider">
      <div><div class="detail-field-label">Created</div><div class="detail-field-value mono">{created}</div></div>
      <div><div class="detail-field-label">Updated</div><div class="detail-field-value mono">{updated}</div></div>
    </div>
  </div>
</div>"""


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
    return _render(
        f"{ticket_id} — {project['name']}", _ticket_detail_page(ticket, body, alias),
        current_alias=alias, current_tab="board",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Board", "href": f"/project/{alias}/board"}, {"label": ticket_id}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


def _doc_detail_page(title: str, body: str, alias: str, kind: str, meta: dict | None = None) -> str:
    back = f'<a class="back-link" href="/project/{alias}/{kind}"><svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg> Back to {kind.capitalize()}</a>'
    body_html = _render_markdown(body)
    sidebar_html = ""
    if meta:
        rows = "".join(
            f'<div><div class="detail-field-label">{k}</div><div class="detail-field-value mono">{v}</div></div>'
            for k, v in meta.items() if v is not None and v != ""
        )
        if rows:
            sidebar_html = f'<div class="detail-sidebar">{rows}</div>'

    if sidebar_html:
        grid = f'<div class="detail-grid"><div class="detail-main"><div class="detail-section"><div class="detail-section-body">{body_html}</div></div></div>{sidebar_html}</div>'
    else:
        grid = f'<div class="detail-main"><div class="detail-section"><div class="detail-section-body">{body_html}</div></div></div>'

    return f"""{back}
<div class="detail-page">
  <div class="detail-header">
    <div class="detail-title">{title}</div>
  </div>
  {grid}
</div>"""


@app.get("/project/{alias}/agents/{slug}", response_class=HTMLResponse)
def project_agent_detail(alias: str, slug: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    f = Path(project["path"]) / ".projhub" / "agents" / f"{slug}.md"
    if not f.exists():
        return HTMLResponse(_render("Not Found", _not_found_html("Agent not found")), status_code=404)
    fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
    title = fm.get("name", slug)
    meta = {
        "Model": fm.get("model"),
        "Trigger": fm.get("trigger"),
        "Tools": ", ".join(fm.get("tools", [])) if isinstance(fm.get("tools"), list) else fm.get("tools"),
        "Description": fm.get("description"),
    }
    return _render(
        f"{title} — {project['name']}", _doc_detail_page(title, body, alias, "agents", meta),
        current_alias=alias, current_tab="agents",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Agents", "href": f"/project/{alias}/agents"}, {"label": title}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/commands/{slug}", response_class=HTMLResponse)
def project_command_detail(alias: str, slug: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    f = Path(project["path"]) / ".projhub" / "commands" / f"{slug}.md"
    if not f.exists():
        return HTMLResponse(_render("Not Found", _not_found_html("Command not found")), status_code=404)
    fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
    title = f"/{fm.get('name', slug)}"
    meta = {
        "Description": fm.get("description"),
        "Arguments": fm.get("arguments"),
    }
    return _render(
        f"{title} — {project['name']}", _doc_detail_page(title, body, alias, "commands", meta),
        current_alias=alias, current_tab="commands",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Commands", "href": f"/project/{alias}/commands"}, {"label": title}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/context/{filename}", response_class=HTMLResponse)
def project_context_detail(alias: str, filename: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    safe = filename.replace("..", "").lstrip("/\\")
    f = Path(project["path"]) / ".projhub" / "context" / safe
    if not f.exists() or not f.is_file():
        return HTMLResponse(_render("Not Found", _not_found_html("Context document not found")), status_code=404)
    raw = f.read_text(encoding="utf-8")
    if f.suffix == ".md":
        fm, body = parse_frontmatter(raw)
    else:
        fm, body = {}, raw
    title = fm.get("title", f.name)
    meta = {k.capitalize(): v for k, v in fm.items() if k not in ("title",) and v is not None}
    return _render(
        f"{title} — {project['name']}", _doc_detail_page(title, body, alias, "context", meta),
        current_alias=alias, current_tab="context",
        breadcrumbs=[{"label": "projhub", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Context", "href": f"/project/{alias}/context"}, {"label": title}],
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
