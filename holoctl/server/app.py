from __future__ import annotations
import asyncio
import html
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..lib.config import find_project_root, load_config
from ..lib.board import Board
from ..lib.discover import discover_repos
from ..lib.markdown import parse_frontmatter
from .jinja import render as _jinja_render
from .views.avatars import initials as _initials, avatar_hue as _avatar_hue
from .views.dates import format_relative_date as _format_relative_date


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

# Modular routers. Each lives under server/routes/. New views land here as
# they migrate from string-built helpers below to Jinja templates.
from .routes.home import router as _home_router  # noqa: E402
from .routes.project_board import router as _project_board_router  # noqa: E402
from .routes.project_detail import router as _project_detail_router  # noqa: E402
from .routes.project_doc import router as _project_doc_router  # noqa: E402
from .routes.project_meta import router as _project_meta_router  # noqa: E402
app.include_router(_home_router)
app.include_router(_project_board_router)
app.include_router(_project_detail_router)
app.include_router(_project_doc_router)
app.include_router(_project_meta_router)

# Re-export shim: these names are still referenced by the string-building
# helpers below (_kanban_html, _list_html etc.) which get deleted in a
# later task. Import from their new canonical home so the names resolve.
from .views.card import format_due as _format_due, ticket_preview as _ticket_preview  # noqa: E402

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
#
# The shell (doctype, sidebar, topbar, tabs, content wrapper) lives in Jinja2
# templates under `server/templates/`. Python here only wires data into them.
# Page bodies are still string-built by `_xxx_html()` helpers and passed as
# `content=` for now; each view migrates to its own template in later PRs.

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
    return _jinja_render(
        "base.html",
        title=title,
        content=content,
        projects=projects if projects is not None else _get_projects(),
        current_alias=current_alias,
        current_tab=current_tab,
        breadcrumbs=breadcrumbs or [],
        tabs=tabs,
        tab_base=tab_base,
        actions=actions,
    )


def _not_found_html(msg: str = "Not found") -> str:
    return _jinja_render("partials/_empty_state.html", msg=msg)


# ── page generators ───────────────────────────────────────────────────────────

def _repo_chip_html(projects_list: list[str]) -> str:
    """Compact repo / project pill for the card top row.

    Surfaces *which* repo a ticket belongs to without dragging a multi-line
    list onto the card. Shows the first project name and `+N` if more.
    Returns "" when the ticket has no `projects` (so the card stays clean
    for tickets that aren't repo-scoped).
    """
    projects_list = [p for p in projects_list if p]
    if not projects_list:
        return ""
    head = projects_list[0]
    extra = f' <span class="kc-repo-extra">+{len(projects_list) - 1}</span>' if len(projects_list) > 1 else ""
    title = ", ".join(projects_list)
    return (f'<span class="kc-repo" title="repo: {_e(title)}">'
            f'<span class="kc-repo-glyph" aria-hidden="true">▸</span>'
            f'{_e(head)}{extra}</span>')


def _deps_chip_html(depends_list: list[str], alias: str) -> str:
    """Inline `↳ HOL-001 +N` indicator linking to the first dependency.

    Surfaces "this ticket is blocked by …" on the card without clicking
    through to the detail page. The linked target uses preventDefault on
    cards so navigation still goes to the parent card link unless the
    user middle-clicks the dep itself; we keep it as plain text inside
    the card to avoid that subtlety.
    """
    depends_list = [d for d in depends_list if d]
    if not depends_list:
        return ""
    head = depends_list[0]
    extra = f' <span class="kc-deps-extra">+{len(depends_list) - 1}</span>' if len(depends_list) > 1 else ""
    title = ", ".join(depends_list)
    return (f'<span class="kc-deps" title="depends on: {_e(title)}">'
            f'<span class="kc-deps-glyph" aria-hidden="true">↳</span>'
            f'{_e(head)}{extra}</span>')


# v0.16 introduced `kind` (task|story|bug|spec|epic|rfc|incident|custom) as a
# first-class field on every ticket. The CLI surfaces it; the board UI used to
# treat every card the same. The chip below puts the kind back on the card so
# specs/epics/bugs stand out visually, while plain `task` (the default for the
# majority of tickets) stays glyph-less to keep the card uncluttered.
_KIND_GLYPHS = {
    "spec":     "◆",
    "epic":     "◇",
    "story":    "◉",
    "bug":      "●",
    "rfc":      "✎",
    "incident": "⚠",
}


def _kind_chip_html(kind: str) -> str:
    """Small chip on the card top row identifying the work-item kind.

    `task` is the default and renders blank (no chip) so the typical card
    is unchanged. Specs/epics/bugs/rfc/incident get a colored glyph + name
    (the CSS uses `[data-kind="…"]` selectors to pick the hue). An unknown
    kind (config-defined custom string) falls back to a neutral square.
    """
    if not kind or kind == "task":
        return ""
    glyph = _KIND_GLYPHS.get(kind, "◾")
    return (f'<span class="kc-kind" data-kind="{_e(kind)}" '
            f'title="kind: {_e(kind)}">'
            f'<span class="kc-kind-glyph" aria-hidden="true">{glyph}</span>'
            f'{_e(kind)}</span>')


