"""F6b — end-to-end conformance for the MCP stdio server.

The other MCP tests call `handle()` in-process. This one drives the real
`hctl serve --mcp` subprocess over stdin/stdout, exercising `serve_stdio`'s
line loop, cold-start, and — critically — that notifications get NO response
line (a response to a notification would desync every subsequent exchange).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    subprocess.run(
        [sys.executable, "-m", "holoctl", "init", "--name", "MCPStdio", "--prefix", "MS", "--skip-compile"],
        cwd=tmp_path, capture_output=True, timeout=60, check=True,
    )
    return tmp_path


def test_stdio_conformance_handshake(workspace: Path):
    proc = subprocess.Popen(
        [sys.executable, "-m", "holoctl", "serve", "--mcp"],
        cwd=workspace,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        def send(obj: dict) -> None:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()

        def read() -> dict:
            assert proc.stdout is not None
            line = proc.stdout.readline()
            assert line, "server closed stdout unexpectedly"
            return json.loads(line)

        # 1. initialize → response with protocol version.
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        resp = read()
        assert resp["id"] == 1
        assert resp["result"]["serverInfo"]["name"] == "holoctl"

        # 2. notifications/initialized → NO response (don't read).
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3. tools/list → if step 2 had emitted a line, this read would get it;
        #    asserting id==2 proves the notification produced nothing.
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        resp = read()
        assert resp["id"] == 2
        names = {t["name"] for t in resp["result"]["tools"]}
        assert "holoctl.board_list" in names

        # 4. tools/call board_list → JSON-text content (workspace is seeded).
        send({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "holoctl.board_list", "arguments": {}},
        })
        resp = read()
        assert resp["id"] == 3
        parsed = json.loads(resp["result"]["content"][0]["text"])
        assert parsed["tickets"] == []

        # 5. ping → empty result.
        send({"jsonrpc": "2.0", "id": 4, "method": "ping"})
        resp = read()
        assert resp == {"jsonrpc": "2.0", "id": 4, "result": {}}

        # 6. unknown notification → NO response.
        send({"jsonrpc": "2.0", "method": "notifications/cancelled"})

        # 7. ping again → must come back as id==5 (proves step 6 was silent).
        send({"jsonrpc": "2.0", "id": 5, "method": "ping"})
        resp = read()
        assert resp["id"] == 5 and resp["result"] == {}

        # 8. EOF on stdin → the read loop ends and the process exits cleanly.
        assert proc.stdin is not None
        proc.stdin.close()
        assert proc.wait(timeout=30) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
