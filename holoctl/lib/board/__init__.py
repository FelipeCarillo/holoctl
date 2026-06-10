"""The holoctl board: ticket index + per-ticket markdown, behind one facade.

This package replaces the former ``holoctl/lib/board.py`` god module
(item 5.3), split by responsibility:

- :mod:`.store`         — index load/save/cache/lock/rebuild (``BoardIndexStore``)
- :mod:`.validate`      — pure validation helpers (status/priority/agents/
                          hierarchy/batch-overlap)
- :mod:`.markdown_sync` — ticket ``.md`` create/patch + DoD acceptance counts
- :mod:`.create`        — ``add`` / ``batch_add`` (``BoardCreateOps``)
- :mod:`.ops`           — move/set/delete/batch/ack/note/set_body
                          (``BoardTicketOps``) + the curator done-hook default

``Board`` here is the facade composing those mixins plus the read-side
queries. The public API is unchanged: ``from holoctl.lib.board import Board``
(and the package-internal ``from .board import Board``) keep working, as does
``from holoctl.lib.board import _INDEX_CACHE`` (same dict object as
``store._INDEX_CACHE`` — tests rely on the identity).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..board_tree import render_tree
from ..markdown import parse_frontmatter
from ..ticket import Ticket
from .create import BoardCreateOps
from .markdown_sync import (
    _CHECKBOX_RE as _CHECKBOX_RE,
    _count_acceptance as _count_acceptance,
    _yaml_format as _yaml_format,
)
from .ops import BoardTicketOps, _default_meta_curate_done
from .store import (
    _INDEX_CACHE as _INDEX_CACHE,
    _log_activity as _log_activity,
    _now as _now,
    _replace_with_retry as _replace_with_retry,
)
from .validate import (
    _normalize_array as _normalize_array,
    _parse_set_value as _parse_set_value,
)

__all__ = ["Board"]


class Board(BoardCreateOps, BoardTicketOps):
    def __init__(
        self,
        project_root: Path,
        config: dict,
        on_meta_curate_done: Callable[[Path, Ticket], dict | None] | None = None,
    ) -> None:
        self._root = project_root
        self._config = config
        self._board_dir = project_root / ".holoctl" / "board"
        self._index_path = self._board_dir / "index.json"
        self._tickets_dir = self._board_dir / "tickets"
        # Sidecar lock file guarding the load→mutate→save critical section.
        # Distinct from index.json so a crash mid-write never leaves a held
        # lock embedded in the data file, and so we can lock even before the
        # index exists.
        self._lock_path = self._board_dir / "index.json.lock"
        # Hook fired when a `meta:curate` ticket transitions to `done`
        # (see BoardTicketOps.move). Injectable for decoupling/tests; the
        # default keeps the original lazy soft-import of the curator.
        self._on_meta_curate_done = (
            on_meta_curate_done if on_meta_curate_done is not None else _default_meta_curate_done
        )

    def stat(self) -> dict:
        data = self._load()
        return {**data["meta"]["counts"], "nextId": data["meta"]["nextId"]}

    def get(self, ticket_id: str) -> Ticket | None:
        data = self._load()
        return next((t for t in data["tickets"] if t["id"] == ticket_id), None)

    def ls(self, filters: dict | None = None) -> list[Ticket]:
        data = self._load()
        tickets: list[Ticket] = data["tickets"]
        f = filters or {}

        if f.get("sprint"):
            tickets = [t for t in tickets if t.get("sprint") == f["sprint"]]
        if f.get("status"):
            tickets = [t for t in tickets if t.get("status") == f["status"]]
        if f.get("agent"):
            tickets = [t for t in tickets if f["agent"] in (t.get("agent") or [])]
        if f.get("tag"):
            tickets = [t for t in tickets if f["tag"] in (t.get("tags") or [])]
        if f.get("priority"):
            tickets = [t for t in tickets if t.get("priority") == f["priority"]]
        if f.get("project"):
            tickets = [t for t in tickets if f["project"] in (t.get("projects") or [])]
        if f.get("kind"):
            tickets = [t for t in tickets if (t.get("kind") or "task") == f["kind"]]
        if f.get("parent"):
            tickets = [t for t in tickets if t.get("parent") == f["parent"]]

        return tickets

    def tree(
        self,
        filters: dict | None = None,
        root: str | None = None,
    ) -> list[dict]:
        """Return tickets as a flat list pre-annotated for tree rendering.

        Each row is ``{"ticket": <ticket dict>, "depth": int, "prefix": str}``.
        ``prefix`` is the pre-baked ASCII glyph string the CLI prints before
        the ticket id (e.g. ``"│  └─ "``); empty for roots.

        ``filters`` accepts the same keys as :meth:`ls`. When filters drop a
        descendant whose parent is kept, the parent still shows so the
        hierarchy reads correctly. Conversely, an ancestor that doesn't match
        is *kept* if at least one of its descendants matches — pruning a tree
        from the middle would lie about the structure.

        ``root`` restricts the result to the subtree rooted at that id.
        """
        data = self._load()
        all_tickets: list[Ticket] = data["tickets"]
        if filters:
            matched_ids = {t["id"] for t in self.ls(filters)}
        else:
            matched_ids = {t["id"] for t in all_tickets}
        return render_tree(all_tickets, matched_ids, root)

    def children(self, parent_id: str) -> dict:
        """Return direct children of a work item plus aggregate progress.

        Used to inspect a spec/story/epic and see how its child tasks are
        doing. Computes:
          - children: list of direct descendants (one level)
          - total_acceptance: total DoD checkboxes across all children
          - acked: total `[x]` checkboxes across all children
          - by_status: counts of children per status
        """
        data = self._load()
        parent: Ticket | None = next(
            (t for t in data["tickets"] if t["id"] == parent_id), None
        )
        if not parent:
            raise KeyError(f"Ticket {parent_id} not found")
        children: list[Ticket] = [t for t in data["tickets"] if t.get("parent") == parent_id]
        # Aggregate DoD progress from the denormalized counts stored in the
        # index (task 4.3) — no longer reads every child .md per view. For an
        # old index that predates these fields, fall back to reading the body
        # once and backfill the index so the next call is cheap.
        total = 0
        acked = 0
        backfilled = False
        for c in children:
            if "acceptance_total" in c and "acceptance_done" in c:
                total += int(c.get("acceptance_total") or 0)
                acked += int(c.get("acceptance_done") or 0)
                continue
            c_total, c_done = self._backfill_acceptance(c)
            total += c_total
            acked += c_done
            backfilled = True
        if backfilled:
            # Persist the backfilled counts under lock so we don't re-read next
            # time. Re-load inside the lock to avoid clobbering a concurrent
            # writer, re-applying the freshly-computed counts onto the current
            # rows.
            self._persist_backfill(parent_id)
        by_status: dict[str, int] = {}
        for c in children:
            s = c.get("status", "?")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "parent": parent,
            "children": children,
            "total_acceptance": total,
            "acked": acked,
            "by_status": by_status,
        }

    def _backfill_acceptance(self, ticket: Ticket) -> tuple[int, int]:
        """Read a ticket's .md body and return ``(total, done)`` DoD counts.

        Used as the backward-compat fallback when an index entry predates the
        ``acceptance_total``/``acceptance_done`` fields. Missing file → (0, 0).
        """
        if not ticket.get("file"):
            return 0, 0
        md_path = self._board_dir / ticket["file"]
        if not md_path.exists():
            return 0, 0
        _, body = parse_frontmatter(md_path.read_text(encoding="utf-8"))
        return _count_acceptance(body)

    def _persist_backfill(self, parent_id: str) -> None:
        """Backfill missing acceptance counts on a parent's children, persisted.

        Re-reads the index under the board lock (so a concurrent writer isn't
        clobbered), recomputes counts for any child still missing them, and
        saves only if something changed.
        """
        with self._locked():
            data = self._load_mut()
            changed = False
            for c in data["tickets"]:
                if c.get("parent") != parent_id:
                    continue
                if "acceptance_total" in c and "acceptance_done" in c:
                    continue
                t, d = self._backfill_acceptance(c)
                c["acceptance_total"] = t
                c["acceptance_done"] = d
                changed = True
            if changed:
                self._save(data)

    def show(self, ticket_id: str) -> dict:
        """Return frontmatter + body of a ticket as a single record.

        Replaces the anti-pattern of agents reading
        `.holoctl/board/tickets/<ID>-*.md` directly. Single source of truth
        for ticket inspection — used by `/board <ID>` and `mcp__holoctl__board_show`.
        """
        data = self._load()
        ticket: Ticket | None = next(
            (t for t in data["tickets"] if t["id"] == ticket_id), None
        )
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")
        if not ticket.get("file"):
            raise ValueError(f"Ticket {ticket_id} has no file path")
        full_path = self._board_dir / ticket["file"]
        if not full_path.exists():
            raise FileNotFoundError(f"Ticket file missing: {full_path}")
        content = full_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)
        return {
            "id": ticket_id,
            "frontmatter": fm,
            "body": body,
            "raw": content,
        }

    def next_id(self) -> str:
        data = self._load()
        return self._generate_id(data["meta"]["nextId"])
