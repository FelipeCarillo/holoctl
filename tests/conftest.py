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


@pytest.fixture
def dashboard_css() -> str:
    """Concatenated CSS the dashboard serves — modules in `static/css/` joined
    in the same order `index.css` imports them. Tests assert against this
    instead of the old monolithic `holoctl.css` (which was split per section)."""
    import re
    from holoctl.server import app as app_module
    css_dir = Path(app_module.__file__).parent / "static" / "css"
    index = (css_dir / "index.css").read_text("utf-8")
    parts: list[str] = []
    for m in re.finditer(r'@import\s+"\./([^"]+)"\s*;', index):
        parts.append((css_dir / m.group(1)).read_text("utf-8"))
    return "".join(parts)


@pytest.fixture
def dashboard_js() -> str:
    """Concatenated JS the dashboard ships — all `.js` files in `static/js/`
    joined into one string. Order matches index.js's import declarations.
    Tests assert against this instead of the old monolithic `holoctl-ui.js`."""
    import re
    from holoctl.server import app as app_module
    js_dir = Path(app_module.__file__).parent / "static" / "js"
    index = (js_dir / "index.js").read_text("utf-8")
    parts: list[str] = [index]
    # Collect both `import { ... } from './x.js'` and bare `import './x.js'`.
    seen: set[str] = set()
    for m in re.finditer(r"import\s+(?:[^'\"]*\s+from\s+)?['\"]\./([^'\"]+)['\"]\s*;", index):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        parts.append((js_dir / name).read_text("utf-8"))
    # Pull in remaining modules not directly imported by index.js (e.g.
    # transitive deps like toast, view-switcher).
    for f in sorted(js_dir.glob("*.js")):
        if f.name == "index.js" or f.name in seen:
            continue
        parts.append(f.read_text("utf-8"))
    return "\n".join(parts)