# Maps a provider id (config catalog: linear, github, trello, jira, azure,
# slack, plus any internal board the user registers via `hctl provider add`)
# to a short visual marker on the card. Falls back to ↗ when unknown so a
# custom provider still shows up as "external origin".
_PROVIDER_GLYPHS = {
    "linear": "L",
    "github": "GH",
    "trello": "T",
    "jira":   "J",
    "azure":  "AZ",
    "slack":  "S",
}


def _source_chip_html(provider: str | None, url: str | None,
                      ref: str | None, label: str | None) -> str:
    """Card chip pointing at the external board this ticket came from.

    Renders e.g. `L · ENG-42` for a Linear ticket, `GH · 1234` for a
    GitHub issue. Always a `<span>` (never `<a>`) inside the kanban-card
    link wrapper — the clickable external URL lives on the detail page
    Properties panel to keep card navigation unambiguous. Empty when the
    ticket has no `source_*` metadata.
    """
    if not (provider or url or ref or label):
        return ""
    glyph = _PROVIDER_GLYPHS.get((provider or "").lower(), "↗")
    body = _e(ref or label or provider or "ext")
    tip = " · ".join(b for b in (label, provider, ref, url) if b)
    return (f'<span class="kc-source" data-provider="{_e((provider or "").lower())}" '
            f'title="from {_e(tip)}">'
            f'<span class="kc-source-glyph" aria-hidden="true">{_e(glyph)}</span>'
            f'<span class="kc-source-ref">{body}</span></span>')


def _parent_chip_html(parent_id: str | None) -> str:
    """Subtle '↑ PRJ-099' indicator in the card meta row when this ticket
    belongs to a parent spec/epic. Visual cousin of the deps chip — same
    weight, opposite arrow direction (parents are above; deps block).
    """
    if not parent_id:
        return ""
    return (f'<span class="kc-parent" title="parent: {_e(parent_id)}">'
            f'<span class="kc-parent-glyph" aria-hidden="true">↑</span>'
            f'{_e(parent_id)}</span>')


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
            projects_list = [p for p in (t.get("projects") or []) if p]
            projects_csv = ",".join(projects_list)
            depends_list = [d for d in (t.get("depends") or []) if d]
            depends_csv = ",".join(depends_list)
            kind = t.get("kind") or "task"
            parent = t.get("parent") or ""
            src_provider = t.get("source_provider") or ""
            src_ref = t.get("source_ref") or ""
            src_url = t.get("source_url") or ""
            src_label = t.get("source_label") or ""
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
                f' data-depends="{_e(depends_csv)}"'
                f' data-kind="{_e(kind)}"'
                f' data-parent="{_e(parent)}"'
                f' data-source="{_e(src_provider)}"'
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
            repo_html = _repo_chip_html(projects_list)
            deps_html = _deps_chip_html(depends_list, alias)
            kind_html = _kind_chip_html(kind)
            source_html = _source_chip_html(src_provider, src_url, src_ref, src_label)
            parent_html = _parent_chip_html(parent)
            preview_html = f'<div class="kc-preview">{_e(preview)}</div>' if preview else ""
            meta_inner = avatars_html + sprint_html + parent_html + deps_html + due_html
            meta_html = f'<div class="kc-meta">{meta_inner}</div>' if meta_inner else ""
            cards += f"""<a href="/project/{_e(alias)}/board/{_e(t['id'])}" class="kanban-card" {data_attrs}>
  <div class="kc-top">
    <span class="kc-prio-dot" data-p="{_e(prio)}" title="priority {_e(prio)}"></span>
    {kind_html}
    <span class="kc-id">{_e(t['id'])}</span>
    {repo_html}
    {source_html}
    <button type="button" class="kc-menu" data-card-menu aria-label="Card actions" title="Actions">⋯</button>
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
        # Inline "Add ticket" ghost at the bottom of each column. Toggles a
        # title-only form that POSTs to /api/.../tickets and lets SSE swap
        # in the new state.
        add_html = (
            f'<button type="button" class="kanban-col-add" '
            f'data-add-ticket data-status="{_e(status)}" aria-expanded="false">'
            f'<span class="kanban-col-add-glyph">+</span> Add ticket</button>'
        )
        cols += f"""<div class="kanban-col" data-status="{_e(status)}" data-bucket="{_e(status)}">
  <div class="kanban-col-header">
    <span class="col-label">{_e(status)}</span>
    <span class="count">{len(col_tickets)}</span>
  </div>
  <div class="kanban-cards">{cards}</div>
  {add_html}
