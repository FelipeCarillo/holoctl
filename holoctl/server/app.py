from __future__ import annotations
import asyncio
import html
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..lib.config import find_project_root, load_config
from ..lib.board import Board
from ..lib.discover import discover_repos
from ..lib.markdown import parse_frontmatter


def _list_workspace_compat() -> list[dict]:
    """Return a single-element list for the workspace where the server was started.

    Replaces the old global-registry-based `list_workspace()`. The workspace is
    the directory containing `.holoctl/` discovered upwards from cwd.
    """
    root = find_project_root()
    if not root:
        return []
    return [{"path": str(root), "alias": root.name, "added": "", "lastSeen": ""}]

_STATIC_DIR = Path(__file__).parent / "static"


def _e(value) -> str:
    """HTML-escape an arbitrary value before interpolation.

    Anything that came from .holoctl/ (config, ticket frontmatter, agent files,
    context docs) is treated as untrusted text. Without this, a project name or
    ticket title with `<script>` would execute in the dashboard, which matters
    when `holoctl serve --host 0.0.0.0` exposes it on the network.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


app = FastAPI(title="holoctl dashboard", docs_url=None, redoc_url=None)
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
    for p in _list_workspace_compat():
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
                git = r.get("git") or {"isGit": False}
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
        _PROJECTS_CACHE["data"] = result
        _PROJECTS_CACHE["ts"] = now
    return result


def _get_project(alias: str) -> dict | None:
    return next((p for p in _get_projects() if p["alias"] == alias), None)


def _read_agents(project_path: Path) -> list[dict]:
    d = project_path / ".holoctl" / "agents"
    if not d.exists():
        return []
    result = []
    for f in sorted(d.glob("*.md")):
        data, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        result.append({**data, "file": f.name})
    return result


def _read_commands(project_path: Path) -> list[dict]:
    d = project_path / ".holoctl" / "commands"
    if not d.exists():
        return []
    result = []
    for f in sorted(d.glob("*.md")):
        data, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        result.append({**data, "file": f.name})
    return result


def _read_context_docs(project_path: Path) -> list[dict]:
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


# ── layout ───────────────────────────────────────────────────────────────────

def _layout(title: str, body: str, *, sidebar: str = "", topbar: str = "") -> str:
    # Inline script in <head> applies theme + sidebar state BEFORE first paint to
    # avoid the dark→light flash on navigation.
    boot_script = (
        "<script>(function(){try{"
        "var t=localStorage.getItem('holoctl-theme')||'dark';"
        "document.documentElement.setAttribute('data-theme',t);"
        "if(localStorage.getItem('holoctl-sidebar')==='collapsed'){"
        "document.documentElement.setAttribute('data-sidebar','collapsed');"
        "}"
        "}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();</script>"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_e(title)} — holoctl</title>
  {boot_script}
  <link rel="stylesheet" href="/static/holoctl.css">
</head>
<body>
  <div class="app" id="app">
    <aside class="sidebar" id="sidebar">{sidebar}</aside>
    <div class="main">
      <div class="topbar">{topbar}</div>
      <div class="content-wrap">{body}</div>
    </div>
  </div>
  <script src="/static/holoctl-ui.js"></script>
</body>
</html>"""


