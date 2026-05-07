"""Tests for holoctl.lib.memory — the durable cross-assistant memory tree."""
from __future__ import annotations

from pathlib import Path

import pytest

from holoctl.lib.memory import Memory, Topic, VALID_SCOPES


def test_ensure_seed_creates_memory_md(tmp_path: Path):
    mem = Memory(tmp_path)
    created = mem.ensure_seed("Acme")
    assert created is True
    assert mem.index_path.exists()
    body = mem.read_index()
    assert "Acme" in body
    assert "always-on" in body.lower()


def test_ensure_seed_idempotent(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.ensure_seed("Acme")
    again = mem.ensure_seed("Acme")
    assert again is False


def test_ensure_gitignore_default_archives_local(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.ensure_gitignore()
    gi = (mem.dir / ".gitignore").read_text(encoding="utf-8")
    assert "topics/_archived/" in gi


def test_add_topic_lazy_requires_description(tmp_path: Path):
    mem = Memory(tmp_path)
    with pytest.raises(ValueError, match="description"):
        mem.add_topic("foo", body="X", scope="lazy")


def test_add_topic_glob_requires_globs(tmp_path: Path):
    mem = Memory(tmp_path)
    with pytest.raises(ValueError, match="globs"):
        mem.add_topic("foo", body="X", scope="glob")


def test_add_topic_invalid_scope(tmp_path: Path):
    mem = Memory(tmp_path)
    with pytest.raises(ValueError, match="invalid scope"):
        mem.add_topic("foo", body="X", scope="banana", description="x")


def test_add_topic_lazy_writes_frontmatter(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.add_topic(
        "decisions",
        body="some content",
        scope="lazy",
        description="Architectural decisions",
    )
    path = mem.topics_dir / "decisions.md"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "scope: lazy" in content
    assert "Architectural decisions" in content


def test_add_topic_glob_writes_globs(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.add_topic(
        "api-conventions",
        body="x",
        scope="glob",
        globs=["src/api/**", "tests/api/**"],
    )
    text = (mem.topics_dir / "api-conventions.md").read_text(encoding="utf-8")
    assert "scope: glob" in text
    # Markdown serializer joins lists with ", "
    assert "src/api/**" in text
    assert "tests/api/**" in text


def test_add_topic_existing_refuses_without_overwrite(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.add_topic("a", body="x", scope="lazy", description="d")
    with pytest.raises(FileExistsError):
        mem.add_topic("a", body="y", scope="lazy", description="d2")


def test_add_topic_overwrite_replaces(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.add_topic("a", body="x", scope="lazy", description="d")
    mem.add_topic("a", body="y", scope="lazy", description="d2", overwrite=True)
    t = mem.get_topic("a")
    assert t is not None
    assert t.body.strip() == "y"
    assert t.description == "d2"


def test_list_topics_excludes_archived_by_default(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.add_topic("active", body="x", scope="lazy", description="d")
    mem.add_topic("old", body="y", scope="lazy", description="d")
    mem.archive_topic("old")
    names = [t.name for t in mem.list_topics()]
    assert names == ["active"]


def test_list_topics_includes_archived_on_request(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.add_topic("active", body="x", scope="lazy", description="d")
    mem.add_topic("old", body="y", scope="lazy", description="d")
    mem.archive_topic("old")
    names = [t.name for t in mem.list_topics(include_archived=True)]
    assert "active" in names
    assert any(n.startswith("_archived/") for n in names)


def test_archive_topic_moves_file(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.add_topic("a", body="x", scope="lazy", description="d")
    target = mem.archive_topic("a")
    assert not (mem.topics_dir / "a.md").exists()
    assert target.exists()
    assert "_archived" in str(target)


def test_archive_topic_missing_raises(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(FileNotFoundError):
        mem.archive_topic("never-existed")


def test_search_finds_in_index(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.write_index("# header\n\nThe quick brown fox\nover the lazy dog")
    hits = mem.search("brown")
    assert any("MEMORY" == h[0] and "brown" in h[1].lower() for h in hits)


def test_search_finds_in_topic(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.add_topic(
        "secrets-policy",
        body="never log credentials\nrotate every 90 days",
        scope="lazy",
        description="d",
    )
    hits = mem.search("rotate")
    assert any("secrets-policy" in h[0] for h in hits)


def test_get_topic_round_trip(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.add_topic(
        "x",
        body="line1\nline2",
        scope="glob",
        globs=["src/**"],
    )
    t = mem.get_topic("x")
    assert t is not None
    assert t.scope == "glob"
    assert t.globs == ["src/**"]
    assert "line1" in t.body
    assert "line2" in t.body


def test_get_topic_missing_returns_none(tmp_path: Path):
    mem = Memory(tmp_path)
    mem.dir.mkdir(parents=True, exist_ok=True)
    assert mem.get_topic("nope") is None


def test_topic_to_markdown_round_trip(tmp_path: Path):
    t = Topic(
        name="x",
        scope="lazy",
        description="A description",
        body="body content",
    )
    md = t.to_markdown()
    assert md.startswith("---\n")
    assert "scope: lazy" in md
    assert "description: A description" in md
    assert "body content" in md


def test_valid_scopes_constants():
    assert set(VALID_SCOPES) == {"always_on", "lazy", "glob"}