</div>"""
    return f'<div class="kanban" id="kanban">{cols}</div>'


_VALID_VIEWS = {"kanban", "list", "tree"}


def _list_row_html(t: dict, alias: str) -> str:
    """One <a class="ticket-row kanban-card"> row.

    Carries the same `data-*` attributes as kanban cards so the existing
    filter / search / sort logic (which selects `.kanban-card`) applies in
    both views without branching.
    """
    agents_list = [a for a in (t.get("agent") or []) if a]
    agents_csv = ",".join(agents_list)
    prio = t.get("priority", "p2")
    sprint = t.get("sprint") or ""
    status = t.get("status", "backlog")
    tags_csv = ",".join(t.get("tags") or [])
    projects_list = [p for p in (t.get("projects") or []) if p]
    projects_csv = ",".join(projects_list)
    depends_list = [d for d in (t.get("depends") or []) if d]
    depends_csv = ",".join(depends_list)
    kind = t.get("kind") or "task"
    parent = t.get("parent") or ""
    src_provider = t.get("source_provider") or ""
    upd_disp, upd_full = _format_relative_date(t.get("updated", ""))
    avatars_html = ""
    if agents_list:
        avs = "".join(
            f'<span class="avatar-initials" data-hue="{_avatar_hue(a)}" '
            f'title="{_e(a)}">{_e(_initials(a))}</span>'
            for a in agents_list
        )
        avatars_html = f'<span class="avatar-stack">{avs}</span>'
    sprint_html = f'<span class="lr-sprint">#{_e(sprint)}</span>' if sprint else '<span class="lr-empty">—</span>'
    repo_html = _repo_chip_html(projects_list) or '<span class="lr-empty">—</span>'
    deps_html = _deps_chip_html(depends_list, alias) or '<span class="lr-empty">—</span>'
    # Kind + parent ride inline with the title cell — same row as the title
    # link so the eye picks them up without adding new columns. Plain `task`
    # stays glyph-less; specs/epics/bugs/etc. get a colored marker.
    kind_html = _kind_chip_html(kind)
    parent_html = _parent_chip_html(parent)
    title_prefix = ""
    if kind_html:
        title_prefix += kind_html
    if parent_html:
        title_prefix += parent_html
    data_attrs = (
        f'data-id="{_e(t["id"])}"'
        f' data-status="{_e(status)}"'
        f' data-p="{_e(prio)}"'
        f' data-agent="{_e(agents_csv)}"'
        f' data-sprint="{_e(sprint)}"'
        f' data-tags="{_e(tags_csv)}"'
        f' data-projects="{_e(projects_csv)}"'
        f' data-depends="{_e(depends_csv)}"'
        f' data-kind="{_e(kind)}"'
        f' data-parent="{_e(parent)}"'
        f' data-source="{_e(src_provider)}"'
        f' data-title="{_e(t.get("title", ""))}"'
        f' data-created="{_e(t.get("created", ""))}"'
        f' data-updated="{_e(t.get("updated", ""))}"'
    )
    return f"""<div class="ticket-row kanban-card" {data_attrs}>
  <div class="lr-cell lr-cell-select">
    <input type="checkbox" class="lr-checkbox" data-ticket-select aria-label="Select {_e(t['id'])}">
  </div>
  <div class="lr-cell lr-cell-prio">
    <span class="kc-prio-dot" data-p="{_e(prio)}" title="priority {_e(prio)}"></span>
  </div>
  <div class="lr-cell lr-cell-id">
    <a class="lr-id-link" href="/project/{_e(alias)}/board/{_e(t['id'])}">{_e(t['id'])}</a>
  </div>
  <div class="lr-cell lr-cell-title">
    {title_prefix}<a class="lr-title-link" href="/project/{_e(alias)}/board/{_e(t['id'])}">{_e(t.get('title', ''))}</a>
  </div>
  <div class="lr-cell lr-cell-status">
    <button type="button" class="lr-edit lr-status" data-edit-field="status" data-status="{_e(status)}" aria-haspopup="listbox" aria-expanded="false">{_e(status)}</button>
  </div>
  <div class="lr-cell lr-cell-prio-pill">
    <button type="button" class="lr-edit lr-prio-pill" data-edit-field="priority" data-p="{_e(prio)}" aria-haspopup="listbox" aria-expanded="false">{_e(prio)}</button>
  </div>
  <div class="lr-cell lr-cell-agents">{avatars_html or '<span class="lr-empty">—</span>'}</div>
  <div class="lr-cell lr-cell-sprint">{sprint_html}</div>
  <div class="lr-cell lr-cell-repo">{repo_html}</div>
  <div class="lr-cell lr-cell-deps">{deps_html}</div>
  <div class="lr-cell lr-cell-updated" title="{_e(upd_full)}">{_e(upd_disp)}</div>
  <div class="lr-cell lr-cell-menu">
    <button type="button" class="kc-menu" data-card-menu aria-label="Row actions" title="Actions">⋯</button>
  </div>
