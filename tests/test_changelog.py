"""Tests for holoctl.lib.changelog — bundled CHANGELOG load + version slicing."""
from __future__ import annotations

from holoctl.lib.changelog import load_changelog, slice_between


_FIXTURE = """# Changelog

Some preamble that should never appear in a slice.

## [0.8.1] — 2026-05-06

### Fixed
- thing one

## [0.8.0] — 2026-05-05

### Added
- big feature

## [0.7.0] — 2026-05-01

### Added
- earlier feature
"""


def test_load_changelog_returns_text():
    """The bundled CHANGELOG must be discoverable in the test environment."""
    text = load_changelog()
    assert text is not None
    assert text.startswith("# Changelog")


def test_slice_between_extracts_range():
    """0.7.0 → 0.8.1 should include 0.8.0 and 0.8.1, exclude 0.7.0 itself."""
    out = slice_between(_FIXTURE, "0.7.0", "0.8.1")
    assert "[0.8.1]" in out
    assert "[0.8.0]" in out
    assert "[0.7.0]" not in out
    assert "preamble" not in out


def test_slice_between_inclusive_of_new():
    """The new bound is inclusive — slicing X..X returns the X section."""
    out = slice_between(_FIXTURE, "0.8.0", "0.8.1")
    assert "[0.8.1]" in out
    assert "[0.8.0]" not in out


def test_slice_between_same_version_is_empty():
    """workspace_version == installed_version → no sections to show."""
    out = slice_between(_FIXTURE, "0.8.1", "0.8.1")
    assert out == ""


def test_slice_between_no_versions_in_range_is_empty():
    out = slice_between(_FIXTURE, "0.9.0", "0.9.5")
    assert out == ""


def test_slice_between_invalid_new_returns_empty():
    """Garbage version strings shouldn't blow up — return empty."""
    assert slice_between(_FIXTURE, "0.7.0", "not-a-version") == ""


def test_slice_between_against_real_changelog():
    """Sanity check against the real bundled CHANGELOG: there must be at least
    one ## header and slicing 0.0.0..current should return non-empty text."""
    text = load_changelog()
    assert text is not None
    out = slice_between(text, "0.0.0", "99.99.99")
    assert "## [" in out
