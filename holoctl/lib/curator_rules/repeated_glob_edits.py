"""Detect N edits in the same glob across M sessions → propose path-scoped rule."""
from __future__ import annotations

import re
from collections import Counter

from ..curator import CuratorContext, Suggestion, hash_pattern


THRESHOLD_EDITS = 8
WINDOW_SESSIONS = 3
TOP_DIRS = 1  # how many top-loaded glob roots to suggest


def run(ctx: CuratorContext) -> list[Suggestion]:
    counts: Counter[str] = Counter()
    for r in ctx.journal.iter_records(kind="tool_use"):
        payload = r.get("payload") or {}
        path = payload.get("file") or payload.get("path")
        if not path:
            continue
        glob = _glob_for(path)
        if glob:
            counts[glob] += 1
    for r in ctx.journal.iter_records(kind="file_edit"):
        payload = r.get("payload") or {}
        path = payload.get("path") or payload.get("file")
        if not path:
            continue
        glob = _glob_for(path)
        if glob:
            counts[glob] += 1

    out: list[Suggestion] = []
    for glob, count in counts.most_common(TOP_DIRS):
        if count < THRESHOLD_EDITS:
            continue
        slug = _slugify(glob)
        pid = hash_pattern("repeated_glob_edits", glob)
        out.append(Suggestion(
            pattern_id=pid,
            rule="repeated_glob_edits",
            title=f"Curate: extract path-scoped rule for {glob} ({count} edits)",
            rationale=(
                f"You've edited files matching `{glob}` {count} times across "
                f"recent sessions. Extracting a memory topic with `scope=glob` "
                f"and `globs: [\"{glob}\"]` will surface conventions for that "
                f"area only when relevant — saving tokens elsewhere."
            ),
            action="rule_extract",
            args={
                "name": f"convention-{slug}",
                "globs": [glob],
                "body": f"# Conventions for `{glob}`\n\n(Add the conventions for this area here.)\n",
                "description": f"Path-scoped conventions for {glob}",
            },
            files=[],
        ))
    return out


def _glob_for(path: str) -> str | None:
    """Heuristic: top-2 directories of the path → ``a/b/**``."""
    p = path.replace("\\", "/").lstrip("./")
    parts = [seg for seg in p.split("/") if seg]
    if len(parts) < 2:
        return None
    if parts[0].startswith("."):
        return None
    return f"{parts[0]}/{parts[1]}/**"


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "glob"