</div>"""


def _list_html(tickets: list[dict], statuses: list[str], alias: str) -> str:
    """Dense table view of all tickets, grouped by status.

    Header row is sticky-top; each group header (status name + count) is
    sticky too so it stays visible while its rows scroll. Bulk-action bar
    is rendered hidden — JS reveals it when at least one row is checked.

    Columns: select | priority dot | ID | title | status | priority pill |
    agents | sprint | updated | menu. Each row carries the same `data-*`
    attributes as kanban cards so filter/search/sort logic works in both.
    """
    # Statuses in config order; "(unsorted)" catches anything off-config.
    grouped: dict[str, list[dict]] = {s: [] for s in statuses}
    extras: list[dict] = []
    for t in tickets:
        s = t.get("status", "")
        (grouped[s] if s in grouped else extras).append(t)
    if extras:
        grouped["(unsorted)"] = extras

    head = """<div class="list-head">
  <div class="lr-cell lr-cell-select">
    <input type="checkbox" class="lr-checkbox" data-ticket-select-all aria-label="Select all">
  </div>
  <div class="lr-cell lr-cell-prio"></div>
  <div class="lr-cell lr-cell-id">ID</div>
  <div class="lr-cell lr-cell-title">Title</div>
  <div class="lr-cell lr-cell-status">Status</div>
  <div class="lr-cell lr-cell-prio-pill">Priority</div>
  <div class="lr-cell lr-cell-agents">Agents</div>
  <div class="lr-cell lr-cell-sprint">Sprint</div>
  <div class="lr-cell lr-cell-repo">Repo</div>
  <div class="lr-cell lr-cell-deps">Deps</div>
  <div class="lr-cell lr-cell-updated">Updated</div>
  <div class="lr-cell lr-cell-menu"></div>
</div>"""

    body_chunks = []
    for status, rows in grouped.items():
        body_chunks.append(f"""<div class="list-group" data-bucket="{_e(status)}">
  <div class="list-group-header" data-status="{_e(status)}" role="button" tabindex="0" aria-expanded="true" aria-label="Toggle {_e(status)} group">
    <span class="lg-toggle" aria-hidden="true">▾</span>
    <span class="lg-label">{_e(status)}</span>
    <span class="lg-count">{len(rows)}</span>
  </div>
  <div class="list-group-rows">""")
        if rows:
            body_chunks.extend(_list_row_html(t, alias) for t in rows)
        else:
            body_chunks.append('<div class="list-group-empty">No tickets in this group</div>')
        body_chunks.append("</div></div>")

    bulk_bar = """<div class="list-bulk-bar" id="list-bulk-bar" hidden>
  <span class="lbb-count" id="lbb-count">0 selected</span>
  <div class="lbb-actions">
    <button type="button" class="btn btn-sm" data-bulk-move data-status="doing">Move to doing</button>
    <button type="button" class="btn btn-sm" data-bulk-move data-status="review">Move to review</button>
    <button type="button" class="btn btn-sm" data-bulk-move data-status="done">Mark done</button>
    <button type="button" class="btn btn-sm btn-danger" data-bulk-archive>Archive</button>
  </div>
  <button type="button" class="lbb-clear" data-bulk-clear aria-label="Clear selection">×</button>
</div>"""

    return f"""<div class="list-view" id="list-view">
  {head}
  <div class="list-body" id="list-body">
    {"".join(body_chunks)}
  </div>
  {bulk_bar}
</div>"""


def _tree_html(tickets: list[dict], statuses: list[str], alias: str) -> str:
    """Hierarchical view: tickets nested by parent/child with ├─ / └─ glyphs.

    Specs/epics anchor their children directly underneath. Tickets that don't
    name a parent appear as top-level rows. The same `data-*` attributes
    kanban cards carry are mirrored here so filter/search/sort logic still
    applies — the tree view just changes how rows are laid out, not what
    rows exist.
    """
    by_id: dict[str, dict] = {t["id"]: t for t in tickets}
    kids: dict[str | None, list[str]] = {}
    for t in tickets:
        p = t.get("parent") or None
        # Dangling parent reference → treat as root, so the row still renders.
        if p is not None and p not in by_id:
            p = None
        kids.setdefault(p, []).append(t["id"])
    for v in kids.values():
        v.sort()

    roots = kids.get(None, [])

    def _row(t: dict, depth: int, pipe_flags: list[bool], is_last: bool) -> str:
        prio = t.get("priority", "p2")
        kind = t.get("kind") or "task"
        sprint = t.get("sprint") or ""
        agents_list = [a for a in (t.get("agent") or []) if a]
        agents_csv = ",".join(agents_list)
        tags_csv = ",".join(t.get("tags") or [])
        projects_list = [p for p in (t.get("projects") or []) if p]
        projects_csv = ",".join(projects_list)
        depends_csv = ",".join(t.get("depends") or [])
        parent = t.get("parent") or ""
        src_provider = t.get("source_provider") or ""
        # Build the glyph column: one span per pipe flag + the final connector.
        glyph_cells = "".join(
            f'<span class="tr-glyph tr-glyph-{"pipe" if flag else "blank"}"></span>'
            for flag in pipe_flags
        )
        if depth > 0:
            connector_cls = "tr-glyph-last" if is_last else "tr-glyph-mid"
            glyph_cells += f'<span class="tr-glyph {connector_cls}"></span>'
        kind_html = _kind_chip_html(kind)
        agents_html = ""
        if agents_list:
            avs = "".join(
                f'<span class="avatar-initials" data-hue="{_avatar_hue(a)}" '
                f'title="{_e(a)}">{_e(_initials(a))}</span>'
                for a in agents_list
            )
            agents_html = f'<span class="avatar-stack">{avs}</span>'
        sprint_html = f'<span class="tr-sprint">#{_e(sprint)}</span>' if sprint else ""
        data_attrs = (
            f'data-id="{_e(t["id"])}"'
            f' data-status="{_e(t.get("status", ""))}"'
            f' data-p="{_e(prio)}"'
            f' data-agent="{_e(agents_csv)}"'
            f' data-sprint="{_e(sprint)}"'
            f' data-tags="{_e(tags_csv)}"'
            f' data-projects="{_e(projects_csv)}"'
            f' data-depends="{_e(depends_csv)}"'
            f' data-kind="{_e(kind)}"'
            f' data-parent="{_e(parent)}"'
            f' data-source="{_e(src_provider)}"'
            f' data-title="{_e(t.get("title", ""))}"'
            f' data-depth="{depth}"'
        )
        return f"""<a class="tree-row" href="/project/{_e(alias)}/board/{_e(t['id'])}" {data_attrs}>
  <span class="tr-gutter">{glyph_cells}</span>
  <span class="tr-prio-dot" data-p="{_e(prio)}" title="priority {_e(prio)}"></span>
  {kind_html}
  <span class="tr-id">{_e(t['id'])}</span>
  <span class="tr-status" data-status="{_e(t.get("status", ""))}">{_e(t.get("status", ""))}</span>
  <span class="tr-title">{_e(t.get("title", ""))}</span>
  {agents_html}
  {sprint_html}
