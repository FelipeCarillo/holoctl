"""Consistency guards for compile target metadata.

These tests lock the invariants between the four places where target lists
appear, so a target rename / addition / removal can't drift any one of them
out of sync (and end up shipping a broken `hctl doctor` / `hctl coverage`
that points at a path no compiler actually emits):

  - `holoctl.lib.compiler._COMPILERS`           — authoritative registry
  - `holoctl.cli.doctor._TARGET_OUTPUTS`        — paths doctor checks
  - `holoctl.cli.coverage._COVERAGE`            — source→target matrix
  - help texts of `compile --help`, `init --help`, `setup-global --help`
  - `holoctl.lib.config._REMOVED_TARGETS`       — silent-migration set

The bug this file exists to prevent was caught only by an end-to-end smoke
run (doctor pointed at `.codex/AGENTS.md` while the compiler emits
`.codex/AGENTS.override.md`). Every claim below is mechanical, so drift is
caught locally without spinning up the CLI.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from holoctl.cli.coverage import _COVERAGE
from holoctl.cli.doctor import _TARGET_OUTPUTS
from holoctl.lib.compiler import _COMPILERS, compile_project
from holoctl.lib.config import _REMOVED_TARGETS, get_defaults


_ACTIVE_TARGETS = set(_COMPILERS.keys())


def _seed_minimal_workspace(root: Path) -> dict:
    """Plant the minimum file set every compiler expects to read."""
    holoctl = root / ".holoctl"
    (holoctl / "agents").mkdir(parents=True, exist_ok=True)
    (holoctl / "commands").mkdir(parents=True, exist_ok=True)
    (holoctl / "context").mkdir(parents=True, exist_ok=True)
    (holoctl / "agents" / "boardmaster.md").write_text(
        "---\nname: boardmaster\ndescription: test\n---\n# body\n", encoding="utf-8"
    )
    (holoctl / "commands" / "status.md").write_text(
        "---\nname: status\ndescription: test\n---\n# body\n", encoding="utf-8"
    )
    (holoctl / "instructions.md").write_text(
        "# Project\n\nMinimal instructions for compiler smoke.\n", encoding="utf-8"
    )
    (holoctl / "context" / "objective.md").write_text("Test objective.\n", encoding="utf-8")
    return get_defaults()


# ---------------------------------------------------------------------------
# Metadata consistency
# ---------------------------------------------------------------------------


def test_target_outputs_keys_subset_of_compilers():
    """Every target doctor checks must be a real compiler."""
    extras = set(_TARGET_OUTPUTS) - _ACTIVE_TARGETS
    assert not extras, (
        f"doctor._TARGET_OUTPUTS references targets that don't exist in "
        f"_COMPILERS: {sorted(extras)}"
    )


def test_compilers_covered_by_doctor():
    """Doctor must check every active target (else regressions slip through)."""
    missing = _ACTIVE_TARGETS - set(_TARGET_OUTPUTS)
    assert not missing, (
        f"_TARGET_OUTPUTS is missing entries for active compilers: "
        f"{sorted(missing)}. Update holoctl/cli/doctor.py:_TARGET_OUTPUTS."
    )


def test_coverage_columns_equal_compilers():
    """`hctl coverage`'s matrix columns must be exactly the active targets."""
    for source, mapping in _COVERAGE.items():
        cols = set(mapping.keys())
        assert cols == _ACTIVE_TARGETS, (
            f"_COVERAGE['{source}'] has columns {sorted(cols)} but compilers "
            f"are {sorted(_ACTIVE_TARGETS)}. Edit holoctl/cli/coverage.py."
        )


def _is_concrete_path(dest) -> bool:
    """True if a _COVERAGE cell is a plain repo-relative path we can verify
    against emitted files. Excludes None, placeholder paths (`<name>`),
    JSON-pointer suffixes (`settings.json:mcpServers`), and descriptive prose
    ('AGENTS.md (Objective…)')."""
    if not isinstance(dest, str) or not dest:
        return False
    return not any(c in dest for c in "<>(~ :")


