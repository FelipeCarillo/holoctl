"""Tests for holoctl.lib.discover — workspace subproject auto-discovery."""
from __future__ import annotations
from pathlib import Path

from holoctl.lib.discover import discover_repos, PROJECT_MARKERS, SKIP_NAMES


def test_empty_workspace_returns_empty_list(tmp_path: Path):
    assert discover_repos(tmp_path) == []


def test_detects_subdir_with_git(tmp_path: Path):
    (tmp_path / "app" / ".git").mkdir(parents=True)
    repos = discover_repos(tmp_path)
    assert len(repos) == 1
    assert repos[0]["name"] == "app"
    assert ".git" in repos[0]["markers"]


def test_detects_each_known_marker(tmp_path: Path, make_marker):
    """Every marker in PROJECT_MARKERS should make its parent dir a repo."""
    for i, marker in enumerate(PROJECT_MARKERS):
        if marker == ".git":
            (tmp_path / f"sub{i}" / marker).mkdir(parents=True)
        else:
            make_marker(tmp_path / f"sub{i}", marker)
    repos = discover_repos(tmp_path)
    assert len(repos) == len(PROJECT_MARKERS)


def test_subdir_without_marker_is_ignored(tmp_path: Path):
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "main.tf").write_text("", encoding="utf-8")
    repos = discover_repos(tmp_path)
    assert repos == []


def test_skip_list_excludes_well_known_dirs(tmp_path: Path, make_marker):
    """Even if a skip-listed dir has a marker, it must not appear."""
    for skipped in ["node_modules", "__pycache__", ".venv", "dist"]:
        make_marker(tmp_path / skipped, "package.json")
    make_marker(tmp_path / "good", "package.json")
    repos = discover_repos(tmp_path)
    assert [r["name"] for r in repos] == ["good"]


def test_hidden_dirs_other_than_git_are_skipped(tmp_path: Path, make_marker):
    """Dirs starting with `.` (except `.git`) shouldn't be scanned."""
    make_marker(tmp_path / ".idea", "package.json")
    make_marker(tmp_path / "app", "package.json")
    repos = discover_repos(tmp_path)
    assert [r["name"] for r in repos] == ["app"]


def test_files_at_root_are_not_repos(tmp_path: Path):
    """Top-level files (even with marker names) should not appear as repos."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "README.md").write_text("", encoding="utf-8")
    repos = discover_repos(tmp_path)
    assert repos == []


def test_repos_sorted_by_name(tmp_path: Path, make_marker):
    for name in ["zebra", "alpha", "mike"]:
        make_marker(tmp_path / name, "package.json")
    names = [r["name"] for r in discover_repos(tmp_path)]
    assert names == ["alpha", "mike", "zebra"]


def test_manual_override_renames_discovered_repo(tmp_path: Path, make_marker):
    make_marker(tmp_path / "app", "package.json")
    repos = discover_repos(
        tmp_path,
        include_manual=[{"name": "frontend-app", "path": "app", "description": "UI"}],
    )
    assert len(repos) == 1
    assert repos[0]["name"] == "frontend-app"
    assert repos[0]["description"] == "UI"
    assert repos[0]["source"] == "auto+manual"


def test_manual_adds_subdir_without_marker(tmp_path: Path):
    """A subdir without any marker can still be registered manually."""
    (tmp_path / "infra").mkdir()
    repos = discover_repos(
        tmp_path,
        include_manual=[{"name": "infra", "path": "infra", "description": "TF"}],
    )
    assert len(repos) == 1
    assert repos[0]["source"] == "manual"
    assert repos[0]["name"] == "infra"


def test_manual_pointing_to_nonexistent_path_is_ignored(tmp_path: Path):
    repos = discover_repos(
        tmp_path,
        include_manual=[{"name": "ghost", "path": "ghost", "description": ""}],
    )
    assert repos == []


def test_unreadable_root_returns_empty(tmp_path: Path):
    """`discover_repos` on a non-existent path should return [], not crash."""
    assert discover_repos(tmp_path / "does-not-exist") == []


def test_skip_list_contains_holoctl_legacy_markers():
    """Defensive: never scan our own state dirs as subprojects."""
    for marker in (".holoctl", ".projctl", ".projhub"):
        assert marker in SKIP_NAMES
