"""Tests for compiler/manifest — manifest module + CompileLedger."""
from __future__ import annotations

import json
import time
from pathlib import Path

from holoctl.lib.compiler.manifest import (
    MANIFEST_REL,
    CompileLedger,
    add_entries,
    load,
    manifest_path,
    save,
    sha256_bytes,
    sha256_text,
)

# ---------------------------------------------------------------------------
# 1. sha256_text
# ---------------------------------------------------------------------------


def test_sha256_text_deterministic():
    assert sha256_text("hello") == sha256_text("hello")


def test_sha256_text_differs_for_different_input():
    assert sha256_text("hello") != sha256_text("world")


def test_sha256_text_returns_hex_string():
    result = sha256_text("test")
    assert isinstance(result, str)
    assert len(result) == 64  # sha256 hex digest is 64 chars
    int(result, 16)  # must be valid hex


def test_sha256_bytes_deterministic():
    data = b"\x00\x01\x02\xff"
    assert sha256_bytes(data) == sha256_bytes(data)


def test_sha256_bytes_differs_for_different_input():
    assert sha256_bytes(b"abc") != sha256_bytes(b"xyz")


# ---------------------------------------------------------------------------
# 2. load — missing and corrupt files
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_default(tmp_path: Path):
    result = load(tmp_path)
    assert result == {"version": 1, "files": {}}


def test_load_corrupt_json_returns_default(tmp_path: Path):
    p = manifest_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("NOT VALID JSON {{{", encoding="utf-8")
    result = load(tmp_path)
    assert result == {"version": 1, "files": {}}


def test_load_partial_json_returns_default(tmp_path: Path):
    p = manifest_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"version": 1', encoding="utf-8")  # truncated
    result = load(tmp_path)
    assert result == {"version": 1, "files": {}}


def test_load_empty_file_returns_default(tmp_path: Path):
    p = manifest_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    result = load(tmp_path)
    assert result == {"version": 1, "files": {}}


# ---------------------------------------------------------------------------
# 2b. add_entries — merge new entries into the manifest (adoption hook)
# ---------------------------------------------------------------------------


def test_add_entries_into_empty_manifest(tmp_path: Path):
    add_entries(
        tmp_path,
        {".claude/agents/foo.md": {"sha256": "abc", "source": "s", "target": "claude"}},
        holoctl_version="0.20.0",
    )
    tracked = load(tmp_path)["files"]
    assert tracked == {
        ".claude/agents/foo.md": {"sha256": "abc", "source": "s", "target": "claude"}
    }


def test_add_entries_merges_and_preserves_existing(tmp_path: Path):
    save(
        tmp_path,
        {".claude/agents/dev.md": {"sha256": "old", "source": "s1", "target": "claude"}},
        holoctl_version="0.20.0",
    )
    add_entries(
        tmp_path,
        {".claude/commands/x.md": {"sha256": "new", "source": "s2", "target": "claude"}},
        holoctl_version="0.20.0",
    )
    tracked = load(tmp_path)["files"]
    # Existing entry preserved + new entry added.
    assert ".claude/agents/dev.md" in tracked
    assert ".claude/commands/x.md" in tracked


def test_add_entries_normalises_windows_keys(tmp_path: Path):
    add_entries(
        tmp_path,
        {".claude\\agents\\foo.md": {"sha256": "abc", "source": "s", "target": "claude"}},
        holoctl_version="0.20.0",
    )
    tracked = load(tmp_path)["files"]
    assert ".claude/agents/foo.md" in tracked


# ---------------------------------------------------------------------------
# 3. save / load round-trip
# ---------------------------------------------------------------------------


def test_save_load_roundtrip(tmp_path: Path):
    files = {
        ".claude/agents/dev.md": {"sha256": "abc123", "source": "src", "target": "tgt"},
        ".claude/CLAUDE.md": {"sha256": "def456", "source": "s2", "target": "t2"},
    }
    save(tmp_path, files, holoctl_version="0.20.0")
    result = load(tmp_path)
    assert result["version"] == 1
    assert result["files"] == files


def test_save_keys_are_sorted(tmp_path: Path):
    files = {
        "z-last.md": {"sha256": "zzz", "source": "s", "target": "t"},
        "a-first.md": {"sha256": "aaa", "source": "s", "target": "t"},
        "m-middle.md": {"sha256": "mmm", "source": "s", "target": "t"},
    }
    save(tmp_path, files, holoctl_version="0.20.0")
    raw = manifest_path(tmp_path).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    keys = list(parsed["files"].keys())
    assert keys == sorted(keys)


