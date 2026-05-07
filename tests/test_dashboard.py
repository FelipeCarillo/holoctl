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
from fastapi.testclient import TestClient

import re

from holoctl.lib.board import Board
from holoctl.server import app as app_module
from holoctl.server.app import (
    _avatar_hue,
    _board_page,
    _format_due,
    _format_iso_datetime,
    _format_relative_date,
    _initials,
    _kanban_html,
    _list_html,
    _read_ticket_activity,
    _ticket_detail_page,
    _ticket_preview,
    _timeline_html,
    app,
)


# ── Helpers / fixtures ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_projects_cache():
    """Reset the 5-second project cache so tests can't see each other."""
    app_module._PROJECTS_CACHE["data"] = None
    app_module._PROJECTS_CACHE["ts"] = 0.0
    yield
    app_module._PROJECTS_CACHE["data"] = None
    app_module._PROJECTS_CACHE["ts"] = 0.0


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
        assert _format_due("2026-05-09") == "May 9"

    def test_iso_datetime(self):
        assert _format_due("2026-12-25T14:00:00Z") == "Dec 25"

    def test_invalid(self):
        assert _format_due("not a date") == ""

    def test_empty(self):
        assert _format_due("") == ""

    def test_none(self):
        assert _format_due(None) == ""


# ── Helpers: _ticket_preview ──────────────────────────────────────────────────


