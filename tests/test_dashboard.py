"""Tests for the FastAPI dashboard.

Covers:
  - card-rendering helpers (initials, hue, due date, body preview);
  - the kanban / board-page HTML output (new Phase-1 markup contract);
  - POST mutation endpoints (`tickets`, `tickets/{id}/move`).

The dashboard reads its workspace from cwd via `find_project_root()`. We
chdir into a fresh `workspace` fixture and clear the projects cache so
the routes see the test repo, not whatever real workspace happens to be
above the test runner.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# The dashboard is an optional extra (`holoctl[dashboard]`); skip this whole
# module cleanly when the web stack isn't installed rather than erroring out.
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import json
import re

from holoctl.lib.board import Board
import holoctl.server.projects as projects_module
from holoctl.server.app import app
from holoctl.server.views.avatars import avatar_hue as _avatar_hue, initials as _initials
from holoctl.server.views.dates import format_iso_datetime as _format_iso_datetime, format_relative_date as _format_relative_date
from holoctl.server.jinja import render
from holoctl.server.views.board import board_context
from holoctl.server.views.list import list_context
from holoctl.server.views.tree import tree_context
from holoctl.server.views.card import format_due, ticket_preview
from holoctl.server.views.detail import read_ticket_activity, detail_context


# ── Module-level rendering helpers ───────────────────────────────────────────


def _render_kanban(project_root: Path, config: dict) -> str:
    """Render the kanban partial directly via Jinja (no HTTP round-trip)."""
    b = Board(project_root, config)
    project = {"alias": project_root.name, "name": config.get("project", {}).get("name", project_root.name), "path": str(project_root)}
    return render(
        "partials/board/_kanban.html",
        **board_context(project, b.ls(), config, view="kanban"),
    )


def _render_list(project_root: Path, config: dict) -> str:
    """Render the list partial directly via Jinja."""
    b = Board(project_root, config)
    return render(
        "partials/board/_list.html",
        **list_context(b.ls(), config["board"]["statuses"], project_root.name),
    )


def _render_tree(project_root: Path, config: dict) -> str:
    """Render the tree partial directly via Jinja."""
    b = Board(project_root, config)
    return render(
        "partials/board/_tree.html",
        **tree_context(b.ls(), project_root.name),
    )


def _render_detail(ticket: dict, body: str, alias: str,
                   workspace: Path, config: dict,
                   all_tickets=None, statuses=None) -> str:
    """Render the full detail page HTML via Jinja (no HTTP round-trip).

    # tabs/breadcrumbs omitted — structural chrome, not under test here
    """
    ctx = detail_context(
        ticket, body, alias,
        all_tickets=all_tickets,
        project_root=workspace,
        statuses=statuses or config["board"]["statuses"],
    )
    return render(
        "project/detail.html",
        title=ticket.get("id", ""),
        current_alias=alias,
        current_tab="board",
        breadcrumbs=[],
        tabs=None,
        tab_base=f"/project/{alias}",
        **ctx,
    )


# ── Helpers / fixtures ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_projects_cache():
    """Reset the 5-second project cache so tests can't see each other."""
    projects_module.PROJECTS_CACHE["data"] = None
    projects_module.PROJECTS_CACHE["ts"] = 0.0
    yield
    projects_module.PROJECTS_CACHE["data"] = None
    projects_module.PROJECTS_CACHE["ts"] = 0.0


