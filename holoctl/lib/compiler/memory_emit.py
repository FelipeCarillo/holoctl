"""Per-target memory emission.

Each function reads the canonical memory tree at ``.holoctl/memory/`` and
writes target-native files. The functions are pure: they take a project
root + topics list + flags and return a list of relative paths written.

Coexistence with Claude Code's auto-memory (item 11 of the multi-assistant
plan): we do NOT toggle ``autoMemoryEnabled`` here. We simply add a
reference to ``.holoctl/memory/MEMORY.md`` in CLAUDE.md so Claude reads
both sources. If the user wants to disable native auto-memory, that's an
explicit setting they tweak themselves.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..memory import Memory, Topic

if TYPE_CHECKING:
    from .manifest import CompileLedger


def _slug(name: str) -> str:
    return name.replace("_archived/", "").replace("/", "-")


def _topic_body_for_emission(topic: Topic) -> str:
    """Serialize a topic body without the canonical frontmatter — target-specific
    frontmatter is added by each emitter."""
    return topic.body.strip("\n") + "\n"


def emit_claude(
    project_root: Path,
    ledger: CompileLedger,
    dry_run: bool = False,
) -> list[str]:
    """Emit memory as Claude Code skills.

    - MEMORY.md (always-on): copied verbatim to ``.claude/skills/holoctl-memory/SKILL.md``
      with ``description: "Workspace memory index — always relevant."``.
    - Each topic with ``scope: lazy``: emit ``.claude/skills/holoctl-memory-<topic>/SKILL.md``
      with the topic's description. Claude decides when to read.
    - Each topic with ``scope: glob``: emit same skill location + ``paths:``
      frontmatter pointing to the globs.
    - Each topic with ``scope: always_on``: append a section to the index skill.

    All SKILL.md files are headerless and routed through *ledger* so they are
    manifest-tracked (clean output + hand-edit protection + orphan pruning).
    """
    mem = Memory(project_root)
    if not mem.dir.exists():
        return []
    written: list[str] = []

    index_body = mem.read_index()
    if index_body:
        rel = ".claude/skills/holoctl-memory/SKILL.md"
        body = (
            "---\n"
            "name: holoctl-memory\n"
            'description: "Workspace memory index — durable cross-assistant context. '
            'Read at session start to load durable facts."\n'
            "---\n\n"
            f"{index_body}"
        )
        if ledger.write(rel, body, source="memory", target="claude"):
            written.append(rel)

    for topic in mem.list_topics():
        slug = _slug(topic.name)
        rel = f".claude/skills/holoctl-memory-{slug}/SKILL.md"
        if topic.scope == "always_on":
            description = (
                topic.description
                or f"Workspace memory topic '{slug}' — always-on context."
            )
        elif topic.scope == "glob":
            description = (
                topic.description
                or f"Workspace memory topic '{slug}' — relevant when editing "
                + ", ".join(topic.globs)
            )
        else:
            description = (
                topic.description
                or f"Workspace memory topic '{slug}' (lazy)"
            )
        front_lines = [
            "---",
            f"name: holoctl-memory-{slug}",
            f'description: "{_escape_quotes(description)}"',
        ]
        if topic.scope == "glob" and topic.globs:
            front_lines.append("paths:")
            for g in topic.globs:
                front_lines.append(f"  - {g}")
        front_lines.append("---")
        body = (
            "\n".join(front_lines)
            + "\n\n"
            + _topic_body_for_emission(topic)
        )
        if ledger.write(rel, body, source="memory", target="claude"):
            written.append(rel)

    return written


# ---- helpers --------------------------------------------------------------


def _escape_quotes(s: str) -> str:
    return s.replace('"', '\\"')


def claude_memory_reference_block() -> str:
    """The block appended to CLAUDE.md so the model knows about memory.

    Coexists with native auto-memory: we just add a pointer; Claude reads
    both. If the user wants to disable native auto-memory, that's their call.
    """
    return (
        "\n\n## Workspace memory (durable, cross-assistant)\n\n"
        "This workspace has structured memory at `.holoctl/memory/` with an\n"
        "always-on index (`MEMORY.md`) and lazy topics. Treat it as the\n"
        "**durable** memory for the project — auto-memory is fine for\n"
        "ephemeral notes but anything important should land here via\n"
        "`hctl memory add`.\n"
        "\n"
        "- Index: @.holoctl/memory/MEMORY.md\n"
        "- Topics directory: `.holoctl/memory/topics/`\n"
        "- List/search: `hctl memory list`, `hctl memory search <q>`\n"
    )
