# Dashboard Render-Rebuild + Editorial Identity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the stalled Jinja migration of the dashboard (delete dead string-builders, relocate live helpers, replace the hand-rolled markdown renderer) and land an Editorial visual identity across all surfaces — in one pass.

**Architecture:** The dashboard already renders all views through `routes/ → views/ (presenters) → templates/ (Jinja)`. The large string-built helpers in `server/app.py` are dead in production but kept alive by `tests/test_dashboard.py`. We re-point those tests at rendered output, delete the dead code, relocate the genuinely-live helpers into focused modules, swap the markdown renderer, then restyle the (already existing) templates via the CSS token layer.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, `markdown-it-py` + `mdit-py-plugins`, vanilla JS + SSE, plain CSS (no build step). Tests: pytest + `fastapi.testclient`. Gates: `ruff`, `mypy`.

**Source spec:** `docs/superpowers/specs/2026-05-26-dashboard-render-rebuild-editorial-design.md`

---

## File map

**Create:**
- `holoctl/server/markdown.py` — markdown rendering (replaces `_render_markdown` + `_strip_empty_sections`)
- `holoctl/server/projects.py` — project listing/lookup + cache (relocated from `app.py`)
- `tests/test_server_markdown.py` — markdown module tests

**Modify:**
- `holoctl/server/app.py` — shrink to wiring + API/SSE; remove dead helpers
- `holoctl/server/views/card.py` — absorb `_format_due` + `_ticket_preview`
- `holoctl/server/views/detail.py` — absorb `_read_ticket_activity`; use `server/markdown.py`
- `holoctl/server/views/doc.py` — use `server/markdown.py`
- `holoctl/server/routes/*.py` — import project helpers from `server/projects.py`
- `tests/test_dashboard.py` — re-point at rendered output
- `pyproject.toml` — add `markdown-it-py`, `mdit-py-plugins`
- `holoctl/server/static/css/tokens.css` — Editorial token system
- `holoctl/server/static/css/*.css` — per-surface Editorial polish
- `holoctl/server/templates/**` — minor class hooks (serif titles)

**Conventions to follow:** match the existing module style (module docstring, `from __future__ import annotations`, type hints — `mypy` is a CI gate). Tests use the `workspace`, `workspace_config`, `client`, `alias`, `dashboard_css` fixtures from `tests/conftest.py`.

---

## Phase 0 — Markdown library (isolated, low-risk)

### Task 1: New `server/markdown.py` backed by markdown-it-py

**Files:**
- Modify: `pyproject.toml` (dependencies)
- Create: `holoctl/server/markdown.py`
- Test: `tests/test_server_markdown.py`

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, add to the runtime `dependencies` list (alongside the existing FastAPI/Jinja entries):

```toml
"markdown-it-py>=3.0",
"mdit-py-plugins>=0.4",
```

Then sync: `uv sync` (or `pip install markdown-it-py mdit-py-plugins`).

- [ ] **Step 2: Write the failing test**

Create `tests/test_server_markdown.py`:

```python
from __future__ import annotations

import pytest

pytest.importorskip("markdown_it")

from holoctl.server.markdown import render_markdown, strip_empty_sections


class TestStripEmptySections:
    def test_drops_placeholder_only_section(self):
        body = "# Goal\n\n(describe the goal)\n\n# Real\n\nActual content.\n"
        out = strip_empty_sections(body)
        assert "Goal" not in out
        assert "Real" in out and "Actual content." in out

    def test_keeps_section_with_content(self):
        body = "# Goal\n\nShip it.\n"
        assert "Ship it." in strip_empty_sections(body)


class TestRenderMarkdown:
    def test_empty_body_returns_placeholder(self):
        assert "detail-empty" in render_markdown("")

    def test_headings(self):
        assert "<h1>" in render_markdown("# Title")

    def test_unordered_list(self):
        html = render_markdown("- one\n- two\n")
        assert "<ul>" in html and "<li>" in html

    def test_table(self):
        html = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |\n")
        assert "<table>" in html and "<td>" in html

    def test_link_is_anchored(self):
        html = render_markdown("see [docs](https://example.com)")
        assert '<a href="https://example.com"' in html

    def test_inline_code(self):
        assert "<code>" in render_markdown("call `foo()`")

    def test_task_list_checkbox(self):
        html = render_markdown("- [x] done\n- [ ] todo\n")
        assert "checkbox" in html or 'type="checkbox"' in html
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server_markdown.py -v`
Expected: FAIL with `ModuleNotFoundError: holoctl.server.markdown`.

