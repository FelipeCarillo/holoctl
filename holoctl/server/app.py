from __future__ import annotations
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..lib.board import Board
from .paths import safe_resolve as _safe_resolve
from .projects import (
    get_projects as _get_projects,
    get_project as _get_project,
    read_context_dir as _read_context_dir,
)

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="holoctl dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# Modular routers. Each lives under server/routes/.
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


@app.get("/api/project/{alias}/context/tree")
def api_context_tree(alias: str, path: str = Query(default="")):
    """Return one directory level of `.holoctl/context/<path>`.

    ``path`` is empty / absent for the top level.  Traversal attempts
    return 403; unknown alias or non-directory path return 404.
    """
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Not found")
    root = (Path(project["path"]) / ".holoctl" / "context").resolve()
    if path:
        target = _safe_resolve(root, path)
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=404, detail="Not a directory")
    entries = _read_context_dir(Path(project["path"]), path)
    return {"entries": [{"name": e["name"], "type": "dir" if e["isDir"] else "file"} for e in entries]}


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
