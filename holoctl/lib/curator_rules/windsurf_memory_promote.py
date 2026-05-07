"""Read Cascade auto-memories and propose promoting them to durable topics.

Cascade writes auto-generated memories to ``~/.codeium/windsurf/memories/``
that are workspace-local and not committed. The Windsurf docs explicitly
recommend moving anything durable to ``.windsurf/rules/`` (which is what
holoctl already does for its own memory tree). This rule looks at those
auto-memories and proposes promoting them to ``.holoctl/memory/topics/``
versioned topics — closing the loop the docs describe.

Trigger: a memory file that's been around for ≥ N sessions without being
edited (proxy: file mtime older than threshold).
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ..curator import CuratorContext, Suggestion, hash_pattern


PROMOTE_AFTER_DAYS = 7


def _windsurf_memories_dir() -> Path:
    if sys.platform == "win32":
        # %USERPROFILE%\.codeium\windsurf\memories
        return Path.home() / ".codeium" / "windsurf" / "memories"
    return Path.home() / ".codeium" / "windsurf" / "memories"


def run(ctx: CuratorContext) -> list[Suggestion]:
    d = _windsurf_memories_dir()
    if not d.exists():
        return []
    out: list[Suggestion] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=PROMOTE_AFTER_DAYS)
    for memory_file in d.glob("*.md"):
        # Skip the global_rules.md — that's user-authored, not auto-memory.
        if memory_file.name == "global_rules.md":
            continue
        mtime = datetime.fromtimestamp(memory_file.stat().st_mtime, tz=timezone.utc)
        if mtime > cutoff:
            continue
        try:
            body = memory_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if not body.strip():
            continue
        slug = _slugify(memory_file.stem)
        pid = hash_pattern("windsurf_memory_promote", slug)
        out.append(Suggestion(
            pattern_id=pid,
            rule="windsurf_memory_promote",
            title=f"Curate: promote Cascade memory '{memory_file.stem}' to versioned topic",
            rationale=(
                f"Cascade auto-generated this memory more than {PROMOTE_AFTER_DAYS} "
                f"days ago and it's still around — a strong signal it's durable. "
                f"The Windsurf docs recommend moving such memories to "
                f"`.windsurf/rules/` (versioned). holoctl will mirror that to "
                f"`.holoctl/memory/topics/{slug}.md` so all 5 assistants benefit."
            ),
            action="memory_promote",
            args={
                "name": slug,
                "body": body,
                "description": f"Promoted from Cascade auto-memory '{memory_file.stem}'",
            },
            priority="p3",
        ))
    return out


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "memory"