class TestTicketPreview:
    def test_template_only_returns_empty(self, workspace: Path, workspace_config: dict):
        """A freshly-created ticket has only template/placeholder content;
        the preview helper should produce no text rather than leaking
        `(objective criterion)`-style hints."""
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Plain ticket", "agent": "developer"})
        assert _ticket_preview(workspace, ticket) == ""

    def test_substantive_body(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "With body", "agent": "developer"})
        # Replace the body with something real.
        b.set_body(ticket["id"], "## Description\n\nAdd JWT-based auth to the public API. Token refresh + revocation.\n")
        # Re-load to pick up the updated file ref.
        ticket = b.get(ticket["id"])
        out = _ticket_preview(workspace, ticket)
        assert out.startswith("Add JWT-based auth")

    def test_truncates_long_lines(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Long", "agent": "developer"})
        b.set_body(ticket["id"], "## Description\n\n" + "x" * 200 + "\n")
        ticket = b.get(ticket["id"])
        out = _ticket_preview(workspace, ticket, max_chars=80)
        assert len(out) <= 80
        assert out.endswith("…")

    def test_skips_headers(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Headers", "agent": "developer"})
        b.set_body(ticket["id"], "# Goal\n\n## Sub\n\nReal prose line here.\n")
        ticket = b.get(ticket["id"])
        out = _ticket_preview(workspace, ticket)
        assert out == "Real prose line here."

    def test_strips_list_marker(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "List", "agent": "developer"})
        b.set_body(ticket["id"], "## Tasks\n\n- [x] Done item with substance here\n")
        ticket = b.get(ticket["id"])
        out = _ticket_preview(workspace, ticket)
        assert out == "Done item with substance here"

    def test_missing_file(self, workspace: Path):
        # Ticket dict without a matching file → empty, no exception.
        ticket = {"id": "TST-999", "file": "tickets/does-not-exist.md"}
        assert _ticket_preview(workspace, ticket) == ""


# ── _kanban_html: new Phase-1 markup contract ─────────────────────────────────


class TestKanbanHtml:
    def test_emits_priority_dot_with_data_attr(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "priority": "p1", "agent": "developer"})
        tickets = b.ls()
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(tickets, statuses, "test", project_root=workspace)
        assert 'class="kc-prio-dot" data-p="p1"' in html
        # Old stripe / p-badge in the card top row are gone.
        assert "kanban-card-top" not in html  # legacy top row class
        assert "p-badge" not in html  # legacy priority badge inside card

    def test_emits_avatar_initials_with_hue(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer"})
        tickets = b.ls()
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(tickets, statuses, "test", project_root=workspace)
        assert 'class="avatar-initials"' in html
        assert "data-hue=" in html
        # Initials of "developer" are "DE".
        assert ">DE</span>" in html

    def test_emits_inline_add_ticket(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        # Each column gets its own [+ Add ticket] button.
        for s in statuses:
            assert f'data-add-ticket data-status="{s}"' in html

    def test_emits_card_menu(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        assert "data-card-menu" in html

    def test_friendly_empty_state(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        assert "No tickets here" in html
        assert "kanban-empty-glyph" in html

    def test_data_attrs_for_filtering(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "priority": "p1", "agent": "developer",
               "sprint": "s1", "tags": "alpha"})
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        assert 'data-status="backlog"' in html
        assert 'data-p="p1"' in html
        assert 'data-agent="developer"' in html
        assert 'data-sprint="s1"' in html
        assert 'data-tags="alpha"' in html


# ── _board_page: header + LIVE relocation ─────────────────────────────────────


class TestBoardPage:
    def test_header_has_h1_title_and_path(self, workspace: Path, workspace_config: dict):
        project = {"alias": workspace.name, "name": "MyProject", "path": str(workspace)}
        b = Board(workspace, workspace_config)
        html = _board_page(project, b.ls(), workspace_config)
        assert '<h1 class="board-title">MyProject</h1>' in html
        assert f'<div class="board-path">{workspace}</div>' in html

    def test_new_ticket_cta_is_active(self, workspace: Path, workspace_config: dict):
        project = {"alias": workspace.name, "name": "MyProject", "path": str(workspace)}
        b = Board(workspace, workspace_config)
        html = _board_page(project, b.ls(), workspace_config)
        # CTA renders, hooked to data-new-ticket — JS routes it to the
        # first column's inline form.
        assert "data-new-ticket" in html
        # No more aria-disabled placeholder.
        assert 'aria-disabled="true"' not in html

    def test_live_indicator_not_in_board_header(self, workspace: Path, workspace_config: dict):
        # LIVE moved to the topbar (rendered by the route, not _board_page),
        # so the body-level board-header should not contain it.
        project = {"alias": workspace.name, "name": "MyProject", "path": str(workspace)}
        b = Board(workspace, workspace_config)
        html = _board_page(project, b.ls(), workspace_config)
        assert "live-indicator" not in html


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

    def test_static_assets_served(self, client: TestClient):
        css = client.get("/static/holoctl.css")
        js = client.get("/static/holoctl-ui.js")
        assert css.status_code == 200
        assert js.status_code == 200
        # Sanity: new tokens / classes shipped.
        assert "html, body { height: 100vh; overflow: hidden; }" in css.text
        assert ".kc-prio-dot" in css.text
        assert ".kanban-col-add" in css.text


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
        disp, full = _format_relative_date("2026-05-09T12:00:00Z")
        assert disp == "May 9"
        assert full == "2026-05-09T12:00:00Z"

    def test_empty(self):
        disp, full = _format_relative_date("")
        assert disp == "—"
        assert full == ""

    def test_invalid(self):
        disp, full = _format_relative_date("not a date")
        assert disp.startswith("not")
        assert full == "not a date"


# ── _list_html: markup contract ───────────────────────────────────────────────


class TestListHtml:
    def test_renders_one_row_per_ticket(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _list_html(b.ls(), statuses, "test")
        assert html.count('class="ticket-row kanban-card"') == 2

    def test_groups_by_status(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer", "status": "doing"})
        statuses = workspace_config["board"]["statuses"]
        html = _list_html(b.ls(), statuses, "test")
        # One group div per status, in config order.
        for s in statuses:
            assert f'data-bucket="{s}"' in html
        # Backlog group has 1, doing group has 1.
        assert html.find('data-bucket="backlog"') < html.find('data-bucket="doing"')

    def test_emits_select_checkbox_per_row(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _list_html(b.ls(), statuses, "test")
        assert "data-ticket-select" in html
        assert "data-ticket-select-all" in html

    def test_emits_inline_edit_buttons(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "priority": "p1", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _list_html(b.ls(), statuses, "test")
        assert 'data-edit-field="status"' in html
        assert 'data-edit-field="priority"' in html

    def test_emits_bulk_bar(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        statuses = workspace_config["board"]["statuses"]
        html = _list_html(b.ls(), statuses, "test")
        assert 'id="list-bulk-bar"' in html
        assert "data-bulk-move" in html
        assert "data-bulk-archive" in html

    def test_carries_filter_data_attrs(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "priority": "p1", "agent": "developer", "sprint": "s1", "tags": "auth"})
        statuses = workspace_config["board"]["statuses"]
        html = _list_html(b.ls(), statuses, "test")
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
        # Direct edit of the index to inject an off-config status.
        from holoctl.server.app import _list_html as _list
        tickets = b.ls()
        tickets[0] = {**tickets[0], "status": "rogue"}
        statuses = workspace_config["board"]["statuses"]
        html = _list(tickets, statuses, "test")
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


# ── _timeline_html: markup contract ───────────────────────────────────────────


class TestTimelineHtml:
    def test_renders_shell(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer", "sprint": "s1"})
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html(b.ls(), statuses, "test")
        # Container, axis row, body, today line.
        assert 'id="timeline-view"' in html
        assert 'id="timeline"' in html
        assert 'id="tl-axis"' in html
        assert 'class="tl-axis-corner"' in html
        assert 'id="tl-today-line"' in html

    def test_renders_zoom_controls(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html(b.ls(), statuses, "test")
        for z in ("week", "month", "quarter"):
            assert f'data-tl-zoom="{z}"' in html
        # Month is the default active zoom.
        assert 'class="tl-zoom-tab active" data-tl-zoom="month"' in html

    def test_groups_by_sprint_default(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer", "sprint": "s1"})
        b.add({"title": "B", "agent": "developer", "sprint": "s2"})
        b.add({"title": "C", "agent": "developer"})  # no sprint
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html(b.ls(), statuses, "test")
        # Three lane buckets: s1, s2, and the empty-sprint sink.
        assert 'data-bucket="s1"' in html
        assert 'data-bucket="s2"' in html
        assert 'data-bucket="(backlog)"' in html
        # Empty/sink lane sorts last.
        assert html.find('data-bucket="s1"') < html.find('data-bucket="(backlog)"')

    def test_groups_by_agent(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "reviewer"})
        b.add({"title": "C"})  # no agent
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html(b.ls(), statuses, "test", group_by="agent")
        assert 'data-bucket="developer"' in html
        assert 'data-bucket="reviewer"' in html
        assert 'data-bucket="(no agent)"' in html
        # Group selector reflects the chosen axis.
        assert '<option value="agent" selected>Agent</option>' in html

    def test_invalid_group_falls_back_to_sprint(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer", "sprint": "s1"})
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html(b.ls(), statuses, "test", group_by="bogus")
        assert 'data-group="sprint"' in html

    def test_emits_row_per_ticket_with_completed_data_attr(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer", "sprint": "s1"})
        b.move(b.ls()[0]["id"], "done")  # sets completed
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html(b.ls(), statuses, "test")
        assert 'class="tl-row kanban-card"' in html
        assert 'data-completed="' in html
        # Created and status carry through too.
        assert 'data-created="' in html
        assert 'data-status="done"' in html

    def test_row_emits_track_placeholder(self, workspace: Path, workspace_config: dict):
        """Bars are positioned client-side; the server just emits the track div."""
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer", "sprint": "s1"})
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html(b.ls(), statuses, "test")
        assert 'class="tl-row-track" data-track' in html

    def test_empty_state(self, workspace: Path, workspace_config: dict):
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html([], statuses, "test")
        assert 'class="tl-empty"' in html
        assert "No tickets to plot" in html

    def test_carries_filter_data_attrs(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "priority": "p1", "agent": "developer", "sprint": "s1", "tags": "auth"})
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html(b.ls(), statuses, "test")
        # Same data-* contract as kanban / list, so global filter logic
        # works on `.kanban-card` rows.
        assert 'data-status="backlog"' in html
        assert 'data-p="p1"' in html
        assert 'data-agent="developer"' in html
        assert 'data-sprint="s1"' in html
        assert 'data-tags="auth"' in html


# ── Route: ?view=timeline ─────────────────────────────────────────────────────


class TestViewTimeline:
    def test_view_timeline_renders(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=timeline")
        assert r.status_code == 200
        assert 'id="timeline-view"' in r.text
        assert 'id="kanban"' not in r.text
        assert 'id="list-view"' not in r.text
        assert 'data-current-view="timeline"' in r.text

    def test_timeline_tab_is_active(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=timeline")
        assert 'data-view="timeline" role="tab" aria-selected="true"' in r.text


class TestApiTimelineHtmlFragment:
    def test_returns_timeline_fragment(self, client: TestClient, alias: str):
        r = client.get(f"/api/project/{alias}/timeline-html")
        assert r.status_code == 200
        body = r.text.lstrip()
        assert body.startswith('<div class="timeline-view"')
        assert 'data-group="sprint"' in body

    def test_group_param_changes_axis(self, client: TestClient, alias: str):
        r = client.get(f"/api/project/{alias}/timeline-html?group=agent")
        assert r.status_code == 200
        assert 'data-group="agent"' in r.text

    def test_unknown_project_404(self, client: TestClient):
        r = client.get("/api/project/no-such/timeline-html")
        assert r.status_code == 404


# ── Helper: _format_iso_datetime ──────────────────────────────────────────────


class TestFormatIsoDatetime:
    def test_iso_z(self):
        assert _format_iso_datetime("2026-05-07T14:22:00Z") == "2026-05-07 14:22"

    def test_iso_no_tz(self):
        assert _format_iso_datetime("2026-05-07T14:22:00") == "2026-05-07 14:22"

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
        out = _read_ticket_activity(workspace, "TST-001")
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
        out = _read_ticket_activity(workspace, "TST-001")
        assert len(out) == 1

    def test_missing_log(self, tmp_path: Path):
        # Bare directory, no .holoctl/activity.jsonl.
        assert _read_ticket_activity(tmp_path, "TST-001") == []


# ── _ticket_detail_page: markup contract ──────────────────────────────────────


class TestTicketDetailPage:
    def test_renders_toolbar_header_grid(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer", "priority": "p1"})
        html = _ticket_detail_page(ticket, "## Description\n\nReal body.\n", "test", project_root=workspace)
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
        html = _ticket_detail_page(ticket, "", "test", project_root=workspace)
        # Priority dot, ID, status pill, priority pill, h1 title.
        assert 'class="kc-prio-dot" data-p="p1"' in html
        assert f'>{ticket["id"]}</span>' in html
        assert 'class="lr-status" data-status="backlog"' in html
        assert 'class="lr-prio-pill" data-p="p1"' in html
        assert '<h1 class="detail-title">Hello world</h1>' in html

    def test_toolbar_has_back_link_and_actions(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _ticket_detail_page(ticket, "", "test", project_root=workspace)
        assert 'href="/project/test/board"' in html
        assert 'data-edit-field="status"' in html  # Move ▾
        assert 'data-card-menu' in html             # ⋯ menu

    def test_properties_card_has_editable_fields(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({
            "title": "T", "agent": "developer", "priority": "p1",
            "sprint": "s1", "tags": "auth,api",
        })
        html = _ticket_detail_page(ticket, "", "test", project_root=workspace)
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
        html = _ticket_detail_page(ticket, "", "test", project_root=workspace)
        # Pretty `YYYY-MM-DD HH:MM` shows up; full ISO sits in the title attr.
        assert "Created" in html
        assert "Updated" in html
        assert ticket["created"][:10] in html  # YYYY-MM-DD prefix

    def test_linked_card_renders_depends(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        ticket_b = b.add({"title": "B", "agent": "developer", "depends": a["id"]})
        all_t = b.ls()
        html = _ticket_detail_page(ticket_b, "", "test", all_tickets=all_t, project_root=workspace)
        assert "depends on" in html
        assert f'href="/project/test/board/{a["id"]}"' in html

    def test_linked_card_renders_blocks_reverse(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        ticket_b = b.add({"title": "B", "agent": "developer", "depends": a["id"]})
        # Detail page for A should surface "blocks B" via reverse scan.
        a_full = b.get(a["id"])
        all_t = b.ls()
        html = _ticket_detail_page(a_full, "", "test", all_tickets=all_t, project_root=workspace)
        assert "blocks" in html
        assert f'href="/project/test/board/{ticket_b["id"]}"' in html

    def test_linked_card_empty_state(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _ticket_detail_page(ticket, "", "test", all_tickets=b.ls(), project_root=workspace)
        assert "No linked tickets" in html

    def test_activity_card_includes_created(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _ticket_detail_page(ticket, "", "test", project_root=workspace)
        assert 'class="dr-activity"' in html
        assert "Created" in html  # derived event always present

    def test_activity_card_includes_completed_when_done(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        b.move(ticket["id"], "done")
        ticket = b.get(ticket["id"])
        html = _ticket_detail_page(ticket, "", "test", project_root=workspace)
        assert "Marked done" in html
        # Activity is sorted newest-first; scope the position check to the
        # <ol class="dr-activity"> block so the Properties card's "Created"
        # date label doesn't muddy the comparison.
        import re
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
        html = _ticket_detail_page(ticket, "", "test", project_root=workspace)
        assert "Body edited" in html

    def test_renders_markdown_body(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _ticket_detail_page(
            ticket,
            "## Description\n\nThis is the **body**.\n",
            "test", project_root=workspace,
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

    def test_timeline_lane_header_role_button(self, client: TestClient, alias: str):
        client.post(f"/api/project/{alias}/tickets",
                    json={"title": "T", "sprint": "s1", "agent": "developer"})
        r = client.get(f"/project/{alias}/board?view=timeline")
        # Lane headers ditto.
        assert 'class="tl-lane-header"' in r.text
        # Both list group + timeline lane headers carry the role; this
        # snippet must appear in the timeline view too.
        assert r.text.count('role="button"') >= 1

    def test_kc_menu_has_aria_label(self, client: TestClient, alias: str):
        client.post(f"/api/project/{alias}/tickets", json={"title": "T"})
        r = client.get(f"/project/{alias}/board")
        # Icon-only ⋯ buttons need an accessible name.
        assert 'aria-label="Card actions"' in r.text

    def test_focus_visible_styles_present(self, client: TestClient):
        # Tag the rule by its keyword so CSS-format changes don't break us.
        r = client.get("/static/holoctl.css")
        assert r.status_code == 200
        assert ":focus-visible" in r.text
        assert "prefers-reduced-motion" in r.text


class TestCssCleanup:
    def test_legacy_kanban_card_classes_removed(self):
        css = (Path(app_module.__file__).parent / "static" / "holoctl.css").read_text("utf-8")
        # These were Phase-1-era aliases; nothing emits them anymore.
        for sel in (".kanban-card-top", ".kanban-card-id",
                    ".kanban-card-title", ".kanban-card-meta",
                    ".kanban-card-dates"):
            assert sel + " " not in css, f"legacy selector {sel} should be removed"

    def test_legacy_status_badge_removed(self):
        css = (Path(app_module.__file__).parent / "static" / "holoctl.css").read_text("utf-8")
        # `.status-badge` was used by the old detail page; gone since Phase 4.
        assert ".status-badge" not in css

    def test_legacy_p_badge_in_card_removed(self):
        css = (Path(app_module.__file__).parent / "static" / "holoctl.css").read_text("utf-8")
        # `.p-badge` was the kanban card's old inline priority chip.
        # The new card uses `.kc-prio-dot` and the list view uses
        # `.lr-prio-pill`.
        assert ".p-badge " not in css and ".p-badge\n" not in css and ".p-badge{" not in css


# ── Post-merge follow-up: horizontal scroll + repo + deps ─────────────────────


class TestKanbanHorizontalScroll:
    """Regression for the user-reported "horizontal scroll doesn't work".

    The bug: `.kanban` carried `min-width: fit-content`, which expanded the
    container to the sum of its column widths. The flex-item grew past its
    parent (`.content-body`) and `overflow-x: auto` had nothing left to
    scroll — the viewport just clipped the rightmost columns.
    """

    def test_min_width_fit_content_removed(self):
        css = (Path(app_module.__file__).parent / "static" / "holoctl.css").read_text("utf-8")
        # Find the `.kanban {` block and assert the bad declaration is gone.
        m = re.search(r"\.kanban\s*\{[^}]*\}", css)
        assert m, ".kanban block must exist in the served CSS"
        block = m.group(0)
        assert "min-width: fit-content" not in block, (
            "fit-content makes .kanban grow past its parent and silently kills "
            "the horizontal scroll between columns"
        )

    def test_kanban_uses_zero_min_width(self):
        css = (Path(app_module.__file__).parent / "static" / "holoctl.css").read_text("utf-8")
        m = re.search(r"\.kanban\s*\{[^}]*\}", css)
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
    the card top row, in the list view, in the timeline row name, and as
    an editable property in the detail page Properties card.
    """

    def test_kanban_card_renders_repo_chip(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer",
               "projects": ["backend"]})
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        assert 'class="kc-repo"' in html
        # Single-project chip closes immediately after the name; multi adds
        # a trailing `<span class="kc-repo-extra">`.
        assert ">backend</span>" in html

    def test_kanban_card_no_chip_when_empty(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        assert 'class="kc-repo"' not in html

    def test_kanban_card_extra_count_when_multiple(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer",
               "projects": ["backend", "web", "shared"]})
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        # Head project + `+N` indicator for the rest.
        assert ">backend " in html
        assert "+2" in html
        # Tooltip lists all of them so hover gives the full picture.
        assert 'title="repo: backend, web, shared"' in html

    def test_list_view_has_repo_column(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer", "projects": ["backend"]})
        statuses = workspace_config["board"]["statuses"]
        html = _list_html(b.ls(), statuses, "test")
        # New column header + cell.
        assert "lr-cell-repo" in html
        assert ">Repo<" in html
        assert ">backend</span>" in html

    def test_timeline_row_name_includes_repo(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer", "sprint": "s1",
               "projects": ["backend"]})
        statuses = workspace_config["board"]["statuses"]
        html = _timeline_html(b.ls(), statuses, "test")
        # The repo chip lives inside the row's sticky-left .tl-row-name.
        assert "tl-row-name" in html
        assert "kc-repo" in html

    def test_detail_page_properties_card_has_repo_field(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer",
                        "projects": ["backend", "web"]})
        html = _ticket_detail_page(ticket, "", "test", project_root=workspace)
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
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        assert 'class="kc-deps"' in html
        assert first["id"] in html  # the dep ID itself
        assert "↳" in html

    def test_kanban_card_deps_extra_count(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        c = b.add({"title": "C", "agent": "developer"})
        b.add({"title": "B", "agent": "developer",
               "depends": [a["id"], c["id"]]})
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        # First dep visible, +1 indicator for the second.
        assert "+1" in html
        assert f"depends on: {a['id']}, {c['id']}" in html

    def test_kanban_card_no_deps_chip_when_empty(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _kanban_html(b.ls(), statuses, "test", project_root=workspace)
        assert 'class="kc-deps"' not in html

    def test_list_view_has_deps_column(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer", "depends": [a["id"]]})
        statuses = workspace_config["board"]["statuses"]
        html = _list_html(b.ls(), statuses, "test")
        assert "lr-cell-deps" in html
        assert ">Deps<" in html
        assert a["id"] in html

    def test_data_attrs_carry_depends_csv(self, workspace: Path, workspace_config: dict):
        """Filter / search logic reads data-* — `data-depends` must round-trip
        across all three views so future filters can pivot on dependency too."""
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer", "depends": [a["id"]]})
        statuses = workspace_config["board"]["statuses"]
        for renderer in (_kanban_html, _list_html, _timeline_html):
            html = renderer(b.ls(), statuses, "test") if renderer is not _kanban_html \
                else renderer(b.ls(), statuses, "test", project_root=workspace)
            assert f'data-depends="{a["id"]}"' in html, f"{renderer.__name__} missed data-depends"