@pytest.fixture
def dashboard(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """Chdir into the workspace so the dashboard discovers it via cwd."""
    monkeypatch.chdir(workspace)
    return workspace


@pytest.fixture
def client(dashboard: Path) -> TestClient:
    return TestClient(app)


@pytest.fixture
def alias(dashboard: Path) -> str:
    return dashboard.name


# ── Helpers: _initials ────────────────────────────────────────────────────────


class TestInitials:
    def test_simple_word(self):
        assert _initials("developer") == "DE"

    def test_two_words(self):
        assert _initials("Felipe Carillo") == "FC"

    def test_hyphenated(self):
        assert _initials("front-end") == "FE"

    def test_dotted(self):
        assert _initials("api.gateway") == "AG"

    def test_empty(self):
        assert _initials("") == "?"

    def test_whitespace_only(self):
        # Falls through to slicing the empty trimmed string — accept any short
        # value as long as it doesn't crash and is uppercase.
        out = _initials("   ")
        assert out == "" or out.isupper()


# ── Helpers: _avatar_hue ──────────────────────────────────────────────────────


class TestAvatarHue:
    def test_in_range(self):
        for name in ("alice", "bob", "carol", "dave", "eve", "frank", "grace"):
            assert 0 <= _avatar_hue(name) <= 5

    def test_deterministic(self):
        assert _avatar_hue("developer") == _avatar_hue("developer")

    def test_distinct_names_distribute(self):
        # We only need the hue to differ for at least two of these — not
        # all 10. Stable and non-trivial.
        names = ["alpha", "beta", "gamma", "delta", "epsilon",
                 "zeta", "eta", "theta", "iota", "kappa"]
        hues = {_avatar_hue(n) for n in names}
        assert len(hues) >= 2

    def test_empty(self):
        assert _avatar_hue("") == 0


# ── Helpers: _format_due ──────────────────────────────────────────────────────


class TestFormatDue:
    def test_iso_date(self):
        assert format_due("2026-05-09") == "May 9"

    def test_iso_datetime(self):
        assert format_due("2026-12-25T14:00:00Z") == "Dec 25"

    def test_invalid(self):
        assert format_due("not a date") == ""

    def test_empty(self):
        assert format_due("") == ""

    def test_none(self):
        assert format_due(None) == ""


# ── Helpers: _ticket_preview ──────────────────────────────────────────────────


class TestTicketPreview:
    def test_template_only_returns_empty(self, workspace: Path, workspace_config: dict):
        """A freshly-created ticket has only template/placeholder content;
        the preview helper should produce no text rather than leaking
        `(objective criterion)`-style hints."""
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Plain ticket", "agent": "developer"})
        assert ticket_preview(workspace, ticket) == ""

    def test_substantive_body(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "With body", "agent": "developer"})
        # Replace the body with something real.
        b.set_body(ticket["id"], "## Description\n\nAdd JWT-based auth to the public API. Token refresh + revocation.\n")
        # Re-load to pick up the updated file ref.
        ticket = b.get(ticket["id"])
        out = ticket_preview(workspace, ticket)
        assert out.startswith("Add JWT-based auth")

    def test_truncates_long_lines(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Long", "agent": "developer"})
        b.set_body(ticket["id"], "## Description\n\n" + "x" * 200 + "\n")
        ticket = b.get(ticket["id"])
        out = ticket_preview(workspace, ticket, max_chars=80)
        assert len(out) <= 80
        assert out.endswith("…")

    def test_skips_headers(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Headers", "agent": "developer"})
        b.set_body(ticket["id"], "# Goal\n\n## Sub\n\nReal prose line here.\n")
        ticket = b.get(ticket["id"])
        out = ticket_preview(workspace, ticket)
        assert out == "Real prose line here."

    def test_strips_list_marker(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "List", "agent": "developer"})
        b.set_body(ticket["id"], "## Tasks\n\n- [x] Done item with substance here\n")
        ticket = b.get(ticket["id"])
        out = ticket_preview(workspace, ticket)
        assert out == "Done item with substance here"

    def test_missing_file(self, workspace: Path):
        # Ticket dict without a matching file → empty, no exception.
        ticket = {"id": "TST-999", "file": "tickets/does-not-exist.md"}
        assert ticket_preview(workspace, ticket) == ""


# ── TestKanbanHtml: rendered Jinja partial ────────────────────────────────────


class TestKanbanHtml:
    def test_emits_priority_dot_with_data_attr(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "priority": "p1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-prio-dot" data-p="p1"' in html
        # Old stripe / p-badge in the card top row are gone.
        assert "kanban-card-top" not in html  # legacy top row class
        assert "p-badge" not in html  # legacy priority badge inside card

    def test_emits_avatar_initials_with_hue(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="avatar-initials"' in html
        assert "data-hue=" in html
        # Initials of "developer" are "DE".
        assert ">DE</span>" in html

    def test_emits_inline_add_ticket(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        # Each column gets its own [+ Add ticket] button.
        for s in workspace_config["board"]["statuses"]:
            assert f'data-add-ticket data-status="{s}"' in html

    def test_emits_card_menu(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert "data-card-menu" in html

    def test_friendly_empty_state(self, workspace: Path, workspace_config: dict):
        html = _render_kanban(workspace, workspace_config)
        assert "No tickets here" in html
        assert "kanban-empty-glyph" in html

    def test_data_attrs_for_filtering(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "priority": "p1", "agent": "developer",
               "sprint": "s1", "tags": "alpha"})
        html = _render_kanban(workspace, workspace_config)
        assert 'data-status="backlog"' in html
        assert 'data-p="p1"' in html
        assert 'data-agent="developer"' in html
        assert 'data-sprint="s1"' in html
        assert 'data-tags="alpha"' in html


# ── TestBoardPage: full route response ────────────────────────────────────────


class TestBoardPage:
    def test_header_has_board_title_and_path(self, client: TestClient, alias: str, workspace: Path):
        html = client.get(f"/project/{alias}/board").text
        # The board header is rendered by partials/board/_header.html.
        # project_name comes from the project config ("TestProject").
        assert 'class="board-title"' in html
        assert 'class="board-path"' in html
        # The workspace path appears somewhere in the page.
        assert str(workspace) in html
        # The project name (not just the CSS class) must appear in the page.
        assert "TestProject" in html

    def test_new_ticket_cta_is_active(self, client: TestClient, alias: str):
        html = client.get(f"/project/{alias}/board").text
        # CTA renders, hooked to data-new-ticket — JS routes it to the
        # first column's inline form.
        assert "data-new-ticket" in html
        # No more aria-disabled placeholder.
        assert 'aria-disabled="true"' not in html

    def test_live_indicator_in_topbar_not_board_header(self, client: TestClient, alias: str):
        # LIVE moved to the topbar (rendered by the route via `actions=`),
        # so it appears before the board-header in the document.
        html = client.get(f"/project/{alias}/board").text
        assert "topbar-actions" in html
        idx_topbar = html.find("topbar-actions")
        idx_live = html.find("live-indicator")
        idx_board_header = html.find('class="board-header"')
        # topbar-actions → live-indicator appear before board-header.
        assert 0 <= idx_topbar < idx_live < idx_board_header


# ── Routes: read-only ─────────────────────────────────────────────────────────


class TestReadRoutes:
    def test_home_200(self, client: TestClient):
        r = client.get("/")
        assert r.status_code == 200

    def test_board_page_200_and_contains_kanban(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        assert r.status_code == 200
        body = r.text
        assert 'id="kanban"' in body
        # New control strip is present.
        assert "view-switcher" in body
        assert 'id="bc-search"' in body

    def test_board_page_emits_live_indicator_in_topbar(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        # The LIVE chip should be inside the topbar-actions container, not the
        # body's board-header.
        assert "topbar-actions" in r.text
        idx_topbar = r.text.find("topbar-actions")
        idx_live = r.text.find("live-indicator")
        idx_board_header = r.text.find('class="board-header"')
        assert 0 <= idx_topbar < idx_live < idx_board_header

    def test_board_html_fragment(self, client: TestClient, alias: str):
        r = client.get(f"/api/project/{alias}/board-html")
        assert r.status_code == 200
        # Fragment-level (just the kanban div).
        assert r.text.lstrip().startswith('<div class="kanban"')

    def test_static_assets_served(self, client: TestClient, dashboard_css: str):
        css = client.get("/static/css/index.css")
        js = client.get("/static/js/index.js")
        assert css.status_code == 200
        assert js.status_code == 200
        # Sanity: new tokens / classes shipped (checked against the resolved
        # css bundle since index.css is just @imports).
        assert "html, body { height: 100vh; overflow: hidden; }" in dashboard_css
        assert ".kc-prio-dot" in dashboard_css
        assert ".kanban-col-add" in dashboard_css


# ── Routes: POST /tickets (create) ────────────────────────────────────────────


class TestApiTicketCreate:
    def test_creates_with_title_only(self, client: TestClient, alias: str, workspace: Path, workspace_config: dict):
        r = client.post(f"/api/project/{alias}/tickets", json={"title": "My new ticket"})
        assert r.status_code == 201
        ticket = r.json()
        assert ticket["title"] == "My new ticket"
        assert ticket["status"] == "backlog"  # default
        assert ticket["priority"] == "p2"      # default
        # Persisted on disk.
        b = Board(workspace, workspace_config)
        assert any(t["title"] == "My new ticket" for t in b.ls())

    def test_creates_at_specified_status(self, client: TestClient, alias: str):
        r = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "Started ticket", "status": "doing"},
        )
        assert r.status_code == 201
        assert r.json()["status"] == "doing"

    def test_rejects_missing_title(self, client: TestClient, alias: str):
        r = client.post(f"/api/project/{alias}/tickets", json={"status": "doing"})
        assert r.status_code == 400
        assert "title" in r.json()["detail"].lower()

    def test_rejects_blank_title(self, client: TestClient, alias: str):
        r = client.post(f"/api/project/{alias}/tickets", json={"title": "   "})
        assert r.status_code == 400

    def test_rejects_unknown_agent(self, client: TestClient, alias: str):
        r = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "T", "agent": "ghost"},
        )
        assert r.status_code == 400
        assert "ghost" in r.json()["detail"].lower() or "agent" in r.json()["detail"].lower()

    def test_rejects_invalid_status(self, client: TestClient, alias: str):
        r = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "T", "status": "bogus"},
        )
        assert r.status_code == 400

    def test_unknown_project_404(self, client: TestClient):
        r = client.post("/api/project/no-such-project/tickets", json={"title": "T"})
        assert r.status_code == 404