</a>"""

    rows_html: list[str] = []

    def _emit(tid: str, depth: int, pipe_flags: list[bool], is_last: bool) -> None:
        t = by_id[tid]
        rows_html.append(_row(t, depth, pipe_flags, is_last))
        child_ids = kids.get(tid, [])
        if depth == 0:
            next_flags = pipe_flags
        else:
            next_flags = pipe_flags + [not is_last]
        for i, cid in enumerate(child_ids):
            _emit(cid, depth + 1, next_flags, i == len(child_ids) - 1)

    for i, rid in enumerate(roots):
        _emit(rid, 0, [], i == len(roots) - 1)

    if not rows_html:
        body = '<div class="tree-empty">No tickets to render.</div>'
    else:
        body = "".join(rows_html)

    return f"""<div class="tree-view" id="tree-view">
  <div class="tree-body">{body}</div>
</div>"""


def _board_page(project: dict, tickets: list[dict], config: dict, view: str = "kanban") -> str:
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
    <button type="button" class="btn btn-primary" data-new-ticket title="Open inline ticket creator in the first column">+ New ticket</button>
  </div>
</div>"""
    statuses = config["board"]["statuses"]
    if view == "list":
        body = _list_html(tickets, statuses, alias)
    elif view == "tree":
        body = _tree_html(tickets, statuses, alias)
    else:
        body = _kanban_html(tickets, statuses, alias, project_root=project_root)
    return header + _board_controls_html(view=view) + body


