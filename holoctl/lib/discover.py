from __future__ import annotations
from pathlib import Path
from typing import Iterable, Optional

from .git import get_git_info, read_git_fast


PROJECT_MARKERS = [
    ".git",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "composer.json",
    "Gemfile",
    "pubspec.yaml",
    "mix.exs",
    "build.gradle",
    "pom.xml",
    "CMakeLists.txt",
]

SKIP_NAMES = {
    "node_modules", ".venv", "venv", "env",
    "dist", "build", "target", "out",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".holoctl", ".projctl", ".projhub",
    ".git", ".svn", ".hg",
    "coverage", ".coverage", ".nyc_output",
    ".next", ".nuxt", ".cache",
    ".DS_Store",
}


def _detect_markers(dir_path: Path) -> list[str]:
    return [m for m in PROJECT_MARKERS if (dir_path / m).exists()]


def discover_repos(
    project_root: Path,
    include_manual: Optional[Iterable[dict]] = None,
    skip: Optional[Iterable[str]] = None,
    *,
    with_dirty: bool = False,
) -> list[dict]:
    """Walk direct children of project_root and collect subprojects.

    Git metadata (branch, commit hash, remote URL) is read directly from
    `.git/HEAD` and `.git/config` — no subprocess. The `dirty` flag and
    last-commit info are NOT included by default because they require
    `git status --porcelain` which spawns a process per repo and is the
    dominant cost on Windows + corporate AV.

    Pass `with_dirty=True` to opt into the slow path (used by the dashboard
    Repos tab and `holoctl repo info`).
    """
    skip_set = set(SKIP_NAMES) | set(skip or [])
    git_reader = get_git_info if with_dirty else read_git_fast

    try:
        entries = list(project_root.iterdir())
    except OSError:
        return []

    discovered: list[dict] = []
    for entry in entries:
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") and entry.name != ".git":
            continue
        if entry.name in skip_set:
            continue

        markers = _detect_markers(entry)
        if not markers:
            continue

        discovered.append({
            "name": entry.name,
            "path": entry.name,
            "markers": markers,
            "git": git_reader(entry) if ".git" in markers else None,
            "source": "auto",
        })

    by_path = {r["path"]: r for r in discovered}
    for manual in (include_manual or []):
        rel_path = manual.get("path", "")
        abs_path = project_root / rel_path
        if not abs_path.exists():
            continue

        if rel_path in by_path:
            existing = by_path[rel_path]
            existing["name"] = manual.get("name") or existing["name"]
            existing["description"] = manual.get("description")
            existing["source"] = "auto+manual"
        else:
            by_path[rel_path] = {
                "name": manual.get("name") or abs_path.name,
                "path": rel_path,
                "markers": _detect_markers(abs_path),
                "git": git_reader(abs_path),
                "description": manual.get("description"),
                "source": "manual",
            }

    return sorted(by_path.values(), key=lambda r: r["name"])
