"""Tests for the generic discovery — non-code workspaces work too."""
from __future__ import annotations

from pathlib import Path

from holoctl.lib.discover import discover_repos


def _make_subdir(root: Path, name: str, *, files: list[str] | None = None) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    for f in files or []:
        (d / f).write_text("", encoding="utf-8")
    return d


def test_discovers_subdir_with_code_marker(tmp_path: Path):
    _make_subdir(tmp_path, "api", files=["pyproject.toml"])
    repos = discover_repos(tmp_path)
    assert [r["name"] for r in repos] == ["api"]
    assert "pyproject.toml" in repos[0]["markers"]


def test_discovers_subdir_with_only_readme(tmp_path: Path):
    """A markdown-only subdir (typical of personal-task workspaces like claudio/)
    must be discovered without requiring a code marker."""
    _make_subdir(tmp_path, "agriwave", files=["README.md", "notes.md"])
    repos = discover_repos(tmp_path)
    names = [r["name"] for r in repos]
    assert "agriwave" in names


def test_discovers_subdir_with_volume_only(tmp_path: Path):
    """A subdir with no marker but ≥5 non-skip files is treated as a unit
    (catches workspaces with content but no README yet)."""
    _make_subdir(
        tmp_path, "drafts",
        files=["a.md", "b.md", "c.md", "d.md", "e.md"],
    )
    repos = discover_repos(tmp_path)
    names = [r["name"] for r in repos]
    assert "drafts" in names


def test_skips_subdir_with_too_few_files_and_no_marker(tmp_path: Path):
    """Sparse subdirs with no README and no marker are not units."""
    _make_subdir(tmp_path, "empty-ish", files=["a.txt"])
    repos = discover_repos(tmp_path)
    names = [r["name"] for r in repos]
    assert "empty-ish" not in names


def test_skip_list_excludes_archive_and_trash(tmp_path: Path):
    """`_arquivados`, `descartar`, `tmp` etc. are excluded even with content."""
    for name in ("_arquivados", "descartar", "tmp", "_archive"):
        _make_subdir(
            tmp_path, name,
            files=["README.md", "a.md", "b.md", "c.md", "d.md"],
        )
    _make_subdir(tmp_path, "real-project", files=["README.md"])
    repos = discover_repos(tmp_path)
    names = [r["name"] for r in repos]
    assert names == ["real-project"]


def test_dotted_subdirs_are_skipped(tmp_path: Path):
    _make_subdir(tmp_path, ".cache", files=["README.md"])
    _make_subdir(tmp_path, ".vscode", files=["README.md"])
    _make_subdir(tmp_path, "real", files=["README.md"])
    repos = discover_repos(tmp_path)
    names = [r["name"] for r in repos]
    assert names == ["real"]


def test_mixed_workspace_finds_code_and_markdown(tmp_path: Path):
    """A workspace with both code projects and markdown projects (claudio +
    projctl side by side) lists both."""
    _make_subdir(tmp_path, "projctl", files=["pyproject.toml", "README.md"])
    _make_subdir(tmp_path, "agriwave", files=["README.md", "pitch.md"])
    repos = discover_repos(tmp_path)
    names = sorted(r["name"] for r in repos)
    assert names == ["agriwave", "projctl"]
