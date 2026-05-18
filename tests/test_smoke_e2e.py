"""End-to-end smoke tests that spawn the real CLI / MCP server.

These are slower than the rest of the suite (each test forks a subprocess)
but they catch wiring bugs that unit tests miss — like the MCP server
failing to advertise the v0.17 tools, or `hctl doctor` reporting healthy
when an output path doesn't actually exist.

The MCP smoke is gated behind a network-free, in-process JSON-RPC exchange
so it works in CI without extra dependencies.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


CLI = [sys.executable, "-m", "holoctl"]


def _run(args: list[str], cwd: Path, *, check: bool = True, timeout: int = 60):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"}
    result = subprocess.run(
        CLI + args,
        cwd=cwd,
        capture_output=True,
        timeout=timeout,
        env=env,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"hctl {' '.join(args)} exited {result.returncode}\n"
            f"--- stdout ---\n{result.stdout.decode('utf-8', 'replace')}\n"
            f"--- stderr ---\n{result.stderr.decode('utf-8', 'replace')}"
        )
    return result


def _decode(b: bytes) -> str:
    return (b or b"").decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# CLI smoke — init → doctor → all checks pass
# ---------------------------------------------------------------------------


def test_init_then_doctor_reports_healthy(tmp_path: Path):
    """The cardinal end-to-end check: after init the workspace must pass
    doctor cleanly. Catches drift between what compilers write and what
    doctor looks for (the bug that motivated this whole file)."""
    _run(
        ["init", "--name", "ci", "--prefix", "CI",
         "--targets", "agents,claude,copilot,codex"],
        cwd=tmp_path,
    )
    result = _run(["doctor"], cwd=tmp_path)
    out = _decode(result.stdout)
    assert "holoctl: ok" in out, out
    assert "All checks passed" in out, out
    assert "issue(s) found" not in out, out


def test_compile_codex_emits_valid_toml_via_subprocess(tmp_path: Path):
    """A second tomllib check, this time via the real CLI binary, so any
    Windows newline or encoding surprise gets exercised."""
    import tomllib
    _run(
        ["init", "--name", "ci", "--targets", "agents,claude,codex"],
        cwd=tmp_path,
    )
    cfg = tmp_path / ".codex" / "config.toml"
    parsed = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert parsed["mcp_servers"]["holoctl"]["args"] == ["serve", "--mcp"]


def test_compile_unknown_target_fails_with_help(tmp_path: Path):
    """Removed targets must fail loud — and tell the user what's available."""
    _run(["init", "--name", "ci"], cwd=tmp_path)
    result = _run(["compile", "--target", "cursor"], cwd=tmp_path, check=False)
    # Error is printed by the CLI; exit code is 0 because typer wraps it,
    # but the message itself must mention the rejection and the live set.
    combined = _decode(result.stdout) + _decode(result.stderr)
    assert "Unknown compile target: cursor" in combined, combined
    assert "Available:" in combined, combined


# ---------------------------------------------------------------------------
# MCP server smoke — stdio handshake + tools/list
# ---------------------------------------------------------------------------


def test_mcp_server_advertises_v017_tools(tmp_path: Path):
    """Spawn `hctl serve --mcp`, perform the JSON-RPC handshake, and confirm
    the server returns the v0.17 tool set including the new ones
    (`config_show`, `agent_create`) and the canonical board/memory tools.

    Catches:
      - tool name regressions (server renames without README/help updates)
      - server crashing on the initialize handshake
      - missing tool registrations after refactors
    """
    _run(["init", "--name", "ci"], cwd=tmp_path)

    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "0"},
        },
    }
    tools_list = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

    stdin = (json.dumps(initialize) + "\n" + json.dumps(tools_list) + "\n").encode("utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"}
    proc = subprocess.run(
        CLI + ["serve", "--mcp"],
        cwd=tmp_path,
        input=stdin,
        capture_output=True,
        timeout=30,
        env=env,
    )
    out = _decode(proc.stdout)

    responses = []
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    init_resp = next((r for r in responses if r.get("id") == 1), None)
    tools_resp = next((r for r in responses if r.get("id") == 2), None)

    assert init_resp is not None, f"no initialize response in:\n{out}"
    assert init_resp["result"]["serverInfo"]["name"] == "holoctl"

    assert tools_resp is not None, f"no tools/list response in:\n{out}"
    tool_names = {t["name"] for t in tools_resp["result"]["tools"]}

    # v0.17 additions — these were the regression risk when the catalog grew.
    for required in (
        "holoctl.config_show",
        "holoctl.agent_create",
        "holoctl.board_create",
        "holoctl.board_batch",
        "holoctl.memory_add",
        "holoctl.memory_search",
    ):
        assert required in tool_names, (
            f"MCP server didn't advertise '{required}'. Got: {sorted(tool_names)}"
        )

    # No retired/renamed tool sneaks back in (sanity).
    assert "holoctl.board_old" not in tool_names
