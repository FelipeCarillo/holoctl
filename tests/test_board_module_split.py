"""Pins for the board.py → board/ package split (item 5.3).

The split must be invisible to consumers: same import paths, same `Board`
API, same `_INDEX_CACHE` identity — plus the one new seam it introduced,
the injectable curator done-hook on the `Board` constructor.
"""
from __future__ import annotations

from pathlib import Path

from holoctl.lib.board import Board, _INDEX_CACHE


def test_public_import_paths_still_resolve():
    """Every name external code imported from the old module still resolves."""
    # `from holoctl.lib.board import Board` is exercised by the import above;
    # `from .board import Board` (lib-internal, e.g. curator.py) is the same
    # module object.
    import holoctl.lib.board as board_pkg
    from holoctl.lib import curator  # noqa: F401  (does `from .board import Board`)

    assert board_pkg.Board is Board

    # tests/test_board_cache.py and test_board_concurrency.py import the cache
    # *object* — it must be the very dict the store reads/writes, not a copy.
    from holoctl.lib.board.store import _INDEX_CACHE as store_cache

    assert _INDEX_CACHE is store_cache


def test_board_facade_api_surface_unchanged(workspace: Path, workspace_config: dict):
    """The composed Board exposes the full pre-split public API."""
    board = Board(workspace, workspace_config)
    for name in (
        "stat", "get", "ls", "tree", "children", "show", "next_id",
        "add", "batch_add", "move", "set", "delete",
        "batch_move", "batch_set", "batch_delete",
        "ack", "note", "set_body", "rebuild_index",
    ):
        assert callable(getattr(board, name)), f"Board.{name} missing"
    # Smoke: a write through the facade still round-trips through index + .md.
    t = board.add({"title": "Split smoke"})
    assert board.get(t["id"]) is not None
    assert (workspace / ".holoctl" / "board" / t["file"]).exists()


def test_curator_done_hook_is_injectable(workspace: Path, workspace_config: dict):
    """`on_meta_curate_done` replaces the soft-imported curator call."""
    calls: list[tuple[Path, str]] = []

    def fake_hook(root: Path, ticket: dict) -> dict | None:
        calls.append((root, ticket["id"]))
        return {"ok": True, "via": "injected"}

    board = Board(workspace, workspace_config, on_meta_curate_done=fake_hook)
    plain = board.add({"title": "No curate tag"})
    tagged = board.add({"title": "Curate me", "tags": ["meta:curate"]})

    # Non-tagged ticket: hook must NOT fire.
    res = board.move(plain["id"], "done")
    assert "curator_applied" not in res
    assert calls == []

    # Tagged ticket entering done: hook fires once, result is surfaced.
    res = board.move(tagged["id"], "done")
    assert calls == [(workspace, tagged["id"])]
    assert res["curator_applied"] == {"ok": True, "via": "injected"}

    # Re-entering done is a no-op transition: hook must not fire again.
    board.move(tagged["id"], "done")
    assert len(calls) == 1


def test_curator_done_hook_errors_are_contained(workspace: Path, workspace_config: dict):
    """A raising hook is reported in the envelope, never propagated."""

    def broken_hook(root: Path, ticket: dict) -> dict | None:
        raise RuntimeError("boom")

    board = Board(workspace, workspace_config, on_meta_curate_done=broken_hook)
    t = board.add({"title": "Curate me", "tags": ["meta:curate"]})
    res = board.move(t["id"], "done")
    assert res["curator_error"] == "boom"
    # The move itself persisted despite the hook failure.
    ticket = board.get(t["id"])
    assert ticket is not None and ticket["status"] == "done"