def test_coverage_concrete_paths_match_emitted_outputs(tmp_path: Path):
    """`hctl coverage` claims, per (source, target), *where* a piece materializes.
    Every concrete path it claims must be a path the compiler actually emits.

    This is the value-level guard the column check (above) lacks — and it is
    exactly what would have caught `_COVERAGE['instructions.md']['codex']`
    pointing at `.codex/AGENTS.md` while the compiler emits
    `.codex/AGENTS.override.md`.
    """
    from holoctl.cli.coverage import _source_exists

    config = _seed_minimal_workspace(tmp_path)
    emitted: set[str] = set()
    for target in sorted(_ACTIVE_TARGETS):
        result = compile_project(tmp_path, config, target, dry_run=False)
        emitted.update(result.get("files", []))

    for source, mapping in _COVERAGE.items():
        # Synthetic rows (e.g. MCP servers) start with '(' and have no source
        # file — their outputs are always emitted; check them too.
        present = source.startswith("(") or _source_exists(tmp_path, source)
        if not present:
            continue
        for target, dest in mapping.items():
            if not _is_concrete_path(dest):
                continue
            assert dest in emitted, (
                f"_COVERAGE['{source}']['{target}'] = {dest!r} but compiling "
                f"the targets never emitted it. Fix holoctl/cli/coverage.py "
                f"(or the compiler). Emitted: {sorted(emitted)}"
            )


def test_removed_and_active_targets_disjoint():
    """A target can't be both retired and live — the silent filter would eat it."""
    overlap = _REMOVED_TARGETS & _ACTIVE_TARGETS
    assert not overlap, (
        f"Targets {sorted(overlap)} appear in both _COMPILERS (live) and "
        f"_REMOVED_TARGETS (filtered on load). Pick one."
    )


# ---------------------------------------------------------------------------
# Behavioral consistency — every target really emits what doctor expects
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", sorted(_ACTIVE_TARGETS))
def test_compile_target_produces_declared_outputs(tmp_path: Path, target: str):
    """For each target, compile must produce every path doctor will look for.

    This is the test that would have caught `.codex/AGENTS.md` vs
    `.codex/AGENTS.override.md`.
    """
    config = _seed_minimal_workspace(tmp_path)
    result = compile_project(tmp_path, config, target, dry_run=False)
    declared = _TARGET_OUTPUTS.get(target, [])
    for rel in declared:
        path = tmp_path / rel
        assert path.exists(), (
            f"target '{target}' declares output '{rel}' in doctor._TARGET_OUTPUTS "
            f"but compile_project didn't create it. files compiler emitted: "
            f"{result.get('files', [])}"
        )


@pytest.mark.parametrize("target", sorted(_ACTIVE_TARGETS))
def test_compile_target_is_idempotent(tmp_path: Path, target: str):
    """Re-running compile must produce byte-identical outputs (no drift)."""
    config = _seed_minimal_workspace(tmp_path)
    compile_project(tmp_path, config, target, dry_run=False)
    snapshot_first = _snapshot_compiled_files(tmp_path)
    compile_project(tmp_path, config, target, dry_run=False)
    snapshot_second = _snapshot_compiled_files(tmp_path)
    assert snapshot_first == snapshot_second, (
        f"target '{target}' is not idempotent — re-running compile changed "
        f"output. diff: {_diff_snapshots(snapshot_first, snapshot_second)}"
    )


def _snapshot_compiled_files(root: Path) -> dict[str, bytes]:
    """All non-.holoctl files under root, mapped to their bytes."""
    out: dict[str, bytes] = {}
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        if rel.startswith(".holoctl/"):
            continue
        out[rel] = f.read_bytes()
    return out


def _diff_snapshots(a: dict, b: dict) -> str:
    keys = sorted(set(a) | set(b))
    diffs = []
    for k in keys:
        if a.get(k) != b.get(k):
            diffs.append(k)
    return ", ".join(diffs) or "(none)"