def test_save_trailing_newline(tmp_path: Path):
    save(tmp_path, {}, holoctl_version="0.20.0")
    raw = manifest_path(tmp_path).read_bytes()
    assert raw.endswith(b"\n")


def test_save_posix_keys_even_from_windows_paths(tmp_path: Path):
    # Simulate a Windows-style key passed in (backslash)
    files = {
        ".claude\\agents\\dev.md": {"sha256": "abc", "source": "s", "target": "t"},
    }
    save(tmp_path, files, holoctl_version="0.20.0")
    result = load(tmp_path)
    # The key must be stored as POSIX
    assert ".claude/agents/dev.md" in result["files"]
    assert ".claude\\agents\\dev.md" not in result["files"]


def test_save_includes_generated_and_version(tmp_path: Path):
    save(tmp_path, {}, holoctl_version="1.2.3")
    raw = json.loads(manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert raw["holoctlVersion"] == "1.2.3"
    assert "generated" in raw
    assert raw["generated"].endswith("Z")


# ---------------------------------------------------------------------------
# 4. CompileLedger.write — new file
# ---------------------------------------------------------------------------


def test_ledger_write_creates_new_file(tmp_path: Path):
    ledger = CompileLedger(tmp_path)
    result = ledger.write(".claude/CLAUDE.md", "hello world", source="src", target="tgt")
    assert result is True
    assert (tmp_path / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "hello world"
    assert ".claude/CLAUDE.md" in ledger.written


def test_ledger_write_creates_parent_dirs(tmp_path: Path):
    ledger = CompileLedger(tmp_path)
    ledger.write(".claude/agents/sub/dev.md", "content", source="s", target="t")
    assert (tmp_path / ".claude" / "agents" / "sub" / "dev.md").exists()


def test_ledger_write_records_sha256(tmp_path: Path):
    ledger = CompileLedger(tmp_path)
    content = "some content"
    ledger.write(".claude/test.md", content, source="s", target="t")
    assert ledger.written[".claude/test.md"]["sha256"] == sha256_text(content)


# ---------------------------------------------------------------------------
# 5. write idempotent — same content keeps ownership
# ---------------------------------------------------------------------------


def test_ledger_write_idempotent_same_content(tmp_path: Path):
    # First ledger writes the file.
    ledger1 = CompileLedger(tmp_path)
    ledger1.write(".claude/test.md", "content", source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    # Second ledger sees same content -> still returns True, file still in written.
    ledger2 = CompileLedger(tmp_path)
    result = ledger2.write(".claude/test.md", "content", source="s", target="t")
    assert result is True
    assert ".claude/test.md" in ledger2.written


# ---------------------------------------------------------------------------
# 6. Hand-edit preserved
# ---------------------------------------------------------------------------


def test_ledger_write_preserves_hand_edited_file(tmp_path: Path):
    # First ledger creates and records the file.
    ledger1 = CompileLedger(tmp_path)
    ledger1.write(".claude/test.md", "original content", source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    # Simulate hand-edit.
    (tmp_path / ".claude" / "test.md").write_text("HAND EDITED", encoding="utf-8")

    # Second ledger with different content -> should NOT overwrite.
    ledger2 = CompileLedger(tmp_path)
    result = ledger2.write(".claude/test.md", "new compiler output", source="s", target="t")
    assert result is False
    # File on disk still has hand-edited content.
    assert (tmp_path / ".claude" / "test.md").read_text(encoding="utf-8") == "HAND EDITED"
    # Not in written.
    assert ".claude/test.md" not in ledger2.written
    # In skipped.
    assert any(e["path"] == ".claude/test.md" for e in ledger2.skipped)


# ---------------------------------------------------------------------------
# 7. Foreign file preserved
# ---------------------------------------------------------------------------


def test_ledger_write_preserves_foreign_file(tmp_path: Path):
    # Create a file that was never in any manifest.
    target = tmp_path / ".claude" / "test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("I was created by someone else", encoding="utf-8")

    ledger = CompileLedger(tmp_path)
    result = ledger.write(".claude/test.md", "compiler output", source="s", target="t")
    assert result is False
    assert target.read_text(encoding="utf-8") == "I was created by someone else"
    assert ".claude/test.md" not in ledger.written
    assert any(e["path"] == ".claude/test.md" for e in ledger.skipped)


# ---------------------------------------------------------------------------
# 8. force=True overwrites hand-edited / foreign
# ---------------------------------------------------------------------------


def test_ledger_force_overwrites_hand_edited(tmp_path: Path):
    # Write original and finalize.
    ledger1 = CompileLedger(tmp_path)
    ledger1.write(".claude/test.md", "original", source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    # Hand-edit.
    (tmp_path / ".claude" / "test.md").write_text("HAND EDITED", encoding="utf-8")

    # Force overwrite.
    ledger2 = CompileLedger(tmp_path, force=True)
    result = ledger2.write(".claude/test.md", "new compiler output", source="s", target="t")
    assert result is True
    assert (tmp_path / ".claude" / "test.md").read_text(encoding="utf-8") == "new compiler output"
    assert ".claude/test.md" in ledger2.written


def test_ledger_force_overwrites_foreign_file(tmp_path: Path):
    target = tmp_path / ".claude" / "foreign.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("foreign content", encoding="utf-8")

    ledger = CompileLedger(tmp_path, force=True)
    result = ledger.write(".claude/foreign.md", "our content", source="s", target="t")
    assert result is True
    assert target.read_text(encoding="utf-8") == "our content"
    assert ".claude/foreign.md" in ledger.written


# ---------------------------------------------------------------------------
# 9. prune_orphans
# ---------------------------------------------------------------------------


def test_prune_orphans_deletes_unmodified(tmp_path: Path):
    # Write a file and finalize.
    ledger1 = CompileLedger(tmp_path)
    ledger1.write(".claude/orphan.md", "old content", source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    # New ledger does NOT write orphan.md -> it should be pruned.
    ledger2 = CompileLedger(tmp_path)
    ledger2.prune_orphans()
    assert not (tmp_path / ".claude" / "orphan.md").exists()
    assert ".claude/orphan.md" in ledger2.removed


def test_prune_orphans_does_not_delete_diverged(tmp_path: Path):
    # Write and finalize.
    ledger1 = CompileLedger(tmp_path)
    ledger1.write(".claude/diverged.md", "original", source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    # Mutate the file on disk (simulate hand-edit of a file holoctl previously owned).
    (tmp_path / ".claude" / "diverged.md").write_text("hand-modified", encoding="utf-8")

    # New ledger doesn't write this file -> prune_orphans should NOT delete it.
    ledger2 = CompileLedger(tmp_path)
    ledger2.prune_orphans()
    assert (tmp_path / ".claude" / "diverged.md").exists()
    assert ".claude/diverged.md" not in ledger2.removed
    assert any(e["path"] == ".claude/diverged.md" for e in ledger2.skipped)


def test_prune_orphans_no_error_if_already_missing(tmp_path: Path):
    # Write and finalize.
    ledger1 = CompileLedger(tmp_path)
    ledger1.write(".claude/gone.md", "content", source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    # Manually delete the file (simulating external deletion).
    (tmp_path / ".claude" / "gone.md").unlink()

    # prune_orphans should not raise.
    ledger2 = CompileLedger(tmp_path)
    ledger2.prune_orphans()  # Must not raise
    # No error; the orphan is gone already, that's fine.


# ---------------------------------------------------------------------------
# 10. finalize — correct counts + churn-avoidance
# ---------------------------------------------------------------------------


def test_finalize_returns_correct_counts(tmp_path: Path):
    # Create a foreign file to exercise "preserved" count.
    foreign = tmp_path / ".claude" / "foreign.md"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("foreign", encoding="utf-8")

    ledger = CompileLedger(tmp_path)
    ledger.write(".claude/new.md", "new content", source="s", target="t")
    ledger.write(".claude/foreign.md", "compiler output", source="s", target="t")  # preserved
    summary = ledger.finalize(holoctl_version="0.20.0")
    assert summary["written"] == 1
    assert summary["preserved"] == 1
    assert summary["removed"] == 0


def test_finalize_writes_manifest(tmp_path: Path):
    ledger = CompileLedger(tmp_path)
    ledger.write(".claude/test.md", "content", source="s", target="t")
    ledger.finalize(holoctl_version="0.20.0")
    assert manifest_path(tmp_path).exists()
    data = load(tmp_path)
    assert ".claude/test.md" in data["files"]


def test_finalize_churn_avoidance_skips_rewrite(tmp_path: Path):
    """If written == prev and manifest exists, finalize must not rewrite."""
    ledger1 = CompileLedger(tmp_path)
    ledger1.write(".claude/test.md", "content", source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    mtime_before = manifest_path(tmp_path).stat().st_mtime

    # Sleep a tiny bit to ensure mtime would differ if rewritten.
    time.sleep(0.05)

    # Second run produces identical written set.
    ledger2 = CompileLedger(tmp_path)
    ledger2.write(".claude/test.md", "content", source="s", target="t")
    ledger2.finalize(holoctl_version="0.20.0")

    mtime_after = manifest_path(tmp_path).stat().st_mtime
    assert mtime_after == mtime_before, "manifest was unnecessarily rewritten (churn)"


# ---------------------------------------------------------------------------
# 11. dry_run=True — nothing touches disk
# ---------------------------------------------------------------------------


def test_dry_run_write_does_not_create_file(tmp_path: Path):
    ledger = CompileLedger(tmp_path, dry_run=True)
    result = ledger.write(".claude/test.md", "content", source="s", target="t")
    assert result is True
    assert not (tmp_path / ".claude" / "test.md").exists()
    # Still recorded in written.
    assert ".claude/test.md" in ledger.written


def test_dry_run_prune_orphans_does_not_delete(tmp_path: Path):
    # Write and finalize normally first.
    ledger1 = CompileLedger(tmp_path)
    ledger1.write(".claude/toprune.md", "content", source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    # Dry-run ledger does NOT write toprune.md -> prune_orphans should NOT delete.
    ledger2 = CompileLedger(tmp_path, dry_run=True)
    ledger2.prune_orphans()
    assert (tmp_path / ".claude" / "toprune.md").exists()
    assert ".claude/toprune.md" in ledger2.removed  # intention recorded


def test_dry_run_finalize_does_not_write_manifest(tmp_path: Path):
    ledger = CompileLedger(tmp_path, dry_run=True)
    ledger.write(".claude/test.md", "content", source="s", target="t")
    ledger.finalize(holoctl_version="0.20.0")
    assert not manifest_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# 12. write_bytes — round-trip + ownership for binary
# ---------------------------------------------------------------------------


def test_write_bytes_creates_file(tmp_path: Path):
    src = tmp_path / "source.bin"
    data = b"\x00\x01\x02\xfe\xff binary data"
    src.write_bytes(data)

    ledger = CompileLedger(tmp_path)
    result = ledger.write_bytes(".claude/support/file.bin", src, source="s", target="t")
    assert result is True
    assert (tmp_path / ".claude" / "support" / "file.bin").read_bytes() == data
    assert ".claude/support/file.bin" in ledger.written
    assert ledger.written[".claude/support/file.bin"]["sha256"] == sha256_bytes(data)


def test_write_bytes_preserves_foreign_binary(tmp_path: Path):
    # Place a foreign binary file.
    target = tmp_path / ".claude" / "support" / "file.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"foreign binary")

    src = tmp_path / "source.bin"
    src.write_bytes(b"our binary content")

    ledger = CompileLedger(tmp_path)
    result = ledger.write_bytes(".claude/support/file.bin", src, source="s", target="t")
    assert result is False
    assert target.read_bytes() == b"foreign binary"
    assert ".claude/support/file.bin" not in ledger.written
    assert any(e["path"] == ".claude/support/file.bin" for e in ledger.skipped)


def test_write_bytes_idempotent(tmp_path: Path):
    data = b"binary data"
    src = tmp_path / "source.bin"
    src.write_bytes(data)

    # Write and finalize.
    ledger1 = CompileLedger(tmp_path)
    ledger1.write_bytes(".claude/support/file.bin", src, source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    # Second run: file owned and unmodified -> still writes (returns True).
    ledger2 = CompileLedger(tmp_path)
    result = ledger2.write_bytes(".claude/support/file.bin", src, source="s", target="t")
    assert result is True
    assert ".claude/support/file.bin" in ledger2.written


def test_write_bytes_hand_edit_preserved(tmp_path: Path):
    data = b"original binary"
    src = tmp_path / "source.bin"
    src.write_bytes(data)

    # Write and finalize.
    ledger1 = CompileLedger(tmp_path)
    ledger1.write_bytes(".claude/support/file.bin", src, source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    # Mutate on disk (simulating hand-edit of binary).
    (tmp_path / ".claude" / "support" / "file.bin").write_bytes(b"mutated")

    # New ledger should not overwrite.
    ledger2 = CompileLedger(tmp_path)
    result = ledger2.write_bytes(".claude/support/file.bin", src, source="s", target="t")
    assert result is False
    assert (tmp_path / ".claude" / "support" / "file.bin").read_bytes() == b"mutated"
    assert ".claude/support/file.bin" not in ledger2.written


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


def test_manifest_path_returns_correct_location(tmp_path: Path):
    p = manifest_path(tmp_path)
    assert p == tmp_path / Path(MANIFEST_REL)


def test_ledger_prev_populated_from_previous_manifest(tmp_path: Path):
    ledger1 = CompileLedger(tmp_path)
    ledger1.write(".claude/test.md", "content", source="s", target="t")
    ledger1.finalize(holoctl_version="0.20.0")

    ledger2 = CompileLedger(tmp_path)
    assert ".claude/test.md" in ledger2.prev


def test_write_normalizes_backslash_key(tmp_path: Path):
    """Keys passed with backslashes (Windows paths) are normalized to POSIX."""
    ledger = CompileLedger(tmp_path)
    # Write using backslash-style key.
    result = ledger.write(".claude\\agents\\dev.md", "content", source="s", target="t")
    assert result is True
    assert ".claude/agents/dev.md" in ledger.written
    assert ".claude\\agents\\dev.md" not in ledger.written


# ---------------------------------------------------------------------------
# 13. Legacy adoption — migrate pre-manifest headered files
# ---------------------------------------------------------------------------

_LEGACY_MARKER = "<!-- Generated by holoctl"
_LEGACY_HEADER = "<!-- Generated by holoctl. Do not edit directly. Source: .holoctl/ -->\n\n"


def test_legacy_file_is_adopted_and_overwritten_clean(tmp_path: Path):
    """A headered file not in the manifest → adopted (overwritten clean), tracked,
    listed in migrated, NOT in skipped."""
    target = tmp_path / ".claude" / "agents" / "dev.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_LEGACY_HEADER + "old body\n", encoding="utf-8")

    ledger = CompileLedger(tmp_path, legacy_marker=_LEGACY_MARKER)
    result = ledger.write(".claude/agents/dev.md", "clean body\n", source="s", target="claude")

    assert result is True
    # Overwritten clean (no header).
    on_disk = target.read_text(encoding="utf-8")
    assert "Generated by holoctl" not in on_disk
    assert on_disk == "clean body\n"
    # Tracked + migrated, not skipped.
    assert ".claude/agents/dev.md" in ledger.written
    assert ".claude/agents/dev.md" in ledger.migrated
    assert not any(e["path"] == ".claude/agents/dev.md" for e in ledger.skipped)


def test_legacy_marker_after_frontmatter_is_adopted(tmp_path: Path):
    """The marker may sit just after YAML frontmatter (skills) — still adopted."""
    target = tmp_path / ".claude" / "skills" / "x" / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nname: x\ndescription: y\n---\n\n" + _LEGACY_HEADER + "body\n",
        encoding="utf-8",
    )
    ledger = CompileLedger(tmp_path, legacy_marker=_LEGACY_MARKER)
    result = ledger.write(".claude/skills/x/SKILL.md", "clean\n", source="s", target="claude")
    assert result is True
    assert ".claude/skills/x/SKILL.md" in ledger.migrated


def test_non_marker_foreign_file_is_not_adopted(tmp_path: Path):
    """A foreign file WITHOUT the legacy marker is preserved, never adopted."""
    target = tmp_path / ".claude" / "agents" / "foo.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# hand written, no marker\n", encoding="utf-8")

    ledger = CompileLedger(tmp_path, legacy_marker=_LEGACY_MARKER)
    result = ledger.write(".claude/agents/foo.md", "compiler output\n", source="s", target="claude")

    assert result is False
    assert target.read_text(encoding="utf-8") == "# hand written, no marker\n"
    assert ".claude/agents/foo.md" not in ledger.written
    assert ".claude/agents/foo.md" not in ledger.migrated
    assert any(e["path"] == ".claude/agents/foo.md" for e in ledger.skipped)


def test_legacy_not_adopted_without_marker_configured(tmp_path: Path):
    """If no legacy_marker is configured, a headered file is just foreign."""
    target = tmp_path / ".claude" / "agents" / "dev.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_LEGACY_HEADER + "old\n", encoding="utf-8")

    ledger = CompileLedger(tmp_path)  # no legacy_marker
    result = ledger.write(".claude/agents/dev.md", "new\n", source="s", target="claude")
    assert result is False
    assert ".claude/agents/dev.md" not in ledger.migrated


def test_is_owned_text_and_is_legacy_predicates(tmp_path: Path):
    # First compile records ownership.
    ledger1 = CompileLedger(tmp_path, target="claude")
    ledger1.write(".claude/a.md", "content", source="s", target="claude")
    ledger1.finalize(holoctl_version="0.20.0")

    ledger2 = CompileLedger(tmp_path, target="claude", legacy_marker=_LEGACY_MARKER)
    assert ledger2.is_owned_text(".claude/a.md") is True
    assert ledger2.is_legacy(".claude/a.md") is False  # tracked, so not legacy

    # A headered, untracked file is legacy.
    legacy = tmp_path / ".claude" / "b.md"
    legacy.write_text(_LEGACY_HEADER + "x\n", encoding="utf-8")
    assert ledger2.is_legacy(".claude/b.md") is True
    assert ledger2.is_owned_text(".claude/b.md") is False


def test_record_text_does_not_write_disk(tmp_path: Path):
    ledger = CompileLedger(tmp_path, target="claude")
    ledger.record_text("CLAUDE.md", "hello", source="s", target="claude")
    # Recorded but nothing written.
    assert "CLAUDE.md" in ledger.written
    assert ledger.written["CLAUDE.md"]["sha256"] == sha256_text("hello")
    assert not (tmp_path / "CLAUDE.md").exists()


# ---------------------------------------------------------------------------
# 14. Target-scoped prune + merge-preserving finalize
# ---------------------------------------------------------------------------


def test_prune_leaves_other_target_files_alone(tmp_path: Path):
    """A claude-scoped prune must not touch an agents-target file."""
    # Seed a manifest with both targets via two ledgers.
    lc = CompileLedger(tmp_path, target="claude")
    lc.write(".claude/agents/dev.md", "c", source="s", target="claude")
    lc.finalize(holoctl_version="0.20.0")
    la = CompileLedger(tmp_path, target="agents")
    la.write("AGENTS.md", "a", source="s", target="agents")
    la.finalize(holoctl_version="0.20.0")

    # Now a claude run that writes nothing: it must prune the claude orphan but
    # leave the agents file (and its on-disk content) untouched.
    lc2 = CompileLedger(tmp_path, target="claude")
    lc2.prune_orphans()
    assert ".claude/agents/dev.md" in lc2.removed  # claude orphan pruned
    assert not (tmp_path / ".claude" / "agents" / "dev.md").exists()
    assert (tmp_path / "AGENTS.md").exists()        # agents file untouched
    assert "AGENTS.md" not in lc2.removed
    assert not any(e["path"] == "AGENTS.md" for e in lc2.skipped)


def test_finalize_merges_other_target_entries(tmp_path: Path):
    """A claude finalize must keep prev agents-target entries in the manifest."""
    lc = CompileLedger(tmp_path, target="claude")
    lc.write(".claude/x.md", "c", source="s", target="claude")
    lc.finalize(holoctl_version="0.20.0")
    la = CompileLedger(tmp_path, target="agents")
    la.write("AGENTS.md", "a", source="s", target="agents")
    la.finalize(holoctl_version="0.20.0")

    # Recompile claude only: agents entry must survive in the saved manifest.
    lc2 = CompileLedger(tmp_path, target="claude")
    lc2.write(".claude/x.md", "c", source="s", target="claude")
    lc2.finalize(holoctl_version="0.20.0")

    files = load(tmp_path)["files"]
    assert ".claude/x.md" in files
    assert "AGENTS.md" in files  # merged, not dropped
    assert files["AGENTS.md"]["target"] == "agents"


def test_finalize_target_none_does_not_keep_foreign(tmp_path: Path):
    """With target=None (legacy single-target), finalize is authoritative —
    it does not preserve other-target prev entries (back-compat)."""
    # Seed a manifest with an entry tagged for some target.
    save(tmp_path, {"AGENTS.md": {"sha256": "x", "source": "s", "target": "agents"}},
         holoctl_version="0.20.0")
    ledger = CompileLedger(tmp_path)  # target=None
    ledger.write(".claude/x.md", "c", source="s", target="claude")
    ledger.finalize(holoctl_version="0.20.0")
    files = load(tmp_path)["files"]
    assert ".claude/x.md" in files
    assert "AGENTS.md" not in files  # not preserved when target is None


def test_finalize_reports_migrated_count(tmp_path: Path):
    target = tmp_path / ".claude" / "dev.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_LEGACY_HEADER + "old\n", encoding="utf-8")
    ledger = CompileLedger(tmp_path, target="claude", legacy_marker=_LEGACY_MARKER)
    ledger.write(".claude/dev.md", "new\n", source="s", target="claude")
    summary = ledger.finalize(holoctl_version="0.20.0")
    assert summary["migrated"] == 1
