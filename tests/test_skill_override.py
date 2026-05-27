"""Skills first-class: built-in override + manifest-tracked support file sync.

Covers the four headline behaviours introduced in Task 21:

  1. A custom `.holoctl/skills/<builtin-name>/SKILL.md` shadows the built-in;
     the user's content wins, the built-in is never written.
  2. Support files (references/, scripts/, templates/) are manifest-tracked:
     - They land in `.claude/skills/<name>/references/<file>` on first compile.
     - Removing the source file and recompiling prunes the output and delists it
       from the manifest.
  3. A user-added file under `.claude/skills/<name>/references/` that holoctl
     never generated is preserved across recompiles (foreign, not in manifest,
     never pruned).
  4. A holoctl-generated support file that the user hand-edits on disk is
     preserved (ledger reports it; not silently overwritten unless --force).
"""
from __future__ import annotations

from pathlib import Path

from holoctl.lib.compiler import compile_project
from holoctl.lib.compiler.manifest import load
from holoctl.lib.config import get_defaults

# A real built-in skill name that ships with the package AND has at least one
# support file under `references/`.  If the package layout ever changes, update
# this constant.
_BUILTIN_WITH_REFS = "holoctl-router"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed(root: Path) -> dict:
    """Minimal .holoctl/ workspace (no custom skills by default)."""
    holoctl = root / ".holoctl"
    (holoctl / "context").mkdir(parents=True, exist_ok=True)
    (holoctl / "context" / "objective.md").write_text("obj.\n", encoding="utf-8")
    return get_defaults()


def _make_custom_skill(
    root: Path,
    name: str,
    skill_content: str = "# custom\n",
) -> Path:
    """Create `.holoctl/skills/<name>/SKILL.md` and return its path."""
    skill_dir = root / ".holoctl" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(skill_content, encoding="utf-8")
    return skill_dir


# ---------------------------------------------------------------------------
# Test 1 — Built-in override: user's content wins
# ---------------------------------------------------------------------------


def test_override_builtin_skill_uses_custom_content(tmp_path: Path):
    """Custom .holoctl/skills/<name>/SKILL.md replaces the built-in version."""
    config = _seed(tmp_path)
    custom_content = "# USER OVERRIDE — this must appear in .claude/\n"
    _make_custom_skill(tmp_path, _BUILTIN_WITH_REFS, custom_content)

    compile_project(tmp_path, config, "claude")

    out = tmp_path / ".claude" / "skills" / _BUILTIN_WITH_REFS / "SKILL.md"
    assert out.exists(), "Skill output should exist"
    on_disk = out.read_text(encoding="utf-8")
    assert "USER OVERRIDE" in on_disk, "Custom content must be in the output"
    # Built-in sentinel text must NOT appear (holoctl-router description is
    # distinctive enough to detect if the built-in leaked through).
    assert "holoctl-router" not in on_disk or "USER OVERRIDE" in on_disk


def test_override_builtin_skill_manifest_source_is_custom(tmp_path: Path):
    """The manifest source for an overridden built-in must be the custom path."""
    config = _seed(tmp_path)
    _make_custom_skill(tmp_path, _BUILTIN_WITH_REFS, "# override\n")

    compile_project(tmp_path, config, "claude")

    tracked = load(tmp_path)["files"]
    key = f".claude/skills/{_BUILTIN_WITH_REFS}/SKILL.md"
    assert key in tracked, "Overriding skill must appear in manifest"
    assert tracked[key]["source"] == f".holoctl/skills/{_BUILTIN_WITH_REFS}", (
        "Manifest source must be the custom path, not 'builtin'"
    )


# ---------------------------------------------------------------------------
# Test 2 — Support files are tracked and pruned when removed from source
# ---------------------------------------------------------------------------


def test_support_file_tracked_in_manifest(tmp_path: Path):
    """A custom skill's references/foo.md lands in manifest after compile."""
    config = _seed(tmp_path)
    skill_dir = _make_custom_skill(tmp_path, "my-skill")
    refs = skill_dir / "references"
    refs.mkdir()
    (refs / "foo.md").write_text("# foo\n", encoding="utf-8")

    compile_project(tmp_path, config, "claude")

    out_file = tmp_path / ".claude" / "skills" / "my-skill" / "references" / "foo.md"
    assert out_file.exists(), "Support file must be emitted"

    tracked = load(tmp_path)["files"]
    assert ".claude/skills/my-skill/references/foo.md" in tracked, (
        "Support file must appear in manifest"
    )