- [ ] **Step 4: Implement `server/markdown.py`**

```python
"""Markdown rendering for the dashboard.

Replaces the hand-rolled `_render_markdown` that used to live in `app.py`.
`strip_empty_sections` drops `# Header` blocks whose body is only
placeholder hints (parenthetical text, empty checklist items, HTML
comments) so template-only tickets render clean.
"""
from __future__ import annotations

import re

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

_PLACEHOLDER_PATTERNS = (
    re.compile(r"^\([^)]*\)\s*$"),
    re.compile(r"^[-*]\s*\[\s*[xX ]?\s*\]\s+\([^)]*\)\s*$"),
    re.compile(r"^<!--.*-->\s*$"),
)

_md = MarkdownIt("gfm-like").use(tasklists_plugin, enabled=True)


def _is_placeholder_only(content: str) -> bool:
    real = [l.strip() for l in content.splitlines() if l.strip()]
    if not real:
        return True
    return all(any(p.match(l) for p in _PLACEHOLDER_PATTERNS) for l in real)


def strip_empty_sections(body: str) -> str:
    parts = re.split(r"^(# .+)$", body, flags=re.MULTILINE)
    if len(parts) <= 1:
        return body
    out = [parts[0]]
    i = 1
    while i < len(parts):
        header = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""
        if not _is_placeholder_only(content):
            out.append(header)
            out.append(content)
        i += 2
    return "".join(out)


def render_markdown(body: str) -> str:
    body = strip_empty_sections(body)
    if not body.strip():
        return '<span class="detail-empty">No description</span>'
    return _md.render(body)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server_markdown.py -v`
Expected: PASS (all 9). If `test_task_list_checkbox` fails, confirm `mdit-py-plugins` installed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml holoctl/server/markdown.py tests/test_server_markdown.py
git commit -m "feat(server): markdown-it-py renderer module"
```

### Task 2: Point detail/doc presenters at `server/markdown.py`

**Files:**
- Modify: `holoctl/server/views/detail.py:27-29,55`
- Modify: `holoctl/server/views/doc.py:7-9`

- [ ] **Step 1: Update `views/detail.py`**

Replace the lazy import block (lines ~26-29) and the body render (line ~55). Remove `_render_markdown, _strip_empty_sections` from the `from ..app import (...)` tuple, leaving `_read_ticket_activity` for now. Add at top of file (module level):

```python
from .dates import format_iso_datetime
from ..markdown import render_markdown
```

Inside `detail_context`, change the lazy import to only:

```python
    from ..app import _read_ticket_activity
```

And change line ~55 from `body_html = _render_markdown(_strip_empty_sections(body))` to:

```python
    body_html = render_markdown(body)
```

(`render_markdown` already calls `strip_empty_sections`.)

- [ ] **Step 2: Update `views/doc.py`**

Read the file first. Replace its lazy `from ..app import _render_markdown, _strip_empty_sections` and the `body_html = _render_markdown(_strip_empty_sections(body))` call with a module-level `from ..markdown import render_markdown` and `body_html = render_markdown(body)`.

- [ ] **Step 3: Run dashboard tests (detail/doc routes still pass)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py -k "detail or doc or Detail or Doc" -v`
Expected: PASS (routes render through the new renderer). Markup is now standard tags; if a test asserted old custom markup it will fail here — note which, fixed in Task 9.

- [ ] **Step 4: Commit**

```bash
git add holoctl/server/views/detail.py holoctl/server/views/doc.py
git commit -m "refactor(server): detail/doc use markdown module"
```

---

## Phase 1 — Relocate live helpers (kills lazy imports)

### Task 3: Move `_format_due` + `_ticket_preview` into `views/card.py`

**Files:**
- Modify: `holoctl/server/views/card.py`
- Modify: `holoctl/server/app.py` (these funcs will be deleted in Task 10; for now keep both working via re-export)
- Test: `tests/test_dashboard.py` (import + class `TestTicketPreview`, `TestFormatDue`)

- [ ] **Step 1: Add the functions to `views/card.py`**

Move the *bodies* of `_format_due` and `_ticket_preview` (and the small `_strip_empty_sections`/regex they rely on — use `from ..markdown import strip_empty_sections`) from `app.py` into `views/card.py` as public functions `format_due` and `ticket_preview`. Replace the lazy import in `card_context` (lines 19-21) with direct calls:

```python
# top of card.py
from pathlib import Path
import re
from ..markdown import strip_empty_sections

def format_due(due_iso: str) -> str:
    ...  # body copied verbatim from app._format_due

def ticket_preview(project_root: Path | None, ticket: dict, max_chars: int = 80) -> str:
    ...  # body copied from app._ticket_preview, using strip_empty_sections()
```

In `card_context`, delete the lazy import and call `format_due(...)` / `ticket_preview(...)` directly.

- [ ] **Step 2: Keep `app.py` re-exporting (temporary shim)**

At the bottom of `app.py`, replace the old `_format_due`/`_ticket_preview` definitions with re-exports so nothing else breaks yet:

```python
from .views.card import format_due as _format_due, ticket_preview as _ticket_preview  # noqa: E402
```

- [ ] **Step 3: Re-point the helper tests' import**

In `tests/test_dashboard.py`, change the `from holoctl.server.app import (...)` block: import `_format_due` / `_ticket_preview` from `holoctl.server.views.card` as `format_due`/`ticket_preview`, and update `TestFormatDue` / `TestTicketPreview` call sites to the new names. Example:

```python
from holoctl.server.views.card import format_due, ticket_preview
# TestFormatDue: assert format_due("2026-05-09") == "May 9"
# TestTicketPreview: assert ticket_preview(workspace, ticket) == ""
```

- [ ] **Step 4: Run**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py -k "FormatDue or TicketPreview" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add holoctl/server/views/card.py holoctl/server/app.py tests/test_dashboard.py
git commit -m "refactor(server): relocate due/preview helpers into card view"
```

### Task 4: Move `_read_ticket_activity` into `views/detail.py`

**Files:**
- Modify: `holoctl/server/views/detail.py`
- Modify: `holoctl/server/app.py`
- Test: `tests/test_dashboard.py` (`_read_ticket_activity` import + its tests)

- [ ] **Step 1: Move the function**

Copy the body of `_read_ticket_activity` from `app.py` into `views/detail.py` as a public `read_ticket_activity(project_root, ticket_id)`. Remove the lazy `from ..app import _read_ticket_activity` and call the local function in `detail_context`.

- [ ] **Step 2: Re-export from `app.py` (temporary shim)**

```python
from .views.detail import read_ticket_activity as _read_ticket_activity  # noqa: E402
```

- [ ] **Step 3: Re-point the test import**

In `tests/test_dashboard.py`, import `read_ticket_activity` from `holoctl.server.views.detail` and update its test call sites.

- [ ] **Step 4: Run**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py -k "Activity or activity" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add holoctl/server/views/detail.py holoctl/server/app.py tests/test_dashboard.py
git commit -m "refactor(server): relocate activity reader into detail view"
```

### Task 5: New `server/projects.py` for project listing/lookup

**Files:**
- Create: `holoctl/server/projects.py`
- Modify: `holoctl/server/app.py`, `holoctl/server/routes/*.py`
- Test: `tests/test_dashboard.py` (`TestReadRoutes`, plus cache-isolation fixture)

- [ ] **Step 1: Create `server/projects.py`**

Move `_list_workspace_compat`, `_get_projects`, `_get_project`, the `_PROJECTS_CACHE` dict + TTL, and the `_read_agents`/`_read_commands`/`_read_context_docs` helpers (if only used by project pages) into `holoctl/server/projects.py` as public names: `list_workspace`, `get_projects`, `get_project`, `PROJECTS_CACHE`, `PROJECTS_CACHE_TTL`. Keep imports they need (`load_config`, `Board`, `discover_repos`, `parse_frontmatter`).

- [ ] **Step 2: Update `app.py` + routes to import from `projects.py`**

In `app.py`, replace the definitions with `from .projects import get_projects as _get_projects, get_project as _get_project, PROJECTS_CACHE as _PROJECTS_CACHE`. In each `routes/*.py`, change `from ..app import _get_project, _not_found_html` to `from ..projects import get_project` (and keep `_not_found_html` from app for now — handled in Task 10).

- [ ] **Step 3: Fix the cache-isolation fixture**

In `tests/test_dashboard.py`, the `_isolate_projects_cache` fixture pokes `app_module._PROJECTS_CACHE`. Point it at `holoctl.server.projects.PROJECTS_CACHE` instead.

- [ ] **Step 4: Run the route tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py -k "ReadRoutes or Route or route" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add holoctl/server/projects.py holoctl/server/app.py holoctl/server/routes tests/test_dashboard.py
git commit -m "refactor(server): extract project listing into projects.py"
```

---

## Phase 2 — Re-point dead-helper tests at rendered output, then delete

Each task here rewrites one test class to assert against **rendered Jinja** instead of a dead string-builder. Pattern: render the same partial the route uses, via the presenter, then assert on semantic markup (`data-*`, ids, titles) so future restyles don't break the test.

### Task 6: Rewrite `TestKanbanHtml` → render the kanban partial

**Files:**
- Modify: `tests/test_dashboard.py` (`TestKanbanHtml`)

- [ ] **Step 1: Add a render helper + rewrite the class**

Replace `TestKanbanHtml` with assertions over the rendered partial:

```python
from holoctl.server.jinja import render
from holoctl.server.views.board import board_context


def _render_kanban(project_root, config):
    from holoctl.lib.board import Board
    b = Board(project_root, config)
    project = {"alias": project_root.name, "name": "T", "path": str(project_root)}
    ctx = board_context(project, b.ls(), config, view="kanban")
    return render("partials/board/_kanban.html", **ctx)


class TestKanbanHtml:
    def test_priority_dot_data_attr(self, workspace, workspace_config):
        from holoctl.lib.board import Board
        Board(workspace, workspace_config).add(
            {"title": "T1", "priority": "p1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-prio-dot"' in html and 'data-p="p1"' in html

    def test_avatar_initials(self, workspace, workspace_config):
        from holoctl.lib.board import Board
        Board(workspace, workspace_config).add({"title": "T1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="avatar-initials"' in html and "data-hue=" in html
        assert ">DE</span>" in html

    def test_inline_add_per_column(self, workspace, workspace_config):
        html = _render_kanban(workspace, workspace_config)
        for s in workspace_config["board"]["statuses"]:
            assert f'data-add-ticket data-status="{s}"' in html

    def test_card_menu(self, workspace, workspace_config):
        from holoctl.lib.board import Board
        Board(workspace, workspace_config).add({"title": "T1", "agent": "developer"})
        assert "data-card-menu" in _render_kanban(workspace, workspace_config)

    def test_friendly_empty_state(self, workspace, workspace_config):
        html = _render_kanban(workspace, workspace_config)
        assert "No tickets here" in html and "kanban-empty-glyph" in html

    def test_filter_data_attrs(self, workspace, workspace_config):
        from holoctl.lib.board import Board
        Board(workspace, workspace_config).add(
            {"title": "T1", "priority": "p1", "agent": "developer",
             "sprint": "s1", "tags": "alpha"})
        html = _render_kanban(workspace, workspace_config)
        for attr in ('data-status="backlog"', 'data-p="p1"',
                     'data-agent="developer"', 'data-sprint="s1"', 'data-tags="alpha"'):
            assert attr in html
```

- [ ] **Step 2: Remove `_kanban_html` from the import block** at the top of the test file.

- [ ] **Step 3: Run**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py::TestKanbanHtml -v`
Expected: PASS. If markup differs (e.g. attribute ordering), open `partials/board/_card.html` and assert on the actual rendered substrings.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard.py
git commit -m "test(server): kanban tests assert rendered partial"
```

### Task 7: Rewrite `TestBoardPage` → assert via the board route

**Files:**
- Modify: `tests/test_dashboard.py` (`TestBoardPage`)

- [ ] **Step 1: Rewrite the class to use `client`**

```python
class TestBoardPage:
    def test_header_h1_and_path(self, client, alias):
        body = client.get(f"/project/{alias}/board").text
        assert '<h1 class="board-title">' in body
        assert 'class="board-path"' in body

    def test_new_ticket_cta_active(self, client, alias):
        body = client.get(f"/project/{alias}/board").text
        assert "data-new-ticket" in body
        assert 'aria-disabled="true"' not in body

    def test_live_indicator_in_topbar_not_board_header(self, client, alias):
        body = client.get(f"/project/{alias}/board").text
        assert "topbar-actions" in body
        assert body.find("topbar-actions") < body.find("live-indicator")
```

- [ ] **Step 2: Remove `_board_page` from the import block.**

- [ ] **Step 3: Run**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py::TestBoardPage -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard.py
git commit -m "test(server): board-page tests use route"
```

### Task 8: Rewrite `_list_html` + `_tree_html` tests → render partials

**Files:**
- Modify: `tests/test_dashboard.py` (the list/tree classes around lines 559-733)

- [ ] **Step 1: Rewrite using the list/tree presenters**

```python
from holoctl.server.views.list import list_context
from holoctl.server.views.tree import tree_context


def _render_list(project_root, config):
    from holoctl.lib.board import Board
    b = Board(project_root, config)
    ctx = list_context(b.ls(), config["board"]["statuses"], project_root.name)
    return render("partials/board/_list.html", **ctx)


def _render_tree(project_root, config):
    from holoctl.lib.board import Board
    b = Board(project_root, config)
    ctx = tree_context(b.ls(), project_root.name)
    return render("partials/board/_tree.html", **ctx)
```

Convert each existing `_list_html(...)` / `_tree_html(...)` assertion to call `_render_list(...)` / `_render_tree(...)`. Preserve the behaviors asserted today: list column headers (ID/Title/Status/…), per-row `data-*`, bulk-action bar, group headers + counts; tree nesting glyphs, parent/child indentation, empty state. Read `partials/board/_list.html` and `_tree.html` to confirm the exact class names before asserting.

- [ ] **Step 2: Remove `_list_html`, `_tree_html` from imports.**

- [ ] **Step 3: Run**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py -k "List or Tree or list or tree" -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard.py
git commit -m "test(server): list/tree tests assert rendered partials"
```

### Task 9: Rewrite `_ticket_detail_page` tests → assert via the detail route

**Files:**
- Modify: `tests/test_dashboard.py` (`TestTicketDetailPage` + any detail asserts around 812-1259)

- [ ] **Step 1: Rewrite using `client`**

For each existing case, create the ticket with `Board`, set its body where the test needs prose, then GET `/project/{alias}/board/{id}` and assert on rendered structure. Example:

```python
class TestTicketDetailPage:
    def test_renders_title_and_body(self, client, alias, workspace, workspace_config):
        from holoctl.lib.board import Board
        b = Board(workspace, workspace_config)
        t = b.add({"title": "Detail me", "agent": "developer"})
        b.set_body(t["id"], "## Description\n\nReal body.\n")
        body = client.get(f"/project/{alias}/board/{t['id']}").text
        assert "Detail me" in body
        assert "Real body." in body
        assert 'class="detail-grid"' in body

    def test_properties_and_rails(self, client, alias, workspace, workspace_config):
        from holoctl.lib.board import Board
        b = Board(workspace, workspace_config)
        t = b.add({"title": "Props", "priority": "p1", "agent": "developer"})
        body = client.get(f"/project/{alias}/board/{t['id']}").text
        assert "Properties" in body and "Activity" in body
        assert 'data-p="p1"' in body

    def test_parent_child_link(self, client, alias, workspace, workspace_config):
        from holoctl.lib.board import Board
        b = Board(workspace, workspace_config)
        parent = b.add({"title": "Parent", "agent": "developer"})
        child = b.add({"title": "Child", "agent": "developer", "parent": parent["id"]})
        body = client.get(f"/project/{alias}/board/{child['id']}").text
        assert parent["id"] in body  # Linked rail references the parent
```

Map every behavior the old tests covered (empty-body placeholder, kind chip, source chip, depends/blocks linked rows, activity ordering) onto a route-level assertion. The body-rendering ones now expect markdown-it output (`<h1>/<ul>/<a>`), not the old custom markup.

- [ ] **Step 2: Remove `_ticket_detail_page` from imports.**

- [ ] **Step 3: Run the whole dashboard test module**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py -v`
Expected: PASS. The import block at the top should now reference **no** dead helpers.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard.py
git commit -m "test(server): detail tests use route + markdown-it output"
```

### Task 10: Delete the dead code from `app.py`

**Files:**
- Modify: `holoctl/server/app.py`

- [ ] **Step 1: Confirm zero production references**

Run: `.venv/Scripts/python.exe -m pytest -q` (full suite green before deleting).
Run a grep to confirm only `app.py` defines them:
`grep -rn "_kanban_html\|_list_html\|_tree_html\|_board_page\|_ticket_detail_page\|_board_controls_html\|_list_row_html" holoctl tests`
Expected: matches only inside `app.py` (definitions) — none in `routes/`, `views/`, or `tests/`.

- [ ] **Step 2: Delete**

Remove from `app.py`: `_kanban_html`, `_list_row_html`, `_list_html`, `_tree_html`, `_board_page`, `_board_controls_html`, `_ticket_detail_page`, the chip string helpers (`_repo_chip_html`, `_deps_chip_html`, `_kind_chip_html`, `_source_chip_html`, `_parent_chip_html`), the `_render_markdown`/`_strip_empty_sections`/`_is_placeholder_only`/`_PLACEHOLDER_PATTERNS` leftovers, the `_e` helper, and the orphan constants `_SVG_ATTRS`/`_ICON_*`/`_KIND_GLYPHS`/`_PROVIDER_GLYPHS` — **after** confirming via grep that templates (`templates/icons/*.svg`, partials) own the icons/glyphs now. Keep the temporary re-export shims from Tasks 3-5 only if still referenced; otherwise remove them too and import directly where used.

- [ ] **Step 3: Move the `_not_found_html` helper**

Replace `_not_found_html` usages in routes with a direct `render("partials/_empty_state.html", msg=...)`, or a 3-line `not_found_html()` in `server/projects.py`. Remove `_not_found_html` from `app.py`.

- [ ] **Step 4: Run full suite + gates**

Run: `.venv/Scripts/python.exe -m pytest -q`
Run: `.venv/Scripts/python.exe -m ruff check holoctl tests`
Run: `.venv/Scripts/python.exe -m mypy holoctl`
Expected: all green. `app.py` is now ~300-400 lines (wiring + API + SSE).

- [ ] **Step 5: Commit**

```bash
git add holoctl/server/app.py holoctl/server/routes holoctl/server/projects.py
git commit -m "refactor(server): delete dead string-builders; app.py is thin wiring"
```

---

## Phase 3 — Editorial visual identity

CSS only (plus tiny template class hooks). The `dashboard_css` fixture concatenates `static/css/*` per `index.css` imports — use it for token-presence assertions. Visual verification: run `.venv/Scripts/hctl.exe serve` in a workspace and open `http://127.0.0.1:4242` (the dev can dogfood on the holoctl repo via `hctl init`). Check **both** themes on every surface.

### Task 11: Rewrite `tokens.css` (the locked Editorial system)

**Files:**
- Modify: `holoctl/server/static/css/tokens.css`
- Test: `tests/test_dashboard.py` (new `TestEditorialTokens` using `dashboard_css`)

- [ ] **Step 1: Write the failing token test**

```python
class TestEditorialTokens:
    def test_fonts_imported(self, dashboard_css):
        assert "Fraunces" in dashboard_css
        assert "Inter" in dashboard_css
        assert "JetBrains Mono" in dashboard_css

    def test_serif_token_present(self, dashboard_css):
        assert "--font-serif" in dashboard_css

    def test_terracotta_accent(self, dashboard_css):
        # accent defined in terms of the terracotta ramp
        assert "--accent" in dashboard_css
        assert "#c2410c" in dashboard_css or "#ea580c" in dashboard_css

    def test_both_themes_defined(self, dashboard_css):
        assert '[data-theme="light"]' in dashboard_css
        assert '[data-theme="dark"]' in dashboard_css
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py::TestEditorialTokens -v` → FAIL.

- [ ] **Step 2: Rewrite `tokens.css`**

Replace the `@import` font line with Fraunces + Inter + JetBrains Mono. Define the type tokens (`--font` = Inter stack, `--font-serif` = Fraunces stack, `--font-mono` = JetBrains Mono). Rewrite `[data-theme="light"]` (canonical) and `[data-theme="dark"]` with the warm palette: off-white canvas (`#f3f2ee`), warm card/surfaces, hairline warm borders, warm near-black dark surfaces, and `--accent` on the terracotta ramp (`#c2410c` light / a lighter terracotta for dark). Keep the existing token *names* (`--bg-0..3`, `--bg-card`, `--text-0..3`, `--accent`, `--accent-hover`, `--accent-subtle`, status colors, `--shadow-*`, radii, `--ease`) so downstream CSS keeps working — only the *values* and the new `--font-serif` change.

- [ ] **Step 3: Run the token test + route smoke**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py::TestEditorialTokens tests/test_dashboard.py::TestReadRoutes -v`
Expected: PASS.

- [ ] **Step 4: Visual check, then commit**

Serve and confirm the board loads in both themes without obvious breakage (colors shift; layout intact).

```bash
git add holoctl/server/static/css/tokens.css tests/test_dashboard.py
git commit -m "feat(ui): Editorial token system (warm palette, Fraunces, terracotta)"
```

### Task 12: Serif titles + base typography

**Files:**
- Modify: `holoctl/server/static/css/main.css` (or `layout.css`)
- Modify: templates where titles need the serif hook (`board-title`, `detail-title`, `dr-card-title`, section titles, home headings)

- [ ] **Step 1:** Add base rules: `body { font-family: var(--font); }`, and apply `font-family: var(--font-serif)` to the title classes (`.board-title`, `.detail-title`, `.dr-card-title`, `.detail-section-title`, home page `h1`/`h2`). Tune `letter-spacing`/weight per the mockup (600 weight, slight negative tracking). Keep card titles configurable — start with serif on `.kc-title`/`.lr-title-link`, ready to revert per the spec's risk note.
- [ ] **Step 2:** Visual check both themes; confirm serif renders (font loaded).
- [ ] **Step 3: Commit**

```bash
git add holoctl/server/static/css/main.css holoctl/server/templates
git commit -m "feat(ui): serif titles + base typography"
```

### Task 13: Board surface polish (kanban / list / tree + controls)

**Files:**
- Modify: `static/css/card.css`, `kanban.css`, `list.css`, `tree.css`, `controls.css`, `chips.css`, `buttons.css`

- [ ] **Step 1:** Apply Editorial spacing/typography to the board: airy column gaps, generous card padding, hairline warm borders, terracotta only on primary CTA / active view tab / p1 markers, mono for IDs. Use existing tokens (Task 11) — no new colors. Match the approved `board-completo` mockup density.
- [ ] **Step 2:** Visual check kanban, list, tree in both themes.
- [ ] **Step 3: Commit** `git commit -am "feat(ui): Editorial board surfaces"`

### Task 14: Detail page polish

**Files:**
- Modify: `static/css/detail.css`, `markdown.css`

- [ ] **Step 1:** Restyle the detail header (large serif title, status/priority pills), the two-column grid, and the right-rail cards (Properties / Linked / Activity). Update `markdown.css` for the **new markdown-it output** (`<h1-3>`, `<ul>/<ol>`, `<table>`, `<a>`, `<code>`, task-list `<input>`); confirm headings/tables/links/checkboxes look right.
- [ ] **Step 2:** Visual check a ticket with a rich body (headings, a table, a link, a checklist) in both themes.
- [ ] **Step 3: Commit** `git commit -am "feat(ui): Editorial detail page + markdown styles"`

### Task 15: Home + secondary tabs (Repos / Agents / Commands / Context)

**Files:**
- Modify: `static/css/home.css`, `agents.css`, `context.css`, `tabs.css`, `back-link.css`, `section-header.css`, `filetree.css`, `empty.css`

- [ ] **Step 1:** Bring the home page and the four secondary tabs to the same Editorial language (serif section headers, warm cards, terracotta accents, consistent spacing). These are mostly token-driven once Tasks 11-13 land; fix any surface-specific overrides still using old hardcoded colors. Grep the CSS for stray hex values that bypass tokens: `grep -rn "#[0-9a-fA-F]\{6\}" holoctl/server/static/css` and fold them into tokens where they should theme.
- [ ] **Step 2:** Visual check every tab in both themes.
- [ ] **Step 3: Commit** `git commit -am "feat(ui): Editorial home + secondary tabs"`

### Task 16: Topbar / shell / SSE-swapped fragments + final pass

**Files:**
- Modify: `static/css/layout.css`, `tabs.css`, `toast.css`, `animations.css`, `responsive.css`

- [ ] **Step 1:** Restyle the topbar (serif wordmark, LIVE indicator, theme toggle), tabs, toasts. Confirm the SSE-swapped kanban/list fragments (Task 6/8 endpoints) render identically to the full-page versions (same partials → they should). Sanity-check responsive breakpoints didn't break with the new spacing.
- [ ] **Step 2:** Full visual sweep: every surface, both themes, plus a live SSE update (move a ticket via CLI and watch the board refresh styled).
- [ ] **Step 3: Final gates + commit**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check holoctl tests && .venv/Scripts/python.exe -m mypy holoctl`
Expected: all green.

```bash
git commit -am "feat(ui): Editorial shell, topbar, fragments; final pass"
```

---

## Self-review notes

- **Spec coverage:** visual system → Tasks 11-16; delete dead code → Task 10; relocate live helpers → Tasks 3-5; markdown swap → Tasks 1-2; thin `app.py` → Task 10; re-point tests → Tasks 3-9; all surfaces → Tasks 13-16; both themes → verification step in every Phase-3 task.
- **Work-order safety:** tests are re-pointed (Tasks 6-9) before deletion (Task 10); markdown swap (Task 2) precedes detail-test rewrite (Task 9) so those tests assert the new output.
- **Naming consistency:** relocated functions are renamed to public (`format_due`, `ticket_preview`, `read_ticket_activity`, `render_markdown`, `strip_empty_sections`, `get_project(s)`); temporary `_`-prefixed re-export shims in `app.py` are removed in Task 10.
- **Deferred:** command-center features, journal/memory/curator views, multi-workspace (sub-project 2).
```