def _sidebar(projects: list[dict], current_alias: str = "") -> str:
    links = ""
    for p in projects:
        active = "active" if p["alias"] == current_alias else ""
        doing = p.get("counts", {}).get("doing", 0)
        badge = f'<span class="badge">{int(doing)}</span>' if doing > 0 else ""
        initial = (p.get("prefix") or p["name"][:2] or "?")[:2].upper()
        links += (
            f'<a href="/project/{_e(p["alias"])}/board" class="nav-item {active}" title="{_e(p["name"])}">'
            f'<span class="nav-icon">{_e(initial)}</span>'
            f'<span class="nav-item-text">{_e(p["name"])}</span>'
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
  <a href="/" class="sidebar-brand" title="holoctl home">
    <span class="logo">P</span>
    <span class="sidebar-brand-name">holoctl</span>
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
            crumbs += f'<a href="{_e(b["href"])}">{_e(b["label"])}</a><span class="sep">/</span>'
        else:
            crumbs += f'<span>{_e(b["label"])}</span>'
    return f'<div class="topbar-breadcrumb">{crumbs}</div><div class="topbar-actions">{actions}</div>'


def _tabs(tabs: list[dict], current: str, base: str) -> str:
    out = '<div class="tabs">'
    for t in tabs:
        active = "active" if t["id"] == current else ""
        out += f'<a href="{_e(base)}/{_e(t["id"])}" class="tab {active}">{_e(t["label"])}</a>'
    out += "</div>"
    return out


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
    # Inner `.content-body` is the scroll container. CSS picks the right
    # behavior per page: vertical-scroll for grids/lists, flex-column with
    # internal kanban scroll on the board.
    return _layout(
        title,
        tabs_html + f'<div class="content"><div class="content-body">{content}</div></div>',
        sidebar=sidebar, topbar=topbar,
    )


def _not_found_html(msg: str = "Not found") -> str:
    return f'<div class="empty-state"><h3>{_e(msg)}</h3></div>'


# ── page generators ───────────────────────────────────────────────────────────

def _home_page(projects: list[dict]) -> str:
    if not projects:
        return '<div class="empty-state"><h3>No projects yet</h3><p>Run <code>holoctl init</code> in a directory to get started.</p></div>'
    cards = ""
    for p in projects:
        counts = p.get("counts", {})
        doing = int(counts.get("doing", 0))
        backlog = int(counts.get("backlog", 0))
        done = int(counts.get("done", 0))
        total = max(int(p.get("ticketCount", 0)), 1)
        prefix = p.get("prefix", "")
        targets = "".join(f'<span class="chip chip-target">{_e(t)}</span>' for t in p.get("targets", []))
        progress = f"""<div class="progress-bar">
  <div class="progress-segment done" style="width:{done/total*100:.0f}%"></div>
  <div class="progress-segment doing" style="width:{doing/total*100:.0f}%"></div>
  <div class="progress-segment backlog" style="width:{backlog/total*100:.0f}%"></div>
</div>"""
        cards += f"""<a href="/project/{_e(p['alias'])}/board" class="project-card">
  <div class="project-card-header">
    <div class="project-card-icon">{_e(prefix[:2])}</div>
    <div>
      <div class="project-card-name">{_e(p['name'])}</div>
      <div class="project-card-sub">{_e(p['alias'])}</div>
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


_AVATAR_HUE_COUNT = 6


def _initials(name: str) -> str:
    """Two-character uppercase glyph for an avatar circle."""
    if not name:
        return "?"
    parts = re.split(r"[\s\-_./]+", name.strip())
    parts = [p for p in parts if p]
    if not parts:
        return name.strip()[:2].upper()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[1][:1]).upper()


def _avatar_hue(name: str) -> int:
    """Deterministic 0..5 hue index — same name always lands the same color."""
    if not name:
        return 0
    return sum(ord(c) for c in name) % _AVATAR_HUE_COUNT


def _ticket_preview(project_root: Path, ticket: dict, max_chars: int = 80) -> str:
    """First non-trivial prose line from a ticket .md, for the kanban card preview.

    Strips frontmatter, drops empty/placeholder sections, then walks the body
    looking for the first line that isn't a header, blank, list marker, or
    HTML comment. Returns "" gracefully when the ticket body is template-only.
    """
    rel = ticket.get("file")
    if not rel:
        return ""
    md_path = project_root / ".holoctl" / "board" / "tickets" / rel if not (project_root / rel).exists() else (project_root / rel)
    if not md_path.exists():
        return ""
    try:
        raw = md_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    _, body = parse_frontmatter(raw)
    body = _strip_empty_sections(body)
    in_html_comment = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Multi-line HTML comments — skip until close.
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue
        if line.startswith("<!--"):
            if "-->" not in line:
                in_html_comment = True
            continue
        # Markdown structural lines.
        if line.startswith("#") or line.startswith("---"):
            continue
        # List / checkbox markers — skip the marker but keep substantive text.
        m = re.match(r"^(?:[-*+]\s*(?:\[[ xX]\]\s+)?|\d+\.\s+)(.*)$", line)
        if m:
            line = m.group(1).strip()
            if not line:
                continue
        # Skip parenthetical placeholder hints.
        if re.match(r"^\([^)]*\)\s*$", line):
            continue
        # Strip basic markdown emphasis / inline code for the preview.
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        if len(line) > max_chars:
            line = line[: max_chars - 1].rstrip() + "…"
        return line
    return ""


def _format_due(due_iso: str) -> str:
    """Short due-date label like 'May 9' for ISO dates; empty if unparseable."""
    if not due_iso:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(due_iso))
    if not m:
        return ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        mo = int(m.group(2))
        day = int(m.group(3))
        return f"{months[mo - 1]} {day}"
    except (ValueError, IndexError):
        return ""


def _kanban_html(tickets: list[dict], statuses: list[str], alias: str,
                 project_root: Path | None = None) -> str:
    """Build the `<div class="kanban">` block. Used by both the full board page
    and the `/api/.../board-html` fragment endpoint that the SSE client swaps
    in on each `board-update` event.

    Cards carry a full set of `data-*` attributes so the client-side
    filter / sort / group-by controls can rework the layout without a
    server round-trip.
    """
    cols = ""
    for status in statuses:
        col_tickets = [t for t in tickets if t["status"] == status]
        cards = ""
        for t in col_tickets:
            agents_list = [a for a in (t.get("agent") or []) if a]
            agents_csv = ",".join(agents_list)
            prio = t.get("priority", "p2")
            sprint = t.get("sprint") or ""
            tags_csv = ",".join(t.get("tags") or [])
            projects_csv = ",".join(t.get("projects") or [])
            preview = _ticket_preview(project_root, t) if project_root else ""
            due = _format_due(t.get("due") or "")
            data_attrs = (
                f'data-id="{_e(t["id"])}"'
                f' data-status="{_e(status)}"'
                f' data-p="{_e(prio)}"'
                f' data-agent="{_e(agents_csv)}"'
                f' data-sprint="{_e(sprint)}"'
                f' data-tags="{_e(tags_csv)}"'
                f' data-projects="{_e(projects_csv)}"'
                f' data-title="{_e(t.get("title", ""))}"'
                f' data-created="{_e(t.get("created", ""))}"'
                f' data-updated="{_e(t.get("updated", ""))}"'
            )
            avatars_html = ""
            if agents_list:
                avs = "".join(
                    f'<span class="avatar-initials" data-hue="{_avatar_hue(a)}" '
                    f'title="{_e(a)}">{_e(_initials(a))}</span>'
                    for a in agents_list
                )
                avatars_html = f'<span class="avatar-stack">{avs}</span>'
            sprint_html = f'<span class="kc-sprint">#{_e(sprint)}</span>' if sprint else ""
            due_html = f'<span class="kc-due">⏱ {_e(due)}</span>' if due else ""
            preview_html = f'<div class="kc-preview">{_e(preview)}</div>' if preview else ""
            meta_inner = avatars_html + sprint_html + due_html
            meta_html = f'<div class="kc-meta">{meta_inner}</div>' if meta_inner else ""
            cards += f"""<a href="/project/{_e(alias)}/board/{_e(t['id'])}" class="kanban-card" {data_attrs}>
  <div class="kc-top">
    <span class="kc-prio-dot" data-p="{_e(prio)}" title="priority {_e(prio)}"></span>
    <span class="kc-id">{_e(t['id'])}</span>
  </div>
  <div class="kc-title">{_e(t['title'])}</div>
  {preview_html}
  {meta_html}
</a>"""
        if not cards:
            cards = ('<div class="kanban-empty">'
                     '<div class="kanban-empty-glyph">·</div>'
                     '<div class="kanban-empty-msg">No tickets here</div>'
                     '</div>')
        cols += f"""<div class="kanban-col" data-status="{_e(status)}" data-bucket="{_e(status)}">
  <div class="kanban-col-header">
    <span class="col-label">{_e(status)}</span>
    <span class="count">{len(col_tickets)}</span>
  </div>
  <div class="kanban-cards">{cards}</div>
</div>"""
    return f'<div class="kanban" id="kanban">{cols}</div>'


def _board_page(project: dict, tickets: list[dict], config: dict) -> str:
    """Board page body: header (h1 + path + CTA) → controls → kanban.

    The LIVE indicator is no longer here — it lives in the topbar so the
    board area stays focused on the work itself.
    """
    alias = project["alias"]
    name = project.get("name") or alias
    path_display = project.get("path", "")
    project_root = Path(path_display) if path_display else None
    header = f"""<div class="board-header">
  <div class="board-header-text">
    <h1 class="board-title">{_e(name)}</h1>
    <div class="board-path">{_e(path_display)}</div>
  </div>
  <div class="board-header-actions">
    <a class="btn btn-primary btn-disabled" href="#" title="Coming soon — for now: holoctl board add '{{\"title\":\"...\"}}'" aria-disabled="true">+ New ticket</a>
  </div>
</div>"""
    return header + _board_controls_html() + _kanban_html(
        tickets, config["board"]["statuses"], alias, project_root=project_root,
    )


def _board_controls_html() -> str:
    """Compact controls strip: view switcher, search, filter chips, sort, group.

    Replaces the old expand/collapse panel with 6 always-visible dropdowns.
    Active filters render as chips; new filters added via the [+ Add filter]
    popover. Sort and Group are dropdowns to the right. State persists per
    workspace under `holoctl-bc-v2:{alias}` in localStorage.
    """
    sort_opts = [
        ("created", "Created · old → new"),
        ("created-desc", "Created · new → old"),
        ("updated-desc", "Updated · recent first"),
        ("priority", "Priority · p0 → p3"),
        ("title", "Title · A → Z"),
        ("id", "ID · numeric"),
    ]
    group_opts = [
        ("status", "Status"),
        ("priority", "Priority"),
        ("sprint", "Sprint"),
        ("agent", "Agent"),
        ("tag", "Tag"),
    ]
    sort_options_html = "".join(f'<option value="{_e(v)}">{_e(label)}</option>' for v, label in sort_opts)
    group_options_html = "".join(f'<option value="{_e(v)}">{_e(label)}</option>' for v, label in group_opts)
    return f"""<div class="board-controls" id="board-controls">
  <div class="bc-row bc-row-primary">
    <div class="view-switcher" role="tablist" aria-label="Board view">
      <button class="view-tab active" data-view="kanban" role="tab" aria-selected="true">
        <span class="view-tab-glyph">▦</span> Kanban
      </button>
      <button class="view-tab" data-view="list" role="tab" aria-selected="false" disabled title="Coming in Phase 2">
        <span class="view-tab-glyph">☰</span> List
      </button>
      <button class="view-tab" data-view="timeline" role="tab" aria-selected="false" disabled title="Coming in Phase 3">
        <span class="view-tab-glyph">⤳</span> Timeline
      </button>
    </div>
    <div class="bc-search">
      <span class="bc-search-glyph" aria-hidden="true">🔍</span>
      <input type="search" id="bc-search" placeholder="Search tickets…" autocomplete="off" spellcheck="false">
    </div>
  </div>
  <div class="bc-row bc-row-secondary">
    <div class="bc-chips" id="bc-chips" aria-label="Active filters"></div>
    <button class="bc-add-filter" id="bc-add-filter" aria-haspopup="dialog" aria-expanded="false">
      <span class="bc-add-filter-glyph">+</span> Add filter
    </button>
    <div class="bc-spacer"></div>
    <label class="bc-inline-select">
      <span>Sort</span>
      <select id="bc-sort" data-sort>{sort_options_html}</select>
    </label>
    <label class="bc-inline-select">
      <span>Group</span>
      <select id="bc-group" data-group>{group_options_html}</select>
    </label>
    <button class="bc-reset" id="bc-reset" data-bc-reset title="Reset filters / sort / group">↺</button>
  </div>
  <div class="bc-popover" id="bc-popover" hidden role="dialog" aria-label="Add filter">
    <div class="bc-popover-step" data-step="axis">
      <div class="bc-popover-title">Filter by</div>
      <div class="bc-popover-axes">
        <button class="bc-popover-axis" data-axis="status">Status</button>
        <button class="bc-popover-axis" data-axis="priority">Priority</button>
        <button class="bc-popover-axis" data-axis="agent">Agent</button>
        <button class="bc-popover-axis" data-axis="sprint">Sprint</button>
        <button class="bc-popover-axis" data-axis="tag">Tag</button>
        <button class="bc-popover-axis" data-axis="project">Project</button>
      </div>
    </div>
    <div class="bc-popover-step" data-step="value" hidden>
      <div class="bc-popover-title">
        <button class="bc-popover-back" id="bc-popover-back" aria-label="Back to axis selection">‹</button>
        <span id="bc-popover-axis-label">Filter by</span>
      </div>
      <div class="bc-popover-values" id="bc-popover-values"></div>
    </div>
  </div>
</div>"""


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
        tool_chips = "".join(f'<span class="tool-chip">{_e(t)}</span>' for t in tools)
        link = f"/project/{_e(alias)}/agents/{_e(a.get('file','').replace('.md',''))}" if alias else "#"
        cards += f"""<a href="{link}" class="agent-card">
  <div class="agent-card-header">
    <span class="agent-card-name">{_e(name)}</span>
    <span class="trigger-badge">{_e(trigger)}</span>
    <span class="model-badge {_e(model)}">{_e(model)}</span>
  </div>
  <div class="agent-card-desc">{_e(desc)}</div>
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
        link = f"/project/{_e(alias)}/commands/{_e(c.get('file','').replace('.md',''))}"
        items += f"""<a href="{link}" class="context-item">
  <div class="context-item-icon command">{_ICON_CMD}</div>
  <div>
    <div class="context-item-name">/{_e(name)}</div>
    <div class="context-item-desc">{_e(desc)}</div>
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
        link = f"/project/{_e(alias)}/context/{_e(d['name'])}" if not d["isDir"] else "#"
        items += f"""<a href="{link}" class="context-item">
  <div class="context-item-icon {icon_cls}">{icon_svg}</div>
  <div>
    <div class="context-item-name">{_e(d['name'])}</div>
    <div class="context-item-desc">{_e(d['description'])}</div>
  </div>
</a>"""
    return f'<div class="context-list">{items}</div>'


def _repos_page(repos: list[dict], alias: str) -> str:
    if not repos:
        return '<div class="empty-state"><p>No repos registered. Run <code>holoctl repo add &lt;path&gt;</code>.</p></div>'
    items = ""
    for r in repos:
        git = r.get("git", {})
        branch = git.get("branch", "—") if git.get("isGit") else "no git"
        dirty = " *" if git.get("dirty") else ""
        items += f"""<div class="context-item">
  <div class="context-item-icon doc">{_ICON_REPO}</div>
  <div style="flex:1">
    <div class="context-item-name">{_e(r['name'])}</div>
    <div class="context-item-desc">{_e(r.get('path',''))}</div>
  </div>
  <div style="display:flex;gap:6px;align-items:center">
    <span class="chip chip-agent">{_e(branch)}{dirty}</span>
    <span class="chip chip-sprint">{int(r.get('ticketCount',0))} tickets</span>
  </div>
</div>"""
    return f'<div class="context-list">{items}</div>'


_PLACEHOLDER_PATTERNS = (
    re.compile(r"^\([^)]*\)\s*$"),                        # `(some hint)`
    re.compile(r"^[-*]\s*\[\s*[xX ]?\s*\]\s+\([^)]*\)\s*$"),  # `- [ ] (criteria)`
    re.compile(r"^<!--.*-->\s*$"),                         # `<!-- HTML comment hint -->`
)


def _strip_empty_sections(body: str) -> str:
    """Remove ticket body sections whose content is blank or only placeholders.

    A section is `# Header` followed by content until the next `# `. If every
    non-blank line in the content matches a placeholder pattern (parenthetical
    hint, checklist item with parenthetical content, or HTML comment), the
    whole section is dropped before rendering. Keeps the dashboard tidy when
    agents leave the template defaults in place instead of filling them in.
    """
    parts = re.split(r"^(# .+)$", body, flags=re.MULTILINE)
    if len(parts) <= 1:
        return body
    out = [parts[0]]
    i = 1
    while i < len(parts):
        header = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""
        if not _is_placeholder_only(content):
            out.append(header)
            out.append(content)
        i += 2
    return "".join(out)


def _is_placeholder_only(content: str) -> bool:
    lines = [l.rstrip() for l in content.splitlines()]
    real = [l for l in lines if l.strip()]
    if not real:
        return True
    for line in real:
        stripped = line.strip()
        if any(p.match(stripped) for p in _PLACEHOLDER_PATTERNS):
            continue
        return False
    return True


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
    back = f'<a class="back-link" href="/project/{_e(alias)}/board"><svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg> Back to Board</a>'
    body_html = _render_markdown(_strip_empty_sections(body))
    return f"""{back}
<div class="detail-page">
  <div class="detail-header">
    <div class="detail-header-top">
      <span class="detail-id">{_e(ticket['id'])}</span>
      <span class="status-badge {_e(status_color)}">{_e(status)}</span>
      <span class="p-badge {_e(prio)}">{_e(prio)}</span>
    </div>
    <div class="detail-title">{_e(ticket['title'])}</div>
  </div>
  <div class="detail-grid">
    <div class="detail-main">
      <div class="detail-section">
        <div class="detail-section-title">Description</div>
        <div class="detail-section-body">{body_html}</div>
      </div>
    </div>
    <div class="detail-sidebar">
      <div><div class="detail-field-label">Agent</div><div class="detail-field-value">{_e(agents)}</div></div>
      <hr class="detail-divider">
      <div><div class="detail-field-label">Sprint</div><div class="detail-field-value mono">{_e(sprint)}</div></div>
      <hr class="detail-divider">
      <div><div class="detail-field-label">Created</div><div class="detail-field-value mono">{_e(created)}</div></div>
      <div><div class="detail-field-label">Updated</div><div class="detail-field-value mono">{_e(updated)}</div></div>
    </div>
  </div>
</div>"""


# ── routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home():
    projects = _get_projects()
    return _render("Home", _home_page(projects), projects=projects,
                   breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": "Home"}])


@app.get("/project/{alias}/board", response_class=HTMLResponse)
def project_board(alias: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    board = Board(Path(project["path"]), project["config"])
    tickets = board.ls()
    # LIVE indicator now lives in the topbar — frees the board header for
    # the project title + path + primary CTA.
    live_action = '<span class="live-indicator"><span class="pulse"></span>LIVE</span>'
    return _render(
        project["name"], _board_page(project, tickets, project["config"]),
        current_alias=alias, current_tab="board",
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Board"}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
        actions=live_action,
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
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Agents"}],
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
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Commands"}],
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
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Context"}],
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
    ticket_file = Path(project["path"]) / ".holoctl" / "board" / ticket["file"]
    _, body = parse_frontmatter(ticket_file.read_text(encoding="utf-8")) if ticket_file.exists() else ({}, "")
    return _render(
        f"{ticket_id} — {project['name']}", _ticket_detail_page(ticket, body, alias),
        current_alias=alias, current_tab="board",
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Board", "href": f"/project/{alias}/board"}, {"label": ticket_id}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


def _doc_detail_page(title: str, body: str, alias: str, kind: str, meta: dict | None = None) -> str:
    back = f'<a class="back-link" href="/project/{_e(alias)}/{_e(kind)}"><svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg> Back to {_e(kind.capitalize())}</a>'
    body_html = _render_markdown(_strip_empty_sections(body))
    sidebar_html = ""
    if meta:
        rows = "".join(
            f'<div><div class="detail-field-label">{_e(k)}</div><div class="detail-field-value mono">{_e(v)}</div></div>'
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
    <div class="detail-title">{_e(title)}</div>
  </div>
  {grid}
</div>"""


@app.get("/project/{alias}/agents/{slug}", response_class=HTMLResponse)
def project_agent_detail(alias: str, slug: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    agents_root = (Path(project["path"]) / ".holoctl" / "agents").resolve()
    f = (agents_root / f"{slug}.md").resolve()
    try:
        f.relative_to(agents_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden")
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
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Agents", "href": f"/project/{alias}/agents"}, {"label": title}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/commands/{slug}", response_class=HTMLResponse)
def project_command_detail(alias: str, slug: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    commands_root = (Path(project["path"]) / ".holoctl" / "commands").resolve()
    f = (commands_root / f"{slug}.md").resolve()
    try:
        f.relative_to(commands_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden")
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
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Commands", "href": f"/project/{alias}/commands"}, {"label": title}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/context/{filename}", response_class=HTMLResponse)
def project_context_detail(alias: str, filename: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    context_root = (Path(project["path"]) / ".holoctl" / "context").resolve()
    f = (context_root / filename).resolve()
    try:
        f.relative_to(context_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden")
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
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Context", "href": f"/project/{alias}/context"}, {"label": title}],
        tabs=_PROJECT_TABS, tab_base=f"/project/{alias}",
    )


@app.get("/project/{alias}/repos", response_class=HTMLResponse)
def project_repos(alias: str):
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_render("Not Found", _not_found_html()), status_code=404)
    # Dirty-flag fetching is opt-in via config.git.checkDirty (default false).
    # When off, this route still works — it just won't show the dirty asterisk.
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
        r["ticketCount"] = sum(1 for t in all_tickets if r["name"] in (t.get("projects") or []))
    return _render(
        project["name"], _repos_page(repos, alias),
        current_alias=alias, current_tab="repos",
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": project["name"], "href": f"/project/{alias}/board"}, {"label": "Repos"}],
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
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": "Agent Registry"}],
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
    index_path = Path(project["path"]) / ".holoctl" / "board" / "index.json"
    if index_path.exists():
        return json.loads(index_path.read_text(encoding="utf-8"))
    return {"meta": {}, "tickets": []}


@app.get("/api/project/{alias}/board-html", response_class=HTMLResponse)
def api_board_html(alias: str):
    """Return just the `<div class="kanban">` fragment.

    The dashboard's SSE client swaps this into the page on every
    `board-update` event, so tickets appear/move/disappear without a
    full reload.
    """
    project = _get_project(alias)
    if not project:
        return HTMLResponse(_not_found_html("Project not found"), status_code=404)
    project_root = Path(project["path"])
    board = Board(project_root, project["config"])
    tickets = board.ls()
    return HTMLResponse(_kanban_html(
        tickets, project["config"]["board"]["statuses"], alias,
        project_root=project_root,
    ))


@app.get("/api/project/{alias}/events")
async def api_events(alias: str):
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Not found")

    index_path = Path(project["path"]) / ".holoctl" / "board" / "index.json"

    async def event_stream():
        last_mtime = None
        while True:
            try:
                if index_path.exists():
                    mtime = index_path.stat().st_mtime
                    if mtime != last_mtime:
                        last_mtime = mtime
                        # The on-disk index.json is pretty-printed (indent="\t"),
                        # but the SSE protocol treats every newline inside the
                        # `data:` field as a record terminator — the browser
                        # would only see "{" before the first newline. Compact
                        # it onto a single line so e.data is the full JSON.
                        raw = index_path.read_text(encoding="utf-8")
                        try:
                            data = json.dumps(json.loads(raw), separators=(",", ":"))
                        except (json.JSONDecodeError, ValueError):
                            data = raw.replace("\n", " ").replace("\r", "")
                        yield f"event: board-update\ndata: {data}\n\n"
            except Exception:
                pass
            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
