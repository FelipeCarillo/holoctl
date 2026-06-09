#!/usr/bin/env python3
"""Validate that pyproject's version matches the latest CHANGELOG entry.

Read-only consistency check used in CI and as a pre-commit hook. It asserts
that ``[project].version`` in ``pyproject.toml`` equals the most recent
released ``## [X.Y.Z]`` header in ``holoctl/CHANGELOG.md`` (an ``## [Unreleased]``
section, if present, is ignored — it has no version number).

Exit codes:
    0 — versions match.
    1 — mismatch, or a required file / header could not be found.

This script never writes anything; it only reports.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# scripts/ lives at the repo root next to pyproject.toml and holoctl/.
REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "holoctl" / "CHANGELOG.md"

# Matches `## [1.2.3]` headers but not `## [Unreleased]`.
_VERSION_HEADER = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]")


def _pyproject_version() -> str:
    with PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    return str(data["project"]["version"])


def _latest_changelog_version(text: str) -> str | None:
    for line in text.splitlines():
        m = _VERSION_HEADER.match(line.strip())
        if m:
            return m.group(1)
    return None


def main() -> int:
    if not PYPROJECT.exists():
        print(f"ERROR: {PYPROJECT} not found", file=sys.stderr)
        return 1
    if not CHANGELOG.exists():
        print(f"ERROR: {CHANGELOG} not found", file=sys.stderr)
        return 1

    pyproject_version = _pyproject_version()
    latest = _latest_changelog_version(CHANGELOG.read_text(encoding="utf-8"))

    if latest is None:
        print(
            f"ERROR: no `## [X.Y.Z]` version header found in {CHANGELOG.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        return 1

    if pyproject_version != latest:
        print(
            "ERROR: version mismatch — "
            f"pyproject.toml = {pyproject_version!r}, "
            f"latest CHANGELOG entry = {latest!r}.\n"
            "Update holoctl/CHANGELOG.md and/or pyproject.toml so they agree.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: pyproject and CHANGELOG agree on version {pyproject_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