# ---------------------------------------------------------------------------
# Dispatcher: removed targets reject with the help text the user needs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("removed", sorted(_REMOVED_TARGETS))
def test_compile_rejects_removed_target_with_useful_message(tmp_path: Path, removed: str):
    """Hitting `cursor` / `windsurf` / `devin` / `generic` post-removal must
    raise with the list of available targets so the user can pick one."""
    config = _seed_minimal_workspace(tmp_path)
    with pytest.raises(ValueError) as ei:
        compile_project(tmp_path, config, removed, dry_run=False)
    msg = str(ei.value)
    assert f"Unknown compile target: {removed}" in msg, msg
    assert "Available:" in msg, msg
    # All active targets must be listed in the error.
    for t in _ACTIVE_TARGETS:
        assert t in msg, f"active target '{t}' not in error message: {msg}"


# ---------------------------------------------------------------------------
# Help texts — exposed via `--help`. These are the strings users actually read.
# ---------------------------------------------------------------------------


def _capture_help(*args: str) -> str:
    """Run `python -m holoctl <args> --help` and return combined stdout/stderr.

    Uses subprocess so we exercise the same code path the user does (typer's
    CliRunner can hide formatting differences from terminal-width detection).
    Forces UTF-8 because Windows defaults to cp1252 and rich emits glyphs
    outside that range."""
    result = subprocess.run(
        [sys.executable, "-m", "holoctl", *args, "--help"],
        capture_output=True,
        timeout=30,
        env={
            "COLUMNS": "200",
            "NO_COLOR": "1",
            "PYTHONIOENCODING": "utf-8",
            **_clean_env(),
        },
    )
    decode = lambda b: (b or b"").decode("utf-8", errors="replace")
    return decode(result.stdout) + decode(result.stderr)


def _clean_env() -> dict:
    """Strip the env to a minimal set so help renders consistently across OS."""
    import os
    keep = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "APPDATA")
    return {k: os.environ[k] for k in keep if k in os.environ}


def test_compile_help_lists_only_active_targets():
    out = _capture_help("compile")
    for t in _ACTIVE_TARGETS:
        assert t in out, f"`compile --help` is missing active target '{t}':\n{out}"
    for r in _REMOVED_TARGETS:
        assert r not in out, (
            f"`compile --help` still mentions retired target '{r}':\n{out}"
        )


def test_init_help_lists_only_active_targets():
    out = _capture_help("init")
    for t in _ACTIVE_TARGETS:
        assert t in out, f"`init --help` is missing active target '{t}':\n{out}"
    for r in _REMOVED_TARGETS:
        assert r not in out, (
            f"`init --help` still mentions retired target '{r}':\n{out}"
        )


def test_setup_global_help_omits_retired_tools():
    """setup-global ships an installer only for claude. Retired tools
    (copilot / cursor / windsurf / devin) must not appear in --help anymore."""
    out = _capture_help("setup-global")
    assert "claude" in out
    for r in ("copilot", "devin", "cursor", "windsurf"):
        assert r not in out, f"`setup-global --help` still mentions '{r}':\n{out}"


# ---------------------------------------------------------------------------
# Config: legacy `targets` are silently filtered on load
# ---------------------------------------------------------------------------


def test_load_config_filters_removed_targets(tmp_path: Path):
    """A workspace that still lists retired targets must load cleanly with
    them stripped — no exception, no warning."""
    from holoctl.lib.config import load_config

    holoctl = tmp_path / ".holoctl"
    holoctl.mkdir()
    legacy = {
        "holoctlVersion": "0.17.0",
        "project": {"name": "legacy", "prefix": "L"},
        "targets": ["agents", "claude", "cursor", "windsurf", "copilot", "devin", "generic", "codex"],
    }
    (holoctl / "config.json").write_text(json.dumps(legacy), encoding="utf-8")

    loaded = load_config(tmp_path)
    assert set(loaded["targets"]) == {"agents", "claude"}
