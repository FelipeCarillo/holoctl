"""Typed schema for board tickets.

A ticket is stored as a plain dict in two places that must stay in sync:

  1. the index row in ``.holoctl/board/index.json`` (written by ``Board.add``
     / ``Board.rebuild_index``), and
  2. the frontmatter of ``.holoctl/board/tickets/<ID>-<slug>.md`` (written by
     ``Board._create_ticket_md`` / patched by ``Board._patch_ticket_md``).

``Ticket`` is a ``TypedDict`` — pure typing, zero runtime change. Tickets stay
plain dicts on the wire (JSON index, MCP responses, Jinja contexts); promoting
the schema to a dataclass is deliberately staged as a possible later step.

``total=False`` because rows from older indices may predate newer fields
(e.g. ``acceptance_total``/``acceptance_done``, ``source_*``) — consumers read
via ``.get()`` and backfill where it matters (see ``Board.children``).

``tests/test_ticket_schema.py`` pins this schema against what ``Board.add()``
and ``Board.rebuild_index()`` actually produce, so drift fails loud.
"""
from __future__ import annotations

from typing import TypedDict


class Ticket(TypedDict, total=False):
    """One work item, as stored in the board index / ticket frontmatter."""

    # ── Identity & hierarchy ───────────────────────────────────────────────
    id: str                     # "<PREFIX>-<zero-padded number>", e.g. "HOL-042"
    title: str
    kind: str                   # task (default) | story | bug | spec | epic | rfc | ...
    parent: str | None          # id of the containing work item, if any

    # ── External-source linkage (Trello / Linear / GitHub / Jira / ...) ───
    source_provider: str | None
    source_ref: str | None      # native id on the source board (ENG-123, #4567)
    source_url: str | None
    source_label: str | None

    # ── Assignment & scoping (list-typed; see TICKET_LIST_FIELDS) ─────────
    agent: list[str]            # personas from .holoctl/agents/
    projects: list[str]         # replaces legacy scalar `scope`
    files: list[str]            # paths the ticket touches (parallel-safety proof)
    depends: list[str]          # ids of blocking tickets
    tags: list[str]

    # ── Workflow ───────────────────────────────────────────────────────────
    status: str                 # one of config["board"]["statuses"]
    priority: str               # one of config["board"]["priorities"]
    sprint: str | None

    # ── Timestamps (ISO 8601 UTC, `Z` suffix; legacy rows may be date-only) ─
    created: str
    updated: str
    completed: str | None       # set on entering `done`, cleared on leaving
    due: str | None             # not written by Board yet; read by the card view

    # ── Denormalized DoD progress (recomputed from the .md body) ──────────
    acceptance_total: int
    acceptance_done: int

    # ── Storage ────────────────────────────────────────────────────────────
    file: str                   # .md path relative to .holoctl/board/

    # ── View-layer enrichment (never persisted) ───────────────────────────
    # Stamped by the workspace metrics route when tickets from several
    # projects are rolled into one list, so per-ticket links resolve.
    _source_alias: str


# Fields stored as lists in the index but serialized as comma-joined strings
# in the .md frontmatter (see Board._create_ticket_md / _patch_ticket_md and
# the `_normalize_array` round-trip in Board.rebuild_index).
TICKET_LIST_FIELDS: tuple[str, ...] = ("agent", "projects", "files", "depends", "tags")

# Optional external-board linkage fields; inherited from `shared` by every
# child in a `Board.batch_add` decomposition unless explicitly overridden.
TICKET_SOURCE_FIELDS: tuple[str, ...] = (
    "source_provider",
    "source_ref",
    "source_url",
    "source_label",
)
