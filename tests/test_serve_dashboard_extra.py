"""F12 — the dashboard web stack is an optional extra, not part of the lean core.

Two guarantees:
  1. Importing the CLI must NOT pull fastapi / uvicorn / jinja2 / starlette —
     a CLI/MCP-only install stays lightweight. A future eager import regresses
     this loudly.
  2. `hctl serve` (dashboard) prints an actionable install hint and exits
     non-zero when the extra is missing, instead of an opaque ImportError.
     `hctl serve --mcp` stays dependency-free.
"""
from __future__ import annotations

import subprocess
import sys

from typer.testing import CliRunner

from holoctl.cli import serve as serve_mod
from holoctl.cli.serve import app as serve_app


def test_cli_import_does_not_pull_web_stack():
    """Run in a clean interpreter so other tests' imports don't pollute the check."""
    code = (
        "import holoctl.__main__, sys; "
        "bad = [m for m in ('fastapi', 'uvicorn', 'jinja2', 'starlette') if m in sys.modules]; "
        "assert not bad, bad; print('clean')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, (
        f"importing the CLI pulled the web stack: {result.stdout} {result.stderr}"
    )
    assert "clean" in result.stdout


def test_serve_dashboard_missing_extra_prints_hint(monkeypatch):
    """When a dashboard module is absent, serve must exit 1 with an install hint."""
    monkeypatch.setattr(serve_mod, "_missing_dashboard_dep", lambda: "uvicorn")
    result = CliRunner().invoke(serve_app, [])
    assert result.exit_code == 1, result.output
    assert "holoctl[dashboard]" in result.output
    assert "uvicorn" in result.output


def test_missing_dashboard_dep_returns_none_when_all_present():
    # In the dev environment the extra is installed, so nothing is missing.
    assert serve_mod._missing_dashboard_dep() is None