# ── Routes: POST /tickets/{id}/move ───────────────────────────────────────────


class TestApiTicketMove:
    def test_moves_to_valid_status(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "Move me"}
        ).json()
        r = client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move",
            json={"status": "doing"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["from"] == "backlog"
        assert body["to"] == "doing"

    def test_archives_via_cancelled(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "Archive me"}
        ).json()
        r = client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move",
            json={"status": "cancelled"},
        )
        assert r.status_code == 200

    def test_invalid_status_400(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move",
            json={"status": "elsewhere"},
        )
        assert r.status_code == 400

    def test_missing_status_400(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move", json={}
        )
        assert r.status_code == 400

    def test_unknown_ticket_404(self, client: TestClient, alias: str):
        r = client.post(
            f"/api/project/{alias}/tickets/TST-999/move",
            json={"status": "doing"},
        )
        assert r.status_code == 404


# ── Routes: PATCH /tickets/{id} ───────────────────────────────────────────────


class TestApiTicketPatch:
    def test_priority_update(self, client: TestClient, alias: str, workspace: Path, workspace_config: dict):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T", "priority": "p2"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "priority", "value": "p1"},
        )
        assert r.status_code == 200
        assert r.json()["value"] == "p1"
        # Persisted.
        b = Board(workspace, workspace_config)
        assert b.get(created["id"])["priority"] == "p1"

    def test_sprint_update(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "sprint", "value": "s2"},
        )
        assert r.status_code == 200
        assert r.json()["value"] == "s2"

    def test_status_update_recounts(self, client: TestClient, alias: str, workspace: Path, workspace_config: dict):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "status", "value": "doing"},
        )
        assert r.status_code == 200
        # Counts in meta should have moved.
        b = Board(workspace, workspace_config)
        assert b.stat()["doing"] == 1

    def test_agent_update_with_array(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "agent", "value": ["developer"]},
        )
        assert r.status_code == 200

    def test_rejects_unknown_field(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "id", "value": "TST-002"},
        )
        assert r.status_code == 400
        assert "editable" in r.json()["detail"].lower() or "id" in r.json()["detail"].lower()

    def test_rejects_invalid_priority(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "priority", "value": "p9"},
        )
        assert r.status_code == 400

    def test_missing_field_400(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"value": "p1"},
        )
        assert r.status_code == 400

    def test_unknown_ticket_404(self, client: TestClient, alias: str):
        r = client.patch(
            f"/api/project/{alias}/tickets/TST-999",
            json={"field": "priority", "value": "p1"},
        )
        assert r.status_code == 404


# ── Helper: _format_relative_date ─────────────────────────────────────────────