def _board_controls_html(view: str = "kanban") -> str:
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
    is_list = view == "list"
    is_tree = view == "tree"
    is_kanban = not (is_list or is_tree)
    def _tab(active: bool) -> tuple[str, str]:
        return ("active" if active else "", "true" if active else "false")
    k_cls, k_sel = _tab(is_kanban)
    l_cls, l_sel = _tab(is_list)
    tr_cls, tr_sel = _tab(is_tree)
    return f"""<div class="board-controls" id="board-controls" data-current-view="{_e(view)}">
  <div class="bc-row bc-row-primary">
    <div class="view-switcher" role="tablist" aria-label="Board view">
      <button class="view-tab {k_cls}" data-view="kanban" role="tab" aria-selected="{k_sel}">
        <span class="view-tab-glyph">▦</span> Kanban
      </button>
      <button class="view-tab {l_cls}" data-view="list" role="tab" aria-selected="{l_sel}">
        <span class="view-tab-glyph">☰</span> List
      </button>
      <button class="view-tab {tr_cls}" data-view="tree" role="tab" aria-selected="{tr_sel}">
        <span class="view-tab-glyph">⫶</span> Tree
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


from .views.dates import format_iso_datetime as _format_iso_datetime  # noqa: E402


def _read_ticket_activity(project_root: Path, ticket_id: str) -> list[dict]:
    """Pull ticket-scoped events out of `.holoctl/activity.jsonl`.

    Returns a list of `{ts, type, actor}` dicts in chronological order.
    Best-effort — corrupt lines are skipped silently. The Activity card
    falls back to derived events (created / updated / completed) when the
    log is missing or empty.
    """
    log = project_root / ".holoctl" / "activity.jsonl"
    if not log.exists():
        return []
    out: list[dict] = []
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if ev.get("ticket") != ticket_id:
                continue
            out.append({
                "ts": ev.get("ts", ""),
                "type": ev.get("type", "event"),
                "actor": ev.get("actor", ""),
            })
    except OSError:
        return []
    return out


def _ticket_detail_page(ticket: dict, body: str, alias: str,
                        all_tickets: list[dict] | None = None,
                        project_root: Path | None = None,
                        statuses: list[str] | None = None) -> str:
    """Detail page for a single ticket (Phase-4 redesign).

    Layout: breadcrumb-level action bar above a large header (priority
    dot + ID + status pill + priority pill + title), then a two-column
    grid with the markdown body on the left and a stack of three info
    cards (Properties / Linked / Activity) on the right. Both columns
    scroll independently — long descriptions don't push the activity
    log off-screen, and vice versa.
    """
    agents_list = [a for a in (ticket.get("agent") or []) if a]
    status = ticket.get("status", "backlog")
    prio = ticket.get("priority", "p2")
    sprint = ticket.get("sprint") or ""
    tags_list = [t for t in (ticket.get("tags") or []) if t]
    projects_list = [p for p in (ticket.get("projects") or []) if p]
    depends_list = [d for d in (ticket.get("depends") or []) if d]
    # v0.16 hierarchy + external-board origin. Surfaced in Properties + Linked
    # below so the visual board doesn't lag behind the schema/CLI surface.
    kind = ticket.get("kind") or "task"
    parent_id = ticket.get("parent") or ""
    src_provider = ticket.get("source_provider") or ""
    src_ref = ticket.get("source_ref") or ""
    src_url = ticket.get("source_url") or ""
    src_label = ticket.get("source_label") or ""
    children_list: list[dict] = []
    if all_tickets is not None:
        ours = ticket.get("id")
        children_list = [t for t in all_tickets if t.get("parent") == ours and t.get("id") != ours]
    blocks_list: list[str] = []
    if all_tickets is not None:
        ours = ticket.get("id")
        for t in all_tickets:
            if t.get("id") == ours:
                continue
            if ours in (t.get("depends") or []):
                blocks_list.append(t.get("id", ""))
    created = ticket.get("created", "")
    updated = ticket.get("updated", "")
    completed = ticket.get("completed", "")

    body_html = _render_markdown(_strip_empty_sections(body))

    # ── Breadcrumb-level action bar ─────────────────────────────────────
    actions = f"""<div class="detail-toolbar">
  <a class="back-link" href="/project/{_e(alias)}/board">
    <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
    Back to Board
  </a>
  <div class="detail-actions">
    <button type="button" class="btn-sm lr-edit lr-status" data-edit-field="status" data-status="{_e(status)}" data-detail-row data-id="{_e(ticket['id'])}">
      Move ▾
    </button>
    <button type="button" class="btn-sm" data-card-menu data-detail-menu data-id="{_e(ticket['id'])}" data-status="{_e(status)}" aria-label="More actions">⋯</button>
  </div>
</div>"""

    # ── Header ─────────────────────────────────────────────────────────
    header = f"""<div class="detail-header">
  <div class="detail-header-row" data-id="{_e(ticket['id'])}" data-status="{_e(status)}" data-p="{_e(prio)}">
    <span class="kc-prio-dot" data-p="{_e(prio)}" title="priority {_e(prio)}"></span>
    <span class="detail-id">{_e(ticket['id'])}</span>
    <span class="lr-status" data-status="{_e(status)}">{_e(status)}</span>
    <span class="lr-prio-pill" data-p="{_e(prio)}">{_e(prio)}</span>
  </div>
  <h1 class="detail-title">{_e(ticket['title'])}</h1>
