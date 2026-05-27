"""Tests for the curator engine + built-in rules."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


from holoctl.lib.config import get_defaults, save_config
from holoctl.lib.curator import (
    CuratorState,
    _load_ticket_meta,
    apply_curator_action,
    run_curator,
    silence_pattern,
)
from holoctl.lib.curator_rules import library_persona_match, repeated_prompt, unused_topic
from holoctl.lib.journal import Journal
from holoctl.lib.memory import Memory


def _seed(tmp_path: Path) -> None:
    cfg = get_defaults()
    cfg["project"]["name"] = "CurTest"
    cfg["project"]["prefix"] = "CT"
    save_config(tmp_path, cfg)
    (tmp_path / ".holoctl" / "board" / "tickets").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".holoctl" / "board" / "index.json").write_text(
        json.dumps({"meta": {"nextId": 1}, "tickets": []}),
        encoding="utf-8",
    )
    (tmp_path / ".holoctl" / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".holoctl" / "agents" / "boardmaster.md").write_text(
        "---\nname: boardmaster\n---\n", encoding="utf-8",
    )
    Memory(tmp_path).ensure_seed("CurTest")


def test_state_persists_round_trip(tmp_path: Path):
    state = CuratorState.load(tmp_path)
    state.last_run = "2026-05-07T12:00:00Z"
    state.suggestions_today = 1
    state.today = "2026-05-07"
    state.silence("abc123")
    state.save(tmp_path)

    loaded = CuratorState.load(tmp_path)
    assert loaded.last_run == "2026-05-07T12:00:00Z"
    assert loaded.suggestions_today == 1
    assert loaded.is_silenced("abc123", now=datetime(2026, 5, 7, tzinfo=timezone.utc))


def test_silence_expires_after_period(tmp_path: Path):
    state = CuratorState.load(tmp_path)
    state.silence("abc", days=1, now=datetime(2026, 5, 7, tzinfo=timezone.utc))
    # 6 hours later — still silenced
    assert state.is_silenced("abc", now=datetime(2026, 5, 7, 6, tzinfo=timezone.utc))
    # 2 days later — no longer silenced
    assert not state.is_silenced("abc", now=datetime(2026, 5, 9, tzinfo=timezone.utc))


def test_run_curator_no_journal_no_suggestions(tmp_path: Path):
    _seed(tmp_path)
    out = run_curator(tmp_path, bypass_cooldown=True)
    assert out == []


def test_repeated_glob_edits_fires(tmp_path: Path):
    _seed(tmp_path)
    j = Journal(tmp_path)
    for i in range(10):
        j.record("tool_use", source="claude", payload={"tool": "Edit", "file": f"src/api/file{i}.py"})
    out = run_curator(tmp_path, bypass_cooldown=True, auto=False)
    assert any(s.rule == "repeated_glob_edits" for s in out)


def test_curator_creates_meta_curate_ticket_on_auto(tmp_path: Path):
    _seed(tmp_path)
    j = Journal(tmp_path)
    for i in range(10):
        j.record("tool_use", source="claude", payload={"tool": "Edit", "file": f"src/api/file{i}.py"})
    suggestions = run_curator(tmp_path, bypass_cooldown=True, auto=True)
    assert suggestions
    index = json.loads(
        (tmp_path / ".holoctl" / "board" / "index.json").read_text(encoding="utf-8")
    )
    tickets = index["tickets"]
    curate_tickets = [t for t in tickets if "meta:curate" in (t.get("tags") or [])]
    assert len(curate_tickets) == 1
    # Metadata file is written alongside.
    meta = _load_ticket_meta(tmp_path, curate_tickets[0]["id"])
    assert meta is not None
    assert meta["curator_action"] == "rule_extract"


def test_rate_limit_one_suggestion_per_day(tmp_path: Path):
    _seed(tmp_path)
    j = Journal(tmp_path)
    # Two completely distinct patterns: glob edits + unused topic
    for i in range(10):
        j.record("tool_use", source="claude", payload={"tool": "Edit", "file": f"src/api/x{i}.py"})
    # An old topic for unused_topic to fire on (mtime in the past).
    mem = Memory(tmp_path)
    mem.add_topic("ancient", body="x", scope="lazy", description="old")
    import os, time
    old = time.time() - (61 * 24 * 3600)
    os.utime(mem.topics_dir / "ancient.md", (old, old))

    first = run_curator(tmp_path, bypass_cooldown=True, auto=True)
    second = run_curator(tmp_path, bypass_cooldown=True, auto=True)
    # Day-civil rate limit = 1 per workspace per day. First call exhausts the
    # budget; second call returns nothing new.
    assert len(first) == 1
    assert second == []


def test_silenced_pattern_does_not_resurface(tmp_path: Path):
    _seed(tmp_path)
    j = Journal(tmp_path)
    for i in range(10):
        j.record("tool_use", source="claude", payload={"tool": "Edit", "file": f"src/api/x{i}.py"})
    out = run_curator(tmp_path, bypass_cooldown=True, auto=False)
    assert out
    pid = out[0].pattern_id
    silence_pattern(tmp_path, pid)
    # Reset state to clear the rate-limit counter (we're testing silence, not rate).
    state = CuratorState.load(tmp_path)
    state.suggestions_today = 0
    state.save(tmp_path)
    out2 = run_curator(tmp_path, bypass_cooldown=True, auto=False)
    assert all(s.pattern_id != pid for s in out2)


def test_apply_agent_add_materializes_persona(tmp_path: Path):
    _seed(tmp_path)
    ticket_id = "CT-099"
    # Plant the parallel metadata file.
    from holoctl.lib.curator import _save_ticket_meta
    _save_ticket_meta(tmp_path, ticket_id, {
        "curator_action": "agent_add",
        "curator_args": {"name": "developer"},
    })
    result = apply_curator_action(tmp_path, {"id": ticket_id})
    assert result is not None
    assert result["ok"] is True
    assert (tmp_path / ".holoctl" / "agents" / "developer.md").exists()


def test_apply_topic_archive(tmp_path: Path):
    _seed(tmp_path)
    mem = Memory(tmp_path)
    mem.add_topic("temp", body="x", scope="lazy", description="d")
    from holoctl.lib.curator import _save_ticket_meta
    _save_ticket_meta(tmp_path, "CT-088", {
        "curator_action": "topic_archive",
        "curator_args": {"name": "temp"},
    })
    result = apply_curator_action(tmp_path, {"id": "CT-088"})
    assert result["ok"] is True
    assert not (mem.topics_dir / "temp.md").exists()


def test_board_move_to_done_auto_executes(tmp_path: Path):
    """Approving (move-to-done) a meta:curate ticket triggers the action."""
    _seed(tmp_path)
    from holoctl.lib.board import Board
    from holoctl.lib.config import load_config
    board = Board(tmp_path, load_config(tmp_path))
    ticket = board.add({
        "title": "Curate: activate developer",
        "agent": "boardmaster",
        "tags": ["meta:curate"],
        "priority": "p2",
    })
    # Plant the parallel curator metadata.
    from holoctl.lib.curator import _save_ticket_meta
    _save_ticket_meta(tmp_path, ticket["id"], {
        "curator_pattern_id": "abc",
        "curator_action": "agent_add",
        "curator_args": {"name": "developer"},
    })
    result = board.move(ticket["id"], "done")
    assert "curator_applied" in result
    assert result["curator_applied"]["ok"] is True
    assert (tmp_path / ".holoctl" / "agents" / "developer.md").exists()


def test_unused_topic_fires_on_old_topic(tmp_path: Path):
    _seed(tmp_path)
    mem = Memory(tmp_path)
    mem.add_topic("ancient", body="x", scope="lazy", description="d")
    import os, time
    old = time.time() - (61 * 24 * 3600)
    os.utime(mem.topics_dir / "ancient.md", (old, old))
    from holoctl.lib.curator import CuratorContext
    ctx = CuratorContext(
        project_root=tmp_path,
        config=get_defaults(),
        journal=Journal(tmp_path),
        memory=mem,
        state=CuratorState.load(tmp_path),
    )
    out = unused_topic.run(ctx)
    names = {s.args.get("name") for s in out}
    assert "ancient" in names


def test_unused_topic_skips_session_trail(tmp_path: Path):
    _seed(tmp_path)
    mem = Memory(tmp_path)
    mem.add_topic("session-trail", body="x", scope="lazy", description="d")
    import os, time
    old = time.time() - (90 * 24 * 3600)
    os.utime(mem.topics_dir / "session-trail.md", (old, old))
    from holoctl.lib.curator import CuratorContext
    ctx = CuratorContext(
        project_root=tmp_path,
        config=get_defaults(),
        journal=Journal(tmp_path),
        memory=mem,
        state=CuratorState.load(tmp_path),
    )
    out = unused_topic.run(ctx)
    assert all(s.args.get("name") != "session-trail" for s in out)


def test_repeated_prompt_hash_clusters(tmp_path: Path):
    _seed(tmp_path)
    j = Journal(tmp_path)
    for _ in range(4):
        j.record("user_prompt", source="claude", payload={"text": "explain billing domain"})
    from holoctl.lib.curator import CuratorContext
    ctx = CuratorContext(
        project_root=tmp_path,
        config=get_defaults(),
        journal=j,
        memory=Memory(tmp_path),
        state=CuratorState.load(tmp_path),
    )
    out = repeated_prompt.run(ctx)
    assert any(s.rule == "repeated_prompt" for s in out)


def test_library_persona_match_uses_yaml_when_to_suggest(tmp_path: Path):
    _seed(tmp_path)
    j = Journal(tmp_path)
    # 12 Edit/Write tool_use events → matches developer's `tool_use` heuristic
    # (threshold 10, kinds Edit/Write).
    for i in range(12):
        j.record("tool_use", source="claude", payload={"tool": "Edit", "file": f"src/x{i}.py"})
    from holoctl.lib.curator import CuratorContext
    ctx = CuratorContext(
        project_root=tmp_path,
        config=get_defaults(),
        journal=j,
        memory=Memory(tmp_path),
        state=CuratorState.load(tmp_path),
    )
    out = library_persona_match.run(ctx)
    names = {s.args.get("name") for s in out}
    assert "developer" in names


def test_library_persona_match_skips_already_active(tmp_path: Path):
    _seed(tmp_path)
    # Activate developer first — heuristic must NOT propose re-activation.
    (tmp_path / ".holoctl" / "agents" / "developer.md").write_text(
        "---\nname: developer\n---\n", encoding="utf-8",
    )
    j = Journal(tmp_path)
    for i in range(12):
        j.record("tool_use", source="claude", payload={"tool": "Edit", "file": "src/x.py"})
    from holoctl.lib.curator import CuratorContext
    ctx = CuratorContext(
        project_root=tmp_path,
        config=get_defaults(),
        journal=j,
        memory=Memory(tmp_path),
        state=CuratorState.load(tmp_path),
    )
    out = library_persona_match.run(ctx)
    assert all(s.args.get("name") != "developer" for s in out)


def test_cooldown_blocks_subsequent_run(tmp_path: Path):
    _seed(tmp_path)
    j = Journal(tmp_path)
    for i in range(10):
        j.record("tool_use", source="claude", payload={"tool": "Edit", "file": f"src/api/x{i}.py"})
    first = run_curator(tmp_path, bypass_cooldown=True, auto=False)
    assert first
    # Second call WITHOUT bypass — within cooldown, should return [].
    second = run_curator(tmp_path, bypass_cooldown=False, auto=False)
    assert second == []
