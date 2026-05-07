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

from holoctl.lib.board import Board
from holoctl.server import app as app_module
from holoctl.server.app import (
    _avatar_hue,
    _board_page,
    _format_due,
    _format_relative_date,
    _initials,
    _kanban_html,
    _list_html,
    _ticket_preview,
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
