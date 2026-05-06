"""Shared pytest fixtures for holoctl tests."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from holoctl.lib.config import get_defaults, save_config


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A fresh workspace with `.holoctl/` initialized.

    Returns the workspace root. Inside it, `.holoctl/config.json` exists with
    defaults plus a project name/prefix sane for assertions.
    """
    config = get_defaults()
    config["project"]["name"] = "TestProject"
    config["project"]["prefix"] = "TST"
    save_config(tmp_path, config)

    board_dir = tmp_path / ".holoctl" / "board"
    (board_dir / "tickets").mkdir(parents=True, exist_ok=True)
    (board_dir / "index.json").write_text(
        json.dumps({
            "meta": {"version": 1, "updated": "2026-01-01", "nextId": 1, "counts": {}},
            "tickets": [],
        }, indent="\t") + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".holoctl" / "activity.jsonl").write_text("", encoding="utf-8")

    # Plant minimal agent files so Board.add() validation passes — same set of
    # personas `holoctl init` ships with.
    agents_dir = tmp_path / ".holoctl" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name in ("developer", "reviewer", "architect", "researcher"):
        (agents_dir / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: test agent\n---\n", encoding="utf-8"
        )

    return tmp_path


@pytest.fixture
def workspace_config(workspace: Path) -> dict:
    """Load the config from the workspace fixture."""
    from holoctl.lib.config import load_config
    return load_config(workspace)


@pytest.fixture
def make_marker():
    """Factory fixture: create an empty project marker file inside a directory."""
    def _make(directory: Path, marker: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / marker).write_text("", encoding="utf-8")
    return _make
