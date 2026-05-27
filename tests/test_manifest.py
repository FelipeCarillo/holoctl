"""Tests for compiler/manifest — manifest module + CompileLedger."""
from __future__ import annotations

import json
import time
from pathlib import Path

from holoctl.lib.compiler.manifest import (
    MANIFEST_REL,
    CompileLedger,
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
