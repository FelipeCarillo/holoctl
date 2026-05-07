"""Propose archiving memory topics that haven't been read in N days.

Detection: compare topic mtime against today minus N days. Read events
are not yet tracked (would need MCP-side instrumentation in 0.15+) — so
this is currently a coarse heuristic on file mtime.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

from ..curator import CuratorContext, Suggestion, hash_pattern


UNUSED_DAYS = 60


def run(ctx: CuratorContext) -> list[Suggestion]:
    out: list[Suggestion] = []
    if not ctx.memory.topics_dir.exists():
        return out
    cutoff = datetime.now(timezone.utc) - timedelta(days=UNUSED_DAYS)
    for topic_file in ctx.memory.topics_dir.glob("*.md"):
        if topic_file.name.startswith("_"):
            continue
        mtime = datetime.fromtimestamp(topic_file.stat().st_mtime, tz=timezone.utc)
        if mtime > cutoff:
            continue
        name = topic_file.stem
        # Don't suggest archiving session-trail (it's append-only by handoff).
        if name == "session-trail":
            continue
        pid = hash_pattern("unused_topic", name)
        out.append(Suggestion(
            pattern_id=pid,
            rule="unused_topic",
            title=f"Curate: archive memory topic '{name}' (untouched ≥{UNUSED_DAYS} days)",
            rationale=(
                f"Topic `{name}` was last modified more than {UNUSED_DAYS} days ago. "
                f"Archiving keeps the active set lean. The topic moves to "
                f"`topics/_archived/` — fully recoverable via `hctl memory list --archived`."
            ),
            action="topic_archive",
            args={"name": name},
            priority="p3",
        ))
    return out