class TestFormatRelativeDate:
    def test_iso(self):
        from datetime import timezone
        disp, full = _format_relative_date("2026-05-09T12:00:00Z", tz=timezone.utc)
        assert disp == "May 9"
        assert full == "2026-05-09T12:00:00Z"

    def test_iso_converts_to_target_tz(self):
        # 00:30 UTC on May 9 → 21:30 May 8 in UTC-3 (Brasília).
        from datetime import timezone, timedelta
        disp, _ = _format_relative_date(
            "2026-05-09T00:30:00Z", tz=timezone(timedelta(hours=-3))
        )
        assert disp == "May 8"

    def test_empty(self):
        disp, full = _format_relative_date("")
        assert disp == "—"
        assert full == ""

    def test_invalid(self):
        disp, full = _format_relative_date("not a date")
        assert disp.startswith("not")
        assert full == "not a date"


# ── TestListHtml: rendered Jinja partial ──────────────────────────────────────


class TestListHtml:
    def test_renders_one_row_per_ticket(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer"})
        html = _render_list(workspace, workspace_config)
        assert html.count('class="ticket-row kanban-card"') == 2

    def test_groups_by_status(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer", "status": "doing"})
        html = _render_list(workspace, workspace_config)
        # One group div per status, in config order.
        for s in workspace_config["board"]["statuses"]:
            assert f'data-bucket="{s}"' in html
        # Backlog group has 1, doing group has 1.
        assert html.find('data-bucket="backlog"') < html.find('data-bucket="doing"')

    def test_emits_select_checkbox_per_row(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        html = _render_list(workspace, workspace_config)
        assert "data-ticket-select" in html
        assert "data-ticket-select-all" in html

    def test_emits_inline_edit_buttons(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "priority": "p1", "agent": "developer"})
        html = _render_list(workspace, workspace_config)
        assert 'data-edit-field="status"' in html
        assert 'data-edit-field="priority"' in html

    def test_emits_bulk_bar(self, workspace: Path, workspace_config: dict):
        html = _render_list(workspace, workspace_config)
        assert 'id="list-bulk-bar"' in html
        assert "data-bulk-move" in html
        assert "data-bulk-archive" in html

    def test_carries_filter_data_attrs(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "priority": "p1", "agent": "developer", "sprint": "s1", "tags": "auth"})
        html = _render_list(workspace, workspace_config)
        # Same data-* contract as kanban cards so filter/search/sort
        # logic on .kanban-card works in both views.
        assert 'data-status="backlog"' in html
        assert 'data-p="p1"' in html
        assert 'data-agent="developer"' in html
        assert 'data-sprint="s1"' in html
        assert 'data-tags="auth"' in html

    def test_off_config_status_lands_in_unsorted(self, workspace: Path, workspace_config: dict):
        # Manually inject a ticket with an unknown status (simulates a
        # config change that left old tickets behind).
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        tickets = b.ls()
        # Inject off-config status directly into the context.
        tickets[0] = {**tickets[0], "status": "rogue"}
        statuses = workspace_config["board"]["statuses"]
        html = render(
            "partials/board/_list.html",
            **list_context(tickets, statuses, workspace.name),
        )
        assert "(unsorted)" in html


# ── Route: ?view=list ─────────────────────────────────────────────────────────


class TestViewSwitcher:
    def test_default_view_is_kanban(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        assert r.status_code == 200
        # Kanban container exists; list-view does not.
        assert 'id="kanban"' in r.text
        assert 'id="list-view"' not in r.text

    def test_view_list_renders_list_markup(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=list")
        assert r.status_code == 200
        assert 'id="list-view"' in r.text
        assert 'class="list-head"' in r.text
        assert 'id="kanban"' not in r.text
        # board-controls advertises its current view so the JS knows
        # which fragment endpoint to fetch on SSE swaps.
        assert 'data-current-view="list"' in r.text

    def test_view_kanban_explicit(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=kanban")
        assert r.status_code == 200
        assert 'id="kanban"' in r.text
        assert 'data-current-view="kanban"' in r.text

    def test_invalid_view_falls_back_to_kanban(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=ufo")
        assert r.status_code == 200
        assert 'id="kanban"' in r.text

    def test_view_switcher_marks_active_tab(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=list")
        # The List tab must carry .active and aria-selected="true".
        assert 'data-view="list" role="tab" aria-selected="true"' in r.text
        assert '.view-tab active" data-view="kanban"' not in r.text

    def test_view_tree_renders_tree_markup(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=tree")
        assert r.status_code == 200
        assert 'id="tree-view"' in r.text
        assert 'data-current-view="tree"' in r.text
        assert 'id="kanban"' not in r.text
        # The Tree tab is in the switcher and marked active.
        assert 'data-view="tree" role="tab" aria-selected="true"' in r.text


# ── TestTreeHtml: rendered Jinja partial ──────────────────────────────────────


class TestTreeHtml:
    def test_renders_root_and_children_with_data_attrs(
        self, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        spec = b.add({"title": "Auth flow", "kind": "spec"})
        c1 = b.add({"title": "Sign", "agent": "developer", "parent": spec["id"]})
        c2 = b.add({"title": "Verify", "agent": "developer", "parent": spec["id"]})

        html = _render_tree(workspace, workspace_config)
        # Every ticket has its own row…
        assert f'data-id="{spec["id"]}"' in html
        assert f'data-id="{c1["id"]}"' in html
        assert f'data-id="{c2["id"]}"' in html
        # Children carry data-parent so DOM-side filters can still group.
        assert f'data-parent="{spec["id"]}"' in html
        # Depth signal — the spec is depth 0, children are depth 1.
        assert 'data-depth="0"' in html
        assert 'data-depth="1"' in html
        # Connector glyphs appear for the children (CSS draws the actual lines).
        assert "tr-glyph-mid" in html or "tr-glyph-last" in html

    def test_orphan_with_missing_parent_promotes_to_root(
        self, workspace: Path, workspace_config: dict
    ):
        """A ticket whose declared parent is absent from the board still renders —
        as a root, not as a dangling row that disappears from the tree."""
        b = Board(workspace, workspace_config)
        # Build directly: an orphan whose parent ID was never created.
        b.add({"title": "Orphan", "agent": "developer"})
        # Inject a phantom parent reference via the index so we can simulate
        # a dangling ref without going through add()'s validation.
        idx_path = workspace / ".holoctl" / "board" / "index.json"
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        data["tickets"][0]["parent"] = "PHANTOM-999"
        idx_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")

        tickets = b.ls()
        html = render(
            "partials/board/_tree.html",
            **tree_context(tickets, workspace.name),
        )
        # The orphan still appears at depth 0 (no glyph gutter).
        assert 'data-depth="0"' in html
        assert "Orphan" in html

    def test_empty_workspace_shows_friendly_message(
        self, workspace: Path, workspace_config: dict
    ):
        html = _render_tree(workspace, workspace_config)
        assert "tree-empty" in html or "No tickets" in html


class TestApiListHtmlFragment:
    def test_returns_list_view_fragment(self, client: TestClient, alias: str):
        r = client.get(f"/api/project/{alias}/list-html")
        assert r.status_code == 200
        body = r.text.lstrip()
        assert body.startswith('<div class="list-view"')
        assert 'class="list-head"' in body

    def test_unknown_project_404(self, client: TestClient):
        r = client.get("/api/project/no-such/list-html")
        assert r.status_code == 404


# ── Helper: _format_iso_datetime ──────────────────────────────────────────────


class TestFormatIsoDatetime:
    def test_iso_z(self):
        from datetime import timezone
        assert _format_iso_datetime("2026-05-07T14:22:36Z", tz=timezone.utc) == "2026-05-07 14:22:36"

    def test_iso_no_tz(self):
        # Naive strings are displayed as-is — no conversion.
        assert _format_iso_datetime("2026-05-07T14:22:36") == "2026-05-07 14:22:36"

    def test_iso_no_seconds_pads(self):
        # Naive string missing the seconds component is padded with `:00`.
        assert _format_iso_datetime("2026-05-07T14:22") == "2026-05-07 14:22:00"

    def test_iso_converts_to_target_tz(self):
        from datetime import timezone, timedelta
        assert _format_iso_datetime(
            "2026-05-07T14:22:36Z", tz=timezone(timedelta(hours=-3))
        ) == "2026-05-07 11:22:36"

    def test_invalid(self):
        # Returns the first 19 chars when it can't parse.
        assert _format_iso_datetime("not a date") == "not a date"

    def test_empty(self):
        assert _format_iso_datetime("") == ""


# ── Helper: _read_ticket_activity ─────────────────────────────────────────────


class TestReadTicketActivity:
    def test_returns_only_matching_ticket(self, workspace: Path):
        log = workspace / ".holoctl" / "activity.jsonl"
        log.write_text(
            '{"ts":"2026-05-04T10:00:00Z","type":"ticket.created","ticket":"TST-001","actor":"cli"}\n'
            '{"ts":"2026-05-05T10:00:00Z","type":"ticket.body_updated","ticket":"TST-001","actor":"cli"}\n'
            '{"ts":"2026-05-06T10:00:00Z","type":"ticket.created","ticket":"TST-002","actor":"cli"}\n',
            encoding="utf-8",
        )
        out = read_ticket_activity(workspace, "TST-001")
        assert len(out) == 2
        assert all(e["type"].startswith("ticket.") for e in out)

    def test_skips_corrupt_lines(self, workspace: Path):
        log = workspace / ".holoctl" / "activity.jsonl"
        log.write_text(
            'not-json\n'
            '{"ts":"2026-05-04T10:00:00Z","type":"ticket.created","ticket":"TST-001"}\n'
            '\n',
            encoding="utf-8",
        )
        out = read_ticket_activity(workspace, "TST-001")
        assert len(out) == 1

    def test_missing_log(self, tmp_path: Path):
        # Bare directory, no .holoctl/activity.jsonl.
        assert read_ticket_activity(tmp_path, "TST-001") == []


# ── TestTicketDetailPage: rendered Jinja output ───────────────────────────────


class TestTicketDetailPage:
    def test_renders_toolbar_header_grid(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer", "priority": "p1"})
        html = _render_detail(ticket, "## Description\n\nReal body.\n",
                              workspace.name, workspace, workspace_config)
        # Wrapper carries the data-flag the CSS uses to swap layout mode.
        assert "data-detail-page" in html
        assert 'class="detail-toolbar"' in html
        assert 'class="detail-header"' in html
        assert 'class="detail-grid"' in html
        # Two scroll columns.
        assert 'class="detail-main"' in html
        assert 'class="detail-rail"' in html

    def test_header_has_dot_id_pills_title(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Hello world", "priority": "p1", "agent": "developer"})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        # Priority dot, ID, status pill, priority pill, h1 title.
        assert 'class="kc-prio-dot" data-p="p1"' in html
        assert f'>{ticket["id"]}</span>' in html
        assert 'class="lr-status" data-status="backlog"' in html
        assert 'class="lr-prio-pill" data-p="p1"' in html
        assert '<h1 class="detail-title">Hello world</h1>' in html

    def test_toolbar_has_back_link_and_actions(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        alias = workspace.name
        html = _render_detail(ticket, "", alias, workspace, workspace_config)
        assert f'href="/project/{alias}/board"' in html
        assert 'data-edit-field="status"' in html  # Move ▾
        assert 'data-card-menu' in html             # ⋯ menu

    def test_properties_card_has_editable_fields(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({
            "title": "T", "agent": "developer", "priority": "p1",
            "sprint": "s1", "tags": "auth,api",
        })
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        # Status/priority via .lr-edit; agents/sprint/tags via the new
        # text popover.
        assert 'data-edit-field="status"' in html
        assert 'data-edit-field="priority"' in html
        assert 'data-edit-text-field="agent"' in html
        assert 'data-edit-text-field="sprint"' in html
        assert 'data-edit-text-field="tags"' in html
        # data-current carries the existing value for prefill.
        assert 'data-current="developer"' in html
        assert 'data-current="s1"' in html
        assert 'data-current="auth,api"' in html

    def test_properties_dates_pretty_formatted(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        # Pretty `YYYY-MM-DD HH:MM` shows up; full ISO sits in the title attr.
        assert "Created" in html
        assert "Updated" in html
        assert ticket["created"][:10] in html  # YYYY-MM-DD prefix

    def test_linked_card_renders_depends(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        ticket_b = b.add({"title": "B", "agent": "developer", "depends": a["id"]})
        all_t = b.ls()
        alias = workspace.name
        html = _render_detail(ticket_b, "", alias, workspace, workspace_config,
                              all_tickets=all_t)
        assert "depends on" in html
        assert f'href="/project/{alias}/board/{a["id"]}"' in html

    def test_linked_card_renders_blocks_reverse(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        ticket_b = b.add({"title": "B", "agent": "developer", "depends": a["id"]})
        # Detail page for A should surface "blocks B" via reverse scan.
        a_full = b.get(a["id"])
        all_t = b.ls()
        alias = workspace.name
        html = _render_detail(a_full, "", alias, workspace, workspace_config,
                              all_tickets=all_t)
        assert "blocks" in html
        assert f'href="/project/{alias}/board/{ticket_b["id"]}"' in html

    def test_linked_card_empty_state(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config,
                              all_tickets=b.ls())
        assert "No linked tickets" in html

    def test_activity_card_includes_created(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        assert 'class="dr-activity"' in html
        assert "Created" in html  # derived event always present

    def test_activity_card_includes_completed_when_done(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        b.move(ticket["id"], "done")
        ticket = b.get(ticket["id"])
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        assert "Marked done" in html
        # Activity is sorted newest-first; scope the position check to the
        # <ol class="dr-activity"> block so the Properties card's "Created"
        # date label doesn't muddy the comparison.
        m = re.search(r'<ol class="dr-activity">(.*?)</ol>', html, re.S)
        assert m, "activity ol not found"
        activity = m.group(1)
        assert activity.find("Marked done") < activity.find("Created")

    def test_activity_includes_log_entries(self, workspace: Path, workspace_config: dict):
        # Seed an activity log entry for our ticket so the helper picks it up.
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        log = workspace / ".holoctl" / "activity.jsonl"
        log.write_text(
            log.read_text(encoding="utf-8") +
            f'{{"ts":"2026-05-08T10:00:00Z","type":"ticket.body_updated","ticket":"{ticket["id"]}","actor":"cli"}}\n',
            encoding="utf-8",
        )
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        assert "Body edited" in html

    def test_renders_markdown_body(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _render_detail(
            ticket,
            "## Description\n\nThis is the **body**.\n",
            workspace.name, workspace, workspace_config,
        )
        assert "<strong>body</strong>" in html


# ── Route: /project/{alias}/board/{ticket_id} ────────────────────────────────


class TestTicketDetailRoute:
    def test_renders_detail_page(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "Live ticket", "agent": "developer", "priority": "p1"},
        ).json()
        r = client.get(f"/project/{alias}/board/{created['id']}")
        assert r.status_code == 200
        body = r.text
        assert "data-detail-page" in body
        assert 'class="detail-toolbar"' in body
        assert 'class="detail-rail"' in body
        # Properties card holds the new editable controls.
        assert 'data-edit-text-field="sprint"' in body

    def test_unknown_ticket_404(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board/TST-999")
        assert r.status_code == 404

    def test_blocks_link_appears(self, client: TestClient, alias: str):
        a = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "A", "agent": "developer"},
        ).json()
        client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "B", "agent": "developer", "depends": [a["id"]]},
        )
        # A should advertise "blocks <B-id>" on its detail page.
        r = client.get(f"/project/{alias}/board/{a['id']}")
        assert r.status_code == 200
        assert "blocks" in r.text


# ── Phase 5: a11y + cleanup ───────────────────────────────────────────────────


class TestAccessibility:
    def test_lr_edit_status_has_aria(self, client: TestClient, alias: str):
        client.post(f"/api/project/{alias}/tickets", json={"title": "T"})
        r = client.get(f"/project/{alias}/board?view=list")
        # Status / priority chips advertise themselves as listbox triggers.
        assert 'aria-haspopup="listbox"' in r.text
        assert 'aria-expanded="false"' in r.text

    def test_list_group_header_role_button(self, client: TestClient, alias: str):
        client.post(f"/api/project/{alias}/tickets", json={"title": "T"})
        r = client.get(f"/project/{alias}/board?view=list")
        # Group headers are clickable divs — must be keyboard-reachable.
        assert 'class="list-group-header"' in r.text
        assert 'role="button"' in r.text
        assert 'tabindex="0"' in r.text

    def test_kc_menu_has_aria_label(self, client: TestClient, alias: str):
        client.post(f"/api/project/{alias}/tickets", json={"title": "T"})
        r = client.get(f"/project/{alias}/board")
        # Icon-only ⋯ buttons need an accessible name.
        assert 'aria-label="Card actions"' in r.text

    def test_focus_visible_styles_present(self, client: TestClient, dashboard_css: str):
        # Tag the rule by its keyword so CSS-format changes don't break us.
        r = client.get("/static/css/index.css")
        assert r.status_code == 200
        assert ":focus-visible" in dashboard_css
        assert "prefers-reduced-motion" in dashboard_css


class TestCssCleanup:
    def test_legacy_kanban_card_classes_removed(self, dashboard_css: str):
        # These were Phase-1-era aliases; nothing emits them anymore.
        for sel in (".kanban-card-top", ".kanban-card-id",
                    ".kanban-card-title", ".kanban-card-meta",
                    ".kanban-card-dates"):
            assert sel + " " not in dashboard_css, f"legacy selector {sel} should be removed"

    def test_legacy_status_badge_removed(self, dashboard_css: str):
        # `.status-badge` was used by the old detail page; gone since Phase 4.
        assert ".status-badge" not in dashboard_css

    def test_legacy_p_badge_in_card_removed(self, dashboard_css: str):
        # `.p-badge` was the kanban card's old inline priority chip.
        # The new card uses `.kc-prio-dot` and the list view uses
        # `.lr-prio-pill`.
        assert ".p-badge " not in dashboard_css and ".p-badge\n" not in dashboard_css and ".p-badge{" not in dashboard_css


# ── Post-merge follow-up: horizontal scroll + repo + deps ─────────────────────


class TestKanbanHorizontalScroll:
    """Regression for the user-reported "horizontal scroll doesn't work".

    The bug: `.kanban` carried `min-width: fit-content`, which expanded the
    container to the sum of its column widths. The flex-item grew past its
    parent (`.content-body`) and `overflow-x: auto` had nothing left to
    scroll — the viewport just clipped the rightmost columns.
    """

    def test_min_width_fit_content_removed(self, dashboard_css: str):
        # Find the `.kanban {` block and assert the bad declaration is gone.
        m = re.search(r"\.kanban\s*\{[^}]*\}", dashboard_css)
        assert m, ".kanban block must exist in the served CSS"
        block = m.group(0)
        assert "min-width: fit-content" not in block, (
            "fit-content makes .kanban grow past its parent and silently kills "
            "the horizontal scroll between columns"
        )

    def test_kanban_uses_zero_min_width(self, dashboard_css: str):
        m = re.search(r"\.kanban\s*\{[^}]*\}", dashboard_css)
        block = m.group(0)
        # `min-width: 0` is the explicit override of flex's default
        # `min-width: auto` (content-sized) — without it, fixed-width
        # column children push the kanban past its parent again.
        assert "min-width: 0" in block
        # Sanity: overflow-x:auto stays so the scroll bar appears when the
        # columns collectively exceed the visible width.
        assert "overflow-x: auto" in block


class TestRepoChip:
    """Phase-6 follow-up: surface `projects` (repo / subproject) on cards.

    Tickets that touch a specific subproject can now declare it via
    `projects: [...]` and the dashboard shows it as a small mono pill on
    the card top row, in the list view, and as an editable property in
    the detail page Properties card.
    """

    def test_kanban_card_renders_repo_chip(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer",
               "projects": ["backend"]})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-repo"' in html
        # Single-project chip closes immediately after the name; multi adds
        # a trailing `<span class="kc-repo-extra">`.
        assert ">backend</span>" in html

    def test_kanban_card_no_chip_when_empty(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-repo"' not in html

    def test_kanban_card_extra_count_when_multiple(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer",
               "projects": ["backend", "web", "shared"]})
        html = _render_kanban(workspace, workspace_config)
        # Head project + `+N` indicator for the rest.
        assert ">backend " in html
        assert "+2" in html
        # Tooltip lists all of them so hover gives the full picture.
        assert 'title="repo: backend, web, shared"' in html

    def test_list_view_has_repo_column(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer", "projects": ["backend"]})
        html = _render_list(workspace, workspace_config)
        # New column header + cell.
        assert "lr-cell-repo" in html
        assert ">Repo<" in html
        assert ">backend</span>" in html

    def test_detail_page_properties_card_has_repo_field(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer",
                        "projects": ["backend", "web"]})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        assert 'data-edit-text-field="projects"' in html
        assert 'data-current="backend,web"' in html
        # Visible label.
        assert "Repo" in html


class TestDependsChip:
    """Phase-6 follow-up: surface `depends` (blocked-by IDs) on cards.

    Each card / row now shows the first dep ID and a `+N` count for the
    rest, plus a tooltip with the full list. Detail page already covered
    this in the Linked card.
    """

    def test_kanban_card_renders_deps(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        first = b.add({"title": "First", "agent": "developer"})
        b.add({"title": "Second", "agent": "developer",
               "depends": [first["id"]]})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-deps"' in html
        assert first["id"] in html  # the dep ID itself
        assert "↳" in html

    def test_kanban_card_deps_extra_count(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        c = b.add({"title": "C", "agent": "developer"})
        b.add({"title": "B", "agent": "developer",
               "depends": [a["id"], c["id"]]})
        html = _render_kanban(workspace, workspace_config)
        # First dep visible, +1 indicator for the second.
        assert "+1" in html
        assert f"depends on: {a['id']}, {c['id']}" in html

    def test_kanban_card_no_deps_chip_when_empty(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-deps"' not in html

    def test_list_view_has_deps_column(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer", "depends": [a["id"]]})
        html = _render_list(workspace, workspace_config)
        assert "lr-cell-deps" in html
        assert ">Deps<" in html
        assert a["id"] in html

    def test_data_attrs_carry_depends_csv(self, workspace: Path, workspace_config: dict):
        """Filter / search logic reads data-* — `data-depends` must round-trip
        across all three views so future filters can pivot on dependency too."""
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer", "depends": [a["id"]]})
        kanban_html = _render_kanban(workspace, workspace_config)
        list_html = _render_list(workspace, workspace_config)
        for html, label in ((kanban_html, "kanban"), (list_html, "list")):
            assert f'data-depends="{a["id"]}"' in html, f"{label} missed data-depends"


# ── Post-merge follow-up #2: detail scroll, Move popover, Day zoom ────────────


class TestDetailPageScrollContainment:
    """Regression for "card detail has no vertical scroll".

    `.content-body:has(> [data-detail-page])` was set to `overflow:
    hidden` but not `display: flex; flex-direction: column`, so the
    detail page's `flex: 1; min-height: 0` failed (parent wasn't flex).
    Page rendered at natural height and anything past the viewport got
    clipped silently. Independent column scrolls inside `.detail-main`
    and `.detail-rail` couldn't even start.
    """

    def test_content_body_becomes_flex_column_for_detail(self, dashboard_css: str):
        # Find the rule and assert it carries both overflow:hidden and the
        # flex-column setup. Without flex column on the parent, the
        # detail-page's flex children don't get sized correctly.
        m = re.search(
            r"\.content-body:has\(> \[data-detail-page\]\)\s*\{[^}]*\}",
            dashboard_css,
        )
        assert m, "content-body :has(detail-page) rule must exist"
        block = m.group(0)
        assert "overflow: hidden" in block
        assert "display: flex" in block
        assert "flex-direction: column" in block

    def test_detail_main_and_rail_scroll_independently(self, dashboard_css: str):
        # Sanity: each column still has its own overflow-y: auto so the
        # parent flex chain actually delivers usable scroll.
        m_main = re.search(
            r"\[data-detail-page\]\s*\.detail-main\s*\{[^}]*\}", dashboard_css,
        )
        assert m_main and "overflow-y: auto" in m_main.group(0)
        m_rail = re.search(r"\.detail-rail\s*\{[^}]*\}", dashboard_css)
        assert m_rail and "overflow-y: auto" in m_rail.group(0)


class TestDetailPageStatusList:
    """Regression for "Move ▾ button does nothing" on the detail page.

    The JS `statusList()` originally mined `.kanban-col[data-status]` to
    populate the Move/⋯ popovers. The detail page has no kanban columns,
    so the popover rendered empty — visually identical to "the button
    doesn't work". Server now stamps a `data-statuses` CSV onto the
    `[data-detail-page]` wrapper and the JS prefers that source.
    """

    def test_detail_wrapper_carries_data_statuses(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "T", "agent": "developer"},
        ).json()
        r = client.get(f"/project/{alias}/board/{created['id']}")
        assert r.status_code == 200
        # The default config ships 5 statuses — find them in the CSV.
        for s in ("backlog", "doing", "review", "done", "cancelled"):
            assert s in r.text
        # And the attribute itself, on the wrapper.
        assert 'data-detail-page data-statuses="' in r.text

    def test_detail_page_emits_status_csv(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config,
                              statuses=statuses)
        assert f'data-statuses="{",".join(statuses)}"' in html

    def test_status_list_js_prefers_data_statuses(self, dashboard_js: str):
        # Both lookups must ship — `[data-statuses]` is the new fallback
        # used outside the kanban view, the old kanban-col query stays
        # for views that mine the columns directly.
        assert "[data-statuses]" in dashboard_js
        assert ".kanban-col[data-status]" in dashboard_js
        # And `[data-statuses]` must appear *before* the column query in
        # the file so the new path takes precedence.
        i_attr = dashboard_js.find("[data-statuses]")
        i_col = dashboard_js.find(".kanban-col[data-status]")
        assert 0 <= i_attr < i_col, (
            "data-statuses lookup must come before the .kanban-col fallback "
            "in statusList() so the detail page's wrapper attr wins"
        )


# ── Tree row carries kanban-card so global filter/search reach it ─────────────


class TestTreeRowHasKanbanCardClass:
    def test_tree_view_route_emits_kanban_card_on_rows(self, client: TestClient, alias: str):
        # Seed one ticket so the tree has something to render.
        client.post(f"/api/project/{alias}/tickets",
                    json={"title": "Root", "agent": "developer"})
        r = client.get(f"/project/{alias}/board?view=tree")
        assert r.status_code == 200
        # The shared kanban-card class is what bcApplyFilter / bcCollectOptions
        # in static/js/board-controls.js look for — without it, search and
        # filter chips silently no-op on the tree.
        assert 'class="tree-row kanban-card"' in r.text


# ── Sort + Group selects only render on views that support them ──────────────


class TestControlsHiddenByView:
    """Tree has no concept of sort/group (would break hierarchy), so those
    selects must be omitted from the controls strip when view=tree.
    Kanban and list keep both."""

    def test_kanban_has_sort_and_group(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=kanban")
        assert 'id="bc-sort"' in r.text
        assert 'id="bc-group"' in r.text

    def test_list_has_sort_and_group(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=list")
        assert 'id="bc-sort"' in r.text
        assert 'id="bc-group"' in r.text

    def test_tree_hides_sort_and_group(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=tree")
        assert 'id="bc-sort"' not in r.text
        assert 'id="bc-group"' not in r.text


# ── Timeline view is removed — `?view=timeline` falls back to kanban ─────────


class TestTimelineRemoved:
    def test_view_timeline_falls_back_to_kanban(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=timeline")
        assert r.status_code == 200
        # _VALID_VIEWS coerces unknown values to kanban.
        assert 'id="kanban"' in r.text
        assert 'id="timeline-view"' not in r.text

    def test_timeline_tab_no_longer_in_switcher(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        assert 'data-view="timeline"' not in r.text

    def test_timeline_html_fragment_route_gone(self, client: TestClient, alias: str):
        r = client.get(f"/api/project/{alias}/timeline-html")
        assert r.status_code == 404
