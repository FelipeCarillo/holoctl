"""Doc detail subpages: agents/{slug}, commands/{slug}, context/{filename}.
Each one reads a markdown file under .holoctl/<kind>/ and renders it through
the shared doc_detail template."""
from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from ..jinja import render
from ..views.doc import doc_context
from .project_board import _PROJECT_TABS

router = APIRouter()


def _safe_resolve(root: Path, name: str) -> Path:
    """Resolve `root / name` and assert it stays inside `root`. Raises 403
    on traversal — matches the protection the legacy app.py routes had."""
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden")
    return candidate


def _project_breadcrumbs(project: dict, listing_label: str, listing_path: str,
                         detail_label: str) -> list[dict]:
    alias = project["alias"]
    return [
        {"label": "holoctl", "href": "/"},
        {"label": project["name"], "href": f"/project/{alias}/board"},
        {"label": listing_label, "href": f"/project/{alias}/{listing_path}"},
        {"label": detail_label},
    ]


@router.get("/project/{alias}/agents/{slug}", response_class=HTMLResponse)
def project_agent_detail(alias: str, slug: str):
    from ..projects import get_project
    from ...lib.markdown import parse_frontmatter

    project = get_project(alias)
    if not project:
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Not found")),
            status_code=404,
        )
    root = (Path(project["path"]) / ".holoctl" / "agents").resolve()
    f = _safe_resolve(root, f"{slug}.md")
    if not f.exists():
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Agent not found")),
            status_code=404,
        )
    fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
    title = fm.get("name", slug)
    tools = fm.get("tools")
    if isinstance(tools, list):
        tools = ", ".join(tools)
    meta = {
        "Model": fm.get("model"),
        "Trigger": fm.get("trigger"),
        "Tools": tools,
        "Description": fm.get("description"),
    }
    ctx = doc_context(title, body, alias, "agents", meta)
    return render(
        "project/doc_detail.html",
        title=f"{title} — {project['name']}",
        current_alias=alias,
        current_tab="agents",
        breadcrumbs=_project_breadcrumbs(project, "Agents", "agents", title),
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        **ctx,
    )


@router.get("/project/{alias}/commands/{slug}", response_class=HTMLResponse)
def project_command_detail(alias: str, slug: str):
    from ..projects import get_project
    from ...lib.markdown import parse_frontmatter

    project = get_project(alias)
    if not project:
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Not found")),
            status_code=404,
        )
    root = (Path(project["path"]) / ".holoctl" / "commands").resolve()
    f = _safe_resolve(root, f"{slug}.md")
    if not f.exists():
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Command not found")),
            status_code=404,
        )
    fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
    title = f"/{fm.get('name', slug)}"
    meta = {
        "Description": fm.get("description"),
        "Arguments": fm.get("arguments"),
    }
    ctx = doc_context(title, body, alias, "commands", meta)
    return render(
        "project/doc_detail.html",
        title=f"{title} — {project['name']}",
        current_alias=alias,
        current_tab="commands",
        breadcrumbs=_project_breadcrumbs(project, "Commands", "commands", title),
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        **ctx,
    )


@router.get("/project/{alias}/context/{filename}", response_class=HTMLResponse)
def project_context_detail(alias: str, filename: str):
    from ..projects import get_project
    from ...lib.markdown import parse_frontmatter

    project = get_project(alias)
    if not project:
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Not found")),
            status_code=404,
        )
    root = (Path(project["path"]) / ".holoctl" / "context").resolve()
    f = _safe_resolve(root, filename)
    if not f.exists() or not f.is_file():
        return HTMLResponse(
            render("base.html", title="Not Found",
                   content=render("partials/_empty_state.html", msg="Context document not found")),
            status_code=404,
        )
    raw = f.read_text(encoding="utf-8")
    if f.suffix == ".md":
        fm, body = parse_frontmatter(raw)
    else:
        fm, body = {}, raw
    title = fm.get("title", f.name)
    meta = {k.capitalize(): v for k, v in fm.items()
            if k not in ("title",) and v is not None}
    ctx = doc_context(title, body, alias, "context", meta)
    return render(
        "project/doc_detail.html",
        title=f"{title} — {project['name']}",
        current_alias=alias,
        current_tab="context",
        breadcrumbs=_project_breadcrumbs(project, "Context", "context", title),
        tabs=_PROJECT_TABS,
        tab_base=f"/project/{alias}",
        **ctx,
    )
