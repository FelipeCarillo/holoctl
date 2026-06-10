"""CLI import hygiene for the dashboard web stack.

The web stack (fastapi/uvicorn/jinja2) ships with the base install — there is
no `[dashboard]` extra to forget anymore — but it must stay a LAZY import:
importing the CLI (`holoctl.__main__`) must NOT pull fastapi / uvicorn /
jinja2 / starlette into the process. Every `hctl board ls` would otherwise pay
~100ms of web-stack import cost. A future eager import regresses this loudly.
"""
from __future__ import annotations

import subprocess
import sys


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