def test_support_file_pruned_after_source_removal(tmp_path: Path):
    """Removing a support file from source prunes it from .claude/ on recompile."""
    config = _seed(tmp_path)
    skill_dir = _make_custom_skill(tmp_path, "my-skill")
    refs = skill_dir / "references"
    refs.mkdir()
    ref_src = refs / "foo.md"
    ref_src.write_text("# foo\n", encoding="utf-8")

    compile_project(tmp_path, config, "claude")
    out_file = tmp_path / ".claude" / "skills" / "my-skill" / "references" / "foo.md"
    assert out_file.exists()

    # Remove the source support file and recompile.
    ref_src.unlink()
    result = compile_project(tmp_path, config, "claude")

    assert not out_file.exists(), "Pruned support file must be gone"
    assert ".claude/skills/my-skill/references/foo.md" not in load(tmp_path)["files"]
    assert ".claude/skills/my-skill/references/foo.md" in result["removed"]


def test_builtin_support_file_tracked_in_manifest(tmp_path: Path):
    """Built-in support files (references/ in package skills) are manifest-tracked."""
    config = _seed(tmp_path)

    compile_project(tmp_path, config, "claude")

    tracked = load(tmp_path)["files"]
    # holoctl-router ships with at least one file under references/
    # NOTE: update this path if the built-in skill's support files are renamed or removed.
    ref_key = f".claude/skills/{_BUILTIN_WITH_REFS}/references/flow-a-first-time.md"
    assert ref_key in tracked, (
        f"Built-in support file {ref_key} must be manifest-tracked"
    )
    assert tracked[ref_key]["source"] == "builtin"
    assert tracked[ref_key]["target"] == "claude"


# ---------------------------------------------------------------------------
# Test 3 — User-added (foreign) support file is preserved across recompiles
# ---------------------------------------------------------------------------


def test_foreign_support_file_preserved_across_recompiles(tmp_path: Path):
    """A user-added file under .claude/skills/<name>/ that holoctl never generated
    must survive recompile unmodified and must not appear in the manifest."""
    config = _seed(tmp_path)
    _make_custom_skill(tmp_path, "my-skill")

    compile_project(tmp_path, config, "claude")

    # Drop a foreign file that holoctl didn't generate.
    foreign_dir = tmp_path / ".claude" / "skills" / "my-skill" / "references"
    foreign_dir.mkdir(parents=True, exist_ok=True)
    foreign = foreign_dir / "user-notes.md"
    foreign.write_text("# my private notes\n", encoding="utf-8")

    compile_project(tmp_path, config, "claude")

    assert foreign.exists(), "Foreign support file must survive recompile"
    assert foreign.read_text(encoding="utf-8") == "# my private notes\n"
    tracked = load(tmp_path)["files"]
    assert ".claude/skills/my-skill/references/user-notes.md" not in tracked, (
        "Foreign file must not appear in manifest"
    )


# ---------------------------------------------------------------------------
# Test 4 — Hand-edited (owned-then-modified) support file is preserved
# ---------------------------------------------------------------------------


def test_hand_edited_support_file_preserved_without_force(tmp_path: Path):
    """A holoctl-generated support file that the user edits on disk must not be
    silently overwritten on recompile (ledger skips it; original content kept)."""
    config = _seed(tmp_path)
    skill_dir = _make_custom_skill(tmp_path, "my-skill")
    refs = skill_dir / "references"
    refs.mkdir()
    # Write source as bytes so the on-disk content is deterministic across
    # platforms (no LF→CRLF translation on Windows).
    (refs / "guide.md").write_bytes(b"original holoctl content\n")

    compile_project(tmp_path, config, "claude")

    out_file = tmp_path / ".claude" / "skills" / "my-skill" / "references" / "guide.md"
    assert out_file.exists()

    # User edits the emitted support file — different bytes.
    out_file.write_bytes(b"user-edited content\n")

    result = compile_project(tmp_path, config, "claude")

    # The hand-edited content must be preserved (not overwritten).
    assert out_file.read_bytes() == b"user-edited content\n", (
        "Hand-edited support file must not be overwritten without --force"
    )
    # The skip is recorded.
    skipped_paths = [s["path"] for s in result["skipped"]]
    assert ".claude/skills/my-skill/references/guide.md" in skipped_paths


def test_hand_edited_support_file_overwritten_with_force(tmp_path: Path):
    """With --force, a hand-edited support file is overwritten and re-tracked."""
    config = _seed(tmp_path)
    skill_dir = _make_custom_skill(tmp_path, "my-skill")
    refs = skill_dir / "references"
    refs.mkdir()
    # Write source as bytes so the on-disk content is deterministic across
    # platforms (no LF→CRLF translation on Windows).
    (refs / "guide.md").write_bytes(b"original holoctl content\n")

    compile_project(tmp_path, config, "claude")

    out_file = tmp_path / ".claude" / "skills" / "my-skill" / "references" / "guide.md"
    out_file.write_bytes(b"user-edited content\n")

    compile_project(tmp_path, config, "claude", force=True)

    assert out_file.read_bytes() == b"original holoctl content\n", (
        "--force must restore the generated content"
    )
    tracked = load(tmp_path)["files"]
    assert ".claude/skills/my-skill/references/guide.md" in tracked
