"""Project memory — the single source of durable, cross-assistant context.

The workspace owns one memory tree at ``.holoctl/memory/``:

    .holoctl/memory/
      MEMORY.md          <- always-on index, kept short (≤200 lines)
      topics/
        <name>.md        <- topic file with frontmatter declaring scope
        _archived/       <- moved here by `hctl memory archive`

Each topic .md has frontmatter declaring how it loads:

    ---
    scope: always_on | lazy | glob
    globs: ["src/api/**"]   # only when scope=glob
    description: "..."        # only when scope=lazy (model decides to read)
    ---

This frontmatter is the *canonical* description; the Claude compiler
translates it to native primitives:

  - Claude Code: skill description (lazy), CLAUDE.md import (always_on),
    skill ``paths:`` (glob).

Non-Claude assistants read this canonical frontmatter directly via the
``holoctl-foreign-bootstrap`` skill and map it to their own primitives.

Memory is **not auto-edited**. Writes go through ``hctl memory add`` (or the
curator in 0.14, after user approval of a ``meta:curate`` ticket).

Coexistence with Claude Code's native auto-memory (per the multi-assistant
plan, item 11): we do NOT disable it. The compiler emits a reference to
``.holoctl/memory/MEMORY.md`` in CLAUDE.md so Claude reads both, but it is
your decision whether the auto-memory keeps writing in parallel. Two sources
in parallel is acceptable; one wins on conflict via Claude's normal context
ordering.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .markdown import parse_frontmatter, serialize_frontmatter


VALID_SCOPES = ("always_on", "lazy", "glob")


@dataclass
class Topic:
    name: str
    scope: str = "lazy"
    description: str = ""
    globs: list[str] = field(default_factory=list)
    body: str = ""

    @property
    def frontmatter(self) -> dict:
        out: dict = {"scope": self.scope}
        if self.description:
            out["description"] = self.description
        if self.globs:
            out["globs"] = list(self.globs)
        return out

    def to_markdown(self) -> str:
        return serialize_frontmatter(self.frontmatter, self.body.lstrip("\n"))


class Memory:
    """Read/write API over ``.holoctl/memory/``.

    All paths are workspace-relative. Construction does not touch disk;
    methods are explicit about reads and writes.
    """

    def __init__(self, project_root: Path):
        self.root = Path(project_root)
        self.dir = self.root / ".holoctl" / "memory"
        self.topics_dir = self.dir / "topics"
        self.archived_dir = self.topics_dir / "_archived"

    # ---- index ----------------------------------------------------------

    @property
    def index_path(self) -> Path:
        return self.dir / "MEMORY.md"

    def read_index(self) -> str:
        if not self.index_path.exists():
            return ""
        return self.index_path.read_text(encoding="utf-8")

    def write_index(self, body: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(body, encoding="utf-8")

    def ensure_seed(self, project_name: str) -> bool:
        """Create the empty seed at MEMORY.md if absent. Returns True if created."""
        if self.index_path.exists():
            return False
        seed = (
            f"# {project_name} — Memory index\n"
            f"\n"
            f"This is the **always-on** memory layer for this workspace. Keep it\n"
            f"short — durable facts only, ≤ 200 lines. Detailed topics live as\n"
            f"separate files in `topics/` and are loaded lazily.\n"
            f"\n"
            f"## Topics\n"
            f"\n"
            f"_(Use `hctl memory list` to see all topics, `hctl memory add` to create one.)_\n"
        )
        self.write_index(seed)
        return True

    # ---- topics ---------------------------------------------------------

    def list_topics(self, *, include_archived: bool = False) -> list[Topic]:
        out: list[Topic] = []
        if not self.topics_dir.exists():
            return out
        for f in sorted(self.topics_dir.glob("*.md")):
            if f.name.startswith("_"):
                continue
            out.append(self._load_topic_from_path(f))
        if include_archived and self.archived_dir.exists():
            for f in sorted(self.archived_dir.glob("*.md")):
                t = self._load_topic_from_path(f)
                t.name = f"_archived/{t.name}"
                out.append(t)
        return out

    def get_topic(self, name: str) -> Topic | None:
        path = self.topics_dir / f"{name}.md"
        if not path.exists():
            archived = self.archived_dir / f"{name}.md"
            if archived.exists():
                return self._load_topic_from_path(archived)
            return None
        return self._load_topic_from_path(path)

    def add_topic(
        self,
        name: str,
        *,
        body: str,
        scope: str = "lazy",
        description: str = "",
        globs: Iterable[str] | None = None,
        overwrite: bool = False,
    ) -> Topic:
        if scope not in VALID_SCOPES:
            raise ValueError(
                f"invalid scope {scope!r}; must be one of {VALID_SCOPES}"
            )
        if scope == "glob" and not globs:
            raise ValueError("scope=glob requires at least one entry in `globs`")
        if scope == "lazy" and not description:
            raise ValueError(
                "scope=lazy requires a `description` so the model can decide"
                " when to load it"
            )
        path = self.topics_dir / f"{name}.md"
        if path.exists() and not overwrite:
            raise FileExistsError(
                f"topic {name!r} already exists — pass overwrite=True to replace"
            )
        topic = Topic(
            name=name,
            scope=scope,
            description=description,
            globs=list(globs or []),
            body=body,
        )
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(topic.to_markdown(), encoding="utf-8")
        return topic

    def archive_topic(self, name: str) -> Path:
        path = self.topics_dir / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"topic {name!r} not found")
        self.archived_dir.mkdir(parents=True, exist_ok=True)
        target = self.archived_dir / f"{name}.md"
        if target.exists():
            target.unlink()
        path.rename(target)
        return target

    def search(self, query: str) -> list[tuple[str, str]]:
        """Return [(topic_name, snippet_line), …] for lines containing query.

        Case-insensitive substring match. Includes the index. Cheap O(N) scan
        — good enough until 0.14 introduces optional embeddings.
        """
        q = query.lower()
        hits: list[tuple[str, str]] = []
        if self.index_path.exists():
            for line in self.read_index().splitlines():
                if q in line.lower():
                    hits.append(("MEMORY", line.strip()))
        for t in self.list_topics():
            for line in t.body.splitlines():
                if q in line.lower():
                    hits.append((t.name, line.strip()))
        return hits

    def ensure_gitignore(self) -> None:
        """Write a default ``.holoctl/memory/.gitignore`` if absent.

        By default everything in ``topics/`` is committed (durable, shareable)
        — but ``_archived/`` is local-only. Users can opt into a more
        privacy-strict policy by editing the file.
        """
        gi = self.dir / ".gitignore"
        if gi.exists():
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        gi.write_text(
            "# holoctl memory — defaults\n"
            "# Archived topics stay local; do not commit.\n"
            "topics/_archived/\n"
            "\n"
            "# Uncomment to make ALL memory local (privacy-strict workspaces):\n"
            "# *\n"
            "# !.gitignore\n",
            encoding="utf-8",
        )

    # ---- internals ------------------------------------------------------

    def _load_topic_from_path(self, path: Path) -> Topic:
        text = path.read_text(encoding="utf-8")
        data, body = parse_frontmatter(text)
        scope = str(data.get("scope") or "lazy")
        if scope not in VALID_SCOPES:
            scope = "lazy"
        globs_raw = data.get("globs")
        if isinstance(globs_raw, list):
            globs = [str(g) for g in globs_raw]
        elif isinstance(globs_raw, str) and globs_raw:
            globs = [g.strip() for g in globs_raw.split(",") if g.strip()]
        else:
            globs = []
        return Topic(
            name=path.stem,
            scope=scope,
            description=str(data.get("description") or ""),
            globs=globs,
            body=body.strip("\n"),
        )
