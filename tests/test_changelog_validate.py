"""Tests for scripts/validate_changelog.py — version-consistency checker.

These exercise the pure helpers (`_latest_changelog_version`) and the end-to-end
`main()` against the real repo, plus the mismatch path via monkeypatching.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Load the script as a module (it lives under scripts/, not an importable pkg).
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_changelog.py"
_spec = importlib.util.spec_from_file_location("validate_changelog", _SCRIPT)
assert _spec and _spec.loader
validate_changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_changelog)


def test_latest_version_skips_unreleased():
    text = "# Changelog\n\n## [Unreleased]\n\n## [1.2.3] — 2026-01-01\n\n## [1.2.2] — 2025-12-01\n"
    assert validate_changelog._latest_changelog_version(text) == "1.2.3"


def test_latest_version_none_when_only_unreleased():
    text = "# Changelog\n\n## [Unreleased]\n\n- nothing released yet\n"
    assert validate_changelog._latest_changelog_version(text) is None


def test_main_passes_on_real_repo(capsys):
    """The real tree ships matching versions, so main() returns 0."""
    assert validate_changelog.main() == 0
    assert "OK" in capsys.readouterr().out


def test_main_reports_mismatch(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(validate_changelog, "_pyproject_version", lambda: "9.9.9")
    monkeypatch.setattr(validate_changelog, "_latest_changelog_version", lambda _text: "0.0.1")
    assert validate_changelog.main() == 1
    assert "mismatch" in capsys.readouterr().err