</div>"""

    # ── Right rail: Properties card ────────────────────────────────────
    if agents_list:
        avs = "".join(
            f'<span class="avatar-initials" data-hue="{_avatar_hue(a)}" '
            f'title="{_e(a)}">{_e(_initials(a))}</span>'
            for a in agents_list
        )
        agents_value = f'<span class="avatar-stack">{avs}</span><span class="dr-prop-text">{_e(", ".join(agents_list))}</span>'
    else:
        agents_value = '<span class="dr-prop-empty">—</span>'

    sprint_display = f'#{_e(sprint)}' if sprint else '<span class="dr-prop-empty">—</span>'
    tags_display = (", ".join(_e(t) for t in tags_list)
                    if tags_list else '<span class="dr-prop-empty">—</span>')
    projects_display = (", ".join(_e(p) for p in projects_list)
                        if projects_list else '<span class="dr-prop-empty">—</span>')
    created_disp = _format_iso_datetime(created) or "—"
    updated_disp = _format_iso_datetime(updated) or "—"

    # Kind / Parent / Source rows. Kind always shows (so the user sees the
    # default "task" and knows the field exists); Parent + Source render an
    # empty-dash when unset so they're discoverable on every ticket.
    kind_display = _kind_chip_html(kind) if kind != "task" else f'<span class="dr-prop-text">{_e(kind)}</span>'
    if parent_id:
        parent_display = (f'<a class="dr-prop-link mono" '
                          f'href="/project/{_e(alias)}/board/{_e(parent_id)}">{_e(parent_id)}</a>')
    else:
        parent_display = '<span class="dr-prop-empty">—</span>'
    if src_provider or src_url or src_ref or src_label:
        chip = _source_chip_html(src_provider, src_url, src_ref, src_label)
        if src_url:
            source_display = (f'{chip} <a class="dr-prop-link mono" '
                              f'href="{_e(src_url)}" target="_blank" rel="noopener">↗ open</a>')
        else:
            source_display = chip
    else:
        source_display = '<span class="dr-prop-empty">—</span>'

    properties = f"""<div class="dr-card" data-detail-row data-id="{_e(ticket['id'])}">
  <div class="dr-card-title">Properties</div>
  <div class="dr-prop">
    <span class="dr-prop-label">Status</span>
    <button type="button" class="dr-prop-edit lr-edit lr-status" data-edit-field="status" data-status="{_e(status)}">{_e(status)}</button>
  </div>
  <div class="dr-prop">
    <span class="dr-prop-label">Priority</span>
    <button type="button" class="dr-prop-edit lr-edit lr-prio-pill" data-edit-field="priority" data-p="{_e(prio)}">{_e(prio)}</button>
  </div>
  <div class="dr-prop">
    <span class="dr-prop-label">Kind</span>
    <button type="button" class="dr-prop-edit-text" data-edit-text-field="kind" data-current="{_e(kind)}">{kind_display}</button>
  </div>
  <div class="dr-prop">
    <span class="dr-prop-label">Parent</span>
    <button type="button" class="dr-prop-edit-text" data-edit-text-field="parent" data-current="{_e(parent_id)}">{parent_display}</button>
  </div>
  <div class="dr-prop">
    <span class="dr-prop-label">Agents</span>
    <button type="button" class="dr-prop-edit-text" data-edit-text-field="agent" data-current="{_e(','.join(agents_list))}">{agents_value}</button>
  </div>
  <div class="dr-prop">
    <span class="dr-prop-label">Sprint</span>
    <button type="button" class="dr-prop-edit-text" data-edit-text-field="sprint" data-current="{_e(sprint)}">{sprint_display}</button>
  </div>
  <div class="dr-prop">
    <span class="dr-prop-label">Tags</span>
    <button type="button" class="dr-prop-edit-text" data-edit-text-field="tags" data-current="{_e(','.join(tags_list))}">{tags_display}</button>
  </div>
  <div class="dr-prop">
    <span class="dr-prop-label">Repo</span>
    <button type="button" class="dr-prop-edit-text" data-edit-text-field="projects" data-current="{_e(','.join(projects_list))}">{projects_display}</button>
  </div>
  <div class="dr-prop">
    <span class="dr-prop-label">Source</span>
    <span class="dr-prop-value">{source_display}</span>
  </div>
  <hr class="dr-divider">
  <div class="dr-prop dr-prop-readonly">
    <span class="dr-prop-label">Created</span>
    <span class="dr-prop-value mono" title="{_e(created)}">{_e(created_disp)}</span>
  </div>
  <div class="dr-prop dr-prop-readonly">
    <span class="dr-prop-label">Updated</span>
    <span class="dr-prop-value mono" title="{_e(updated)}">{_e(updated_disp)}</span>
  </div>
</div>"""

    # ── Right rail: Linked card ────────────────────────────────────────
    # Order: parent first (the spec this lives under), then children
    # (work this ticket spawns), then depends (blockers above this one),
    # then blocks (downstream of this one). Reads top-down like a tree.
    if depends_list or blocks_list or parent_id or children_list:
        parent_item = ""
        if parent_id:
            parent_item = (
                f'<a class="dr-linked-item" href="/project/{_e(alias)}/board/{_e(parent_id)}">'
                f'<span class="dr-linked-arrow">↑</span> parent {_e(parent_id)}</a>'
            )
        child_items = "".join(
            f'<a class="dr-linked-item" href="/project/{_e(alias)}/board/{_e(c.get("id",""))}">'
            f'<span class="dr-linked-arrow">↓</span> child {_e(c.get("id",""))} '
            f'<span class="dr-linked-meta">· {_e((c.get("kind") or "task"))} · '
            f'{_e(c.get("status",""))}</span></a>'
            for c in children_list
        )
        dep_items = "".join(
            f'<a class="dr-linked-item" href="/project/{_e(alias)}/board/{_e(d)}">'
            f'<span class="dr-linked-arrow">↳</span> depends on {_e(d)}</a>'
            for d in depends_list
        )
        blk_items = "".join(
            f'<a class="dr-linked-item" href="/project/{_e(alias)}/board/{_e(b)}">'
            f'<span class="dr-linked-arrow">↳</span> blocks {_e(b)}</a>'
            for b in blocks_list
        )
        linked_body = parent_item + child_items + dep_items + blk_items
    else:
        linked_body = '<div class="dr-empty">No linked tickets</div>'

    linked = f"""<div class="dr-card">
  <div class="dr-card-title">Linked</div>
  <div class="dr-linked">{linked_body}</div>
