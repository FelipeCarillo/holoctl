from __future__ import annotations
import asyncio
import json
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

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
from .routes.project_metrics import router as _project_metrics_router  # noqa: E402
from .routes.workspace_metrics import router as _workspace_metrics_router  # noqa: E402
app.include_router(_home_router)
app.include_router(_workspace_metrics_router)
app.include_router(_project_board_router)
app.include_router(_project_detail_router)
app.include_router(_project_doc_router)
app.include_router(_project_meta_router)
app.include_router(_project_metrics_router)


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


@app.post("/api/project/{alias}/tickets/bulk-move")
def api_ticket_bulk_move(alias: str, payload: dict = Body(...)):
    """Move many tickets to one status in a single request.

    Body: `{"ids": ["TST-001", ...], "status": "doing"}`. Delegates to
    `Board.batch_move`, which is atomic per-ticket: it moves what it can
    and reports the rest. Returns the board's batch result verbatim —
    `{"moved": [...], "errors": [{"id", "error"}, ...], "count": N}` —
    so the caller sees per-id success/failure. The endpoint itself
    returns 200 even on partial failure (mirrors the MCP batch_move
    contract); only project-level / validation problems are 4xx.
    """
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="ids must be a non-empty list")
    if not all(isinstance(i, str) for i in ids):
        raise HTTPException(status_code=400, detail="ids must be a list of strings")
    new_status = (payload.get("status") or "").strip()
    if not new_status:
        raise HTTPException(status_code=400, detail="status is required")
    board = Board(Path(project["path"]), project["config"])
    result = board.batch_move(ids, new_status)
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


# Cap concurrent SSE streams. Each connection holds an event-loop task that
# polls a file every 2s forever; without a bound, a handful of stuck browser
# tabs (or a trivial DoS) can pin the loop and the threadpool. 32 is generous
# for a localhost-first dashboard while still being a hard ceiling.
#
# Plain int, not a semaphore: the reservation happens synchronously inside the
# async handler (no await between check and increment), which is atomic on the
# event loop — a connect burst can't slip past the cap and queue inside the
# generator the way the old `.locked()` fast-path + acquire-in-generator did.
_SSE_MAX_CONNECTIONS = 32
_sse_connections = 0


def _sse_take_slot() -> Callable[[], None] | None:
    """Reserve one SSE slot; returns an idempotent release, or None when full.

    Only called from the event loop thread, synchronously — so check+increment
    has no TOCTOU window. The release is wired to BOTH the stream generator's
    ``finally`` and the response's background task: whichever path runs (clean
    close, client disconnect before the first chunk, generator exception)
    decrements exactly once.
    """
    global _sse_connections
    if _sse_connections >= _SSE_MAX_CONNECTIONS:
        return None
    _sse_connections += 1
    released = False

    def _release() -> None:
        nonlocal released
        global _sse_connections
        if not released:
            released = True
            _sse_connections -= 1

    return _release

# Poll cadence for the board index, and how often to emit an SSE heartbeat
# comment so proxies / browsers don't treat an idle stream as dead.
_SSE_POLL_SECONDS = 2
_SSE_HEARTBEAT_SECONDS = 25


def _read_index_snapshot(
    index_path: Path, last_mtime: float | None = None
) -> tuple[float, str | None] | None:
    """Read + compact the board index for the SSE payload.

    Stat-first: when *last_mtime* is given and the file's mtime hasn't moved,
    returns ``(mtime, None)`` after the stat alone — no read, no JSON parse.
    This runs every poll tick (2s) per connection, so skipping the full
    read+parse for the (overwhelmingly common) idle case matters.

    Returns ``None`` if the file is absent, ``(mtime, None)`` if unchanged
    since *last_mtime*, or ``(mtime, single_line_json)`` with fresh content.
    Runs blocking filesystem I/O, so callers invoke it via
    `asyncio.to_thread` to keep the event loop free.
    """
    if not index_path.exists():
        return None
    mtime = index_path.stat().st_mtime
    if last_mtime is not None and mtime == last_mtime:
        return mtime, None
    # The on-disk index.json is pretty-printed (indent="\t"), but the SSE
    # protocol treats every newline inside the `data:` field as a record
    # terminator — the browser would only see "{" before the first newline.
    # Compact it onto a single line so e.data is the full JSON.
    raw = index_path.read_text(encoding="utf-8")
    try:
        # `ensure_ascii=False`: preserve accented titles in the SSE payload so
        # DevTools / Network tab show readable text, not `é` escapes.
        data = json.dumps(json.loads(raw), separators=(",", ":"), ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        data = raw.replace("\n", " ").replace("\r", "")
    return mtime, data


@app.get("/api/project/{alias}/events")
async def api_events(alias: str):
    project = _get_project(alias)
    if not project:
        raise HTTPException(status_code=404, detail="Not found")

    # Reserve the slot before streaming starts — fail fast rather than
    # queueing a new poller when all slots are taken.
    release_slot = _sse_take_slot()
    if release_slot is None:
        raise HTTPException(status_code=503, detail="Too many live connections")

    index_path = Path(project["path"]) / ".holoctl" / "board" / "index.json"

    async def event_stream():
        try:
            last_mtime = None
            since_heartbeat = 0.0
            while True:
                try:
                    # File I/O off the event loop so blocking stat()/read_text()
                    # can't stall every other request sharing this worker.
                    # Stat-first: `data is None` means unchanged since last_mtime.
                    snapshot = await asyncio.to_thread(
                        _read_index_snapshot, index_path, last_mtime
                    )
                    if snapshot is not None:
                        mtime, data = snapshot
                        if data is not None:
                            last_mtime = mtime
                            yield f"event: board-update\ndata: {data}\n\n"
                            since_heartbeat = 0.0
                except Exception:
                    pass
                # Keepalive comment (ignored by EventSource) so idle streams
                # aren't reaped by proxies/browsers between board updates.
                since_heartbeat += _SSE_POLL_SECONDS
                if since_heartbeat >= _SSE_HEARTBEAT_SECONDS:
                    since_heartbeat = 0.0
                    yield ": keepalive\n\n"
                await asyncio.sleep(_SSE_POLL_SECONDS)
        finally:
            release_slot()

    # `background=` covers the path where the generator never starts (client
    # gone before the first chunk): Starlette runs it after the response
    # teardown either way, and release is idempotent with the finally above.
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        background=BackgroundTask(release_slot),
    )
