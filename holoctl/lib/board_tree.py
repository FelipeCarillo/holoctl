"""Pure tree-rendering for the board hierarchy.

Extracted from ``Board`` so the presentation logic (ASCII glyph computation,
ancestor-keep expansion, deterministic DFS) lives apart from the data layer.
``render_tree`` takes plain data and returns render-ready rows — no I/O, no
``Board`` coupling — which makes it trivial to unit-test in isolation.
"""
from __future__ import annotations

from .ticket import Ticket


def render_tree(
    all_tickets: list[Ticket],
    matched_ids: set[str],
    root: str | None = None,
) -> list[dict]:
    """Return tickets as a flat list pre-annotated for tree rendering.

    Each row is ``{"ticket": <ticket dict>, "depth": int, "prefix": str}``.
    ``prefix`` is the pre-baked ASCII glyph string printed before the ticket id
    (e.g. ``"│  └─ "``); empty for roots.

    ``matched_ids`` is the set of ticket ids that matched the caller's filters
    (or all ids when unfiltered). An ancestor that didn't match is *kept* if any
    descendant matched, so the hierarchy reads correctly rather than being
    pruned from the middle.

    ``root`` restricts the result to the subtree rooted at that id.
    """
    by_id: dict[str, Ticket] = {t["id"]: t for t in all_tickets}

    # Expand the matched set with every ancestor — keeps the tree readable.
    keep: set[str] = set()
    for tid in matched_ids:
        cursor: str | None = tid
        depth_guard = 0
        while cursor and depth_guard <= len(all_tickets):
            if cursor in keep:
                break
            keep.add(cursor)
            cursor = (by_id.get(cursor) or {}).get("parent") or None
            depth_guard += 1

    # Build the children adjacency over the kept set.
    kids: dict[str | None, list[str]] = {}
    for t in all_tickets:
        if t["id"] not in keep:
            continue
        p = t.get("parent") or None
        # An item whose parent is outside `keep` is treated as a root in the
        # rendered tree — otherwise we'd dangle it.
        if p is not None and p not in keep:
            p = None
        kids.setdefault(p, []).append(t["id"])

    # Sort children stably by id for deterministic output.
    for v in kids.values():
        v.sort()

    if root is not None:
        if root not in by_id:
            raise KeyError(f"Ticket {root} not found")
        roots = [root]
    else:
        roots = kids.get(None, [])

    # `pipe_flags` carries one bool per ancestor level *above* the current node,
    # in order from the outermost root down: True means that ancestor had more
    # siblings after it (draw "│  " for the continuation column), False means it
    # was the last child (draw "   "). The node itself contributes nothing to
    # `pipe_flags` until we recurse into its children.
    out: list[dict] = []

    def _emit(tid: str, depth: int, pipe_flags: list[bool], is_last: bool) -> None:
        pad = "".join("│  " if flag else "   " for flag in pipe_flags)
        if depth == 0:
            prefix = ""
        else:
            prefix = pad + ("└─ " if is_last else "├─ ")
        out.append({"ticket": by_id[tid], "depth": depth, "prefix": prefix})
        child_ids = kids.get(tid, [])
        # For the children's prefix: append a column reflecting whether *this*
        # node had a sibling after it. Roots don't add a column — the depth-0
        # row prints nothing in front of the title, so its children start at
        # column 0 too.
        if depth == 0:
            next_flags = pipe_flags
        else:
            next_flags = pipe_flags + [not is_last]
        for i, cid in enumerate(child_ids):
            _emit(cid, depth + 1, next_flags, i == len(child_ids) - 1)

    for i, rid in enumerate(roots):
        _emit(rid, 0, [], i == len(roots) - 1)

    return out