</div>"""

    # ── Right rail: Activity card ──────────────────────────────────────
    # Combine derived events (always available) with anything matching in
    # activity.jsonl, then sort newest-first.
    derived: list[tuple[str, str, str]] = []  # (ts, label, type)
    if created:
        derived.append((created, "Created", "ticket.created"))
    if updated and updated != created:
        derived.append((updated, "Updated", "ticket.updated"))
    if completed:
        derived.append((completed, "Marked done", "ticket.completed"))
    if project_root is not None:
        for ev in _read_ticket_activity(project_root, ticket.get("id", "")):
            tp = ev.get("type", "")
            # The "ticket.created" event in the log mirrors `created`; skip
            # the duplicate since it'd be the same timestamp.
            if tp == "ticket.created":
                continue
            label = {
                "ticket.body_updated": "Body edited",
            }.get(tp, tp.replace("ticket.", "").replace("_", " ").capitalize())
            derived.append((ev.get("ts", ""), label, tp))
    # Newest first; on equal timestamps (Board.add → Board.move can happen
    # in the same wall-clock second), break the tie so the more-advanced
    # state wins — completed > body_updated > updated > created.
    _TYPE_RANK = {
        "ticket.completed": 0,
        "ticket.body_updated": 1,
        "ticket.updated": 2,
        "ticket.created": 3,
    }
    derived.sort(
        key=lambda x: (x[0], -_TYPE_RANK.get(x[2], 99)),
        reverse=True,
    )
    if derived:
        items = "".join(
            f'<li class="dr-act-item" data-type="{_e(t)}">'
            f'<span class="dr-act-dot"></span>'
            f'<span class="dr-act-label">{_e(label)}</span>'
            f'<span class="dr-act-time mono" title="{_e(ts)}">{_e(_format_iso_datetime(ts) or ts)}</span>'
            f'</li>'
            for ts, label, t in derived
        )
        activity_body = f'<ol class="dr-activity">{items}</ol>'
    else:
        activity_body = '<div class="dr-empty">No activity yet</div>'

    activity = f"""<div class="dr-card">
  <div class="dr-card-title">Activity</div>
  {activity_body}
</div>"""

    # Embed the configured status list as a CSV so the JS popover for the
    # toolbar Move ▾ / ⋯ menu has something to populate with — on the
    # detail page there are no `.kanban-col[data-status]` elements to mine.
    statuses_csv = ",".join(_e(s) for s in (statuses or []))
    return f"""<div class="detail-page" data-detail-page data-statuses="{statuses_csv}">
  {actions}
  {header}
  <div class="detail-grid">
    <div class="detail-main">
      <div class="detail-section">
        <div class="detail-section-title">Description</div>
        <div class="detail-section-body">{body_html}</div>
      </div>
    </div>
    <aside class="detail-rail">
      {properties}
      {linked}
      {activity}
    </aside>
  </div>
</div>"""


# ── routes ───────────────────────────────────────────────────────────────────

@app.get("/project/{alias}")
def project_redirect(alias: str):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/project/{alias}/board")


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


@app.post("/api/project/{alias}/tickets")
def api_ticket_create(alias: str, payload: dict = Body(...)):
    """Create a ticket from a JSON payload.

    Mirrors `holoctl board add`: requires `title`, accepts optional
    `status`, `priority`, `agent`, `sprint`, `tags`. Returns the created
    ticket dict on 201, or `{error: ...}` on 4xx for validation failures
    (unknown agent, invalid priority, etc.) so the client can surface the
    message inline without a refresh.
    """
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    board = Board(Path(project["path"]), project["config"])
    try:
        ticket = board.add(payload)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(status_code=201, content=ticket)


@app.patch("/api/project/{alias}/tickets/{ticket_id}")
def api_ticket_patch(alias: str, ticket_id: str, payload: dict = Body(...)):
    """Update a single editable field on a ticket.

    Body: `{"field": "priority", "value": "p1"}`. Allowed fields and
    validation come from `Board.set` — the dashboard is just a pass-through
    so the CLI / MCP / dashboard all share one code path. Lists may be
    passed either as actual JSON arrays (`["a","b"]`) or as bracketed
    strings; non-string scalars are JSON-encoded before handoff so
    `_parse_set_value` interprets them correctly.
    """
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    field = (payload.get("field") or "").strip()
    if not field:
        raise HTTPException(status_code=400, detail="field is required")
    raw_value = payload.get("value")
    if isinstance(raw_value, str):
        value_str = raw_value
    elif raw_value is None:
        value_str = "null"
    elif isinstance(raw_value, bool):
        value_str = "true" if raw_value else "false"
    else:
        value_str = json.dumps(raw_value)
    board = Board(Path(project["path"]), project["config"])
    try:
        result = board.set(ticket_id, field, value_str)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=result)


@app.post("/api/project/{alias}/tickets/{ticket_id}/move")
def api_ticket_move(alias: str, ticket_id: str, payload: dict = Body(...)):
    """Move a ticket to a new status.

    Body: `{"status": "doing"}`. Status must be in
    `config.board.statuses`. 404 when the project or ticket doesn't
    exist; 400 when the target status is invalid.
    """
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    new_status = (payload.get("status") or "").strip()
    if not new_status:
        raise HTTPException(status_code=400, detail="status is required")
    board = Board(Path(project["path"]), project["config"])
    try:
        result = board.move(ticket_id, new_status)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=result)


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
