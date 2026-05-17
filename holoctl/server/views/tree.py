"""Tree view presenter: hierarchical ticket layout by parent/child."""
from __future__ import annotations

from .card import card_context


def tree_context(tickets: list[dict], alias: str) -> dict:
    """Flatten tickets into a depth-first sequence with the glyph-state each
    row needs to draw its part of the connector tree (├─ / └─)."""
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
    rows: list[dict] = []

    def _emit(tid: str, depth: int, pipe_flags: list[bool], is_last: bool) -> None:
        t = by_id[tid]
        c = card_context(t, alias)
        c["depth"] = depth
        c["pipe_flags"] = list(pipe_flags)
        c["is_last"] = is_last
        rows.append(c)
        child_ids = kids.get(tid, [])
        next_flags = pipe_flags if depth == 0 else pipe_flags + [not is_last]
        for i, cid in enumerate(child_ids):
            _emit(cid, depth + 1, next_flags, i == len(child_ids) - 1)

    for i, rid in enumerate(roots):
        _emit(rid, 0, [], i == len(roots) - 1)

    return {"tree_rows": rows}
