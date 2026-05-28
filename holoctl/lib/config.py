from __future__ import annotations
import copy
import json
from pathlib import Path

_DEFAULTS: dict = {
    "version": 1,
    # Last holoctl release that synced this workspace's templates. Stamped at
    # `hctl init` and bumped by `hctl upgrade`. Used by `hctl upgrade --check`
    # to compute the CHANGELOG slice between old and new.
    "holoctlVersion": "0.0.0",
    "project": {
        "name": "MyProject",
        "prefix": "PRJ",
        "description": "",
        "objective": "",
        "repos": [],
    },
    "board": {
        "statuses": ["backlog", "doing", "review", "done", "cancelled"],
        "priorities": ["p0", "p1", "p2", "p3"],
        "idPadding": 3,
        "customFields": {},
    },
    "agents": {
        "defaultModel": "standard",
        "requireTicket": True,
    },
    "commands": {
        # `hctl` is the short alias of `holoctl` (both are registered in
        # pyproject.toml as entry points). Defaulting slash commands to the
        # short form saves ~3 chars per call × dozens of calls per agent
        # session — nontrivial token economy on long workflows.
        "boardCli": "hctl board",
    },
    "git": {
        # When false (default) holoctl never spawns `git status --porcelain`.
        # The `dirty` flag in `repo list`, `repo info`, `overview`, and the
        # dashboard Repos tab is omitted. Flip to true (per workspace) to
        # restore it. Subprocess spawn is the dominant cost on Windows +
        # corporate AV; off-by-default makes the dashboard instant.
        "checkDirty": False,
    },
    # holoctl maintains a deep, native compiler only for Claude Code (`claude`
    # → CLAUDE.md, .claude/agents/, .claude/commands/, skills, settings.json).
    # `agents` emits a minimal AGENTS.md discovery shim (the cross-tool
    # convention) plus `.holoctl/foreign-bootstrap.md`, which points any
    # non-Claude assistant (Copilot, Codex, Cursor, Aider, Zed, …) at the
    # `holoctl-foreign-bootstrap` skill so it can generate its own config dir
    # from `.holoctl/`. Both targets ship by default; `agents` is listed first
    # so a foreign assistant finds the pointer immediately.
    "targets": ["agents", "claude"],
    "server": {
        "port": 4242,
        "theme": "dark",
    },
    # External-board provider catalog. Each entry describes how holoctl
    # recognizes a card URL from that provider and (optionally) which MCP
    # tool name to probe at runtime to fetch the card body. The transport
    # (the MCP itself) is configured outside holoctl — in Claude Code's
    # `.mcp.json` or via a gateway. holoctl just declares what it knows
    # how to use. Defaults are populated lazily by `_apply_provider_defaults`
    # so `_deep_merge` on legacy configs gives them automatically.
    "providers": {},
}


def _default_providers() -> dict:
    """Defaults for the 6 well-known external boards.

    `mcp_fetch_tool` names are best-guesses — when wrong, `enabled: auto`
    causes the skill to fall back silently to paste. User can override per
    workspace by editing `config.providers.<name>.mcp_fetch_tool` or via
    `hctl provider add` / `hctl provider enable`.
    """
    return {
        "linear": {
            "enabled": "auto",
            "url_pattern": r"^https?://linear\.app/[^/]+/issue/(?P<ref>[A-Z]+-\d+)",
            "mcp_fetch_tool": "mcp__linear__get_issue",
            "mcp_search_tool": "mcp__linear__list_issues",
            "label_template": "{ref}: {title}",
        },
        "github": {
            "enabled": "auto",
            "url_pattern": (
                r"^https?://github\.com/(?P<org>[^/]+)/(?P<repo>[^/]+)/issues/(?P<ref>\d+)"
            ),
            "mcp_fetch_tool": "mcp__github__get_issue",
            "mcp_search_tool": "mcp__github__search_issues",
            "label_template": "{org}/{repo}#{ref}: {title}",
        },
        "trello": {
            "enabled": "auto",
            "url_pattern": r"^https?://trello\.com/c/(?P<ref>[A-Za-z0-9]+)",
            "mcp_fetch_tool": "mcp__trello__get_card",
            "label_template": "{ref}: {title}",
        },
        "azure_devops": {
            "enabled": "auto",
            "url_pattern": (
                r"^https?://dev\.azure\.com/(?P<org>[^/]+)/.*/_workitems/edit/(?P<ref>\d+)"
            ),
            "mcp_fetch_tool": "mcp__azure_devops__get_work_item",
            "label_template": "{org} #{ref}: {title}",
        },
        "jira": {
            "enabled": "auto",
            "url_pattern": (
                r"^https?://(?P<org>[^.]+)\.atlassian\.net/browse/(?P<ref>[A-Z]+-\d+)"
            ),
            "mcp_fetch_tool": "mcp__jira__get_issue",
            "label_template": "{ref}: {title}",
        },
        "slack": {
            "enabled": "auto",
            "url_pattern": (
                r"^https?://(?P<org>[^.]+)\.slack\.com/archives/(?P<channel>[A-Z0-9]+)/p(?P<ref>\d+)"
            ),
            "mcp_fetch_tool": "mcp__slack__get_message",
            "label_template": "slack#{channel}: {title}",
        },
    }


def _apply_provider_defaults(config: dict) -> dict:
    """Ensure `config.providers` has the 6 well-known entries — additive only.

    Custom user-added providers (e.g. an internal company board) are
    preserved untouched. Existing entries (even known providers) keep their
    user-set values; we only add missing keys.
    """
    if not isinstance(config.get("providers"), dict):
        config["providers"] = {}
    defaults = _default_providers()
    for name, entry in defaults.items():
        if name not in config["providers"]:
            config["providers"][name] = entry
    return config


# Markers checked when locating a project root. `.holoctl` is canonical;
# `.projctl` and `.projhub` are accepted for backwards compatibility with
# pre-rename installs and are auto-renamed to `.holoctl` on the next save.
_PROJECT_DIR_MARKERS = (".holoctl", ".projctl", ".projhub")


def _existing_marker(root: Path) -> str | None:
    for marker in _PROJECT_DIR_MARKERS:
        if (root / marker / "config.json").exists():
            return marker
    return None


def _migrate_legacy_marker(project_root: Path) -> None:
    canonical = project_root / ".holoctl"
    legacy = _existing_marker(project_root)
    if legacy and legacy != ".holoctl" and not canonical.exists():
        (project_root / legacy).rename(canonical)


def find_project_root(start: Path | None = None) -> Path | None:
    current = Path(start or Path.cwd()).resolve()
    while True:
        if _existing_marker(current):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


# Targets that holoctl previously shipped but were retired. Filtered silently
# from workspace configs on load so legacy workspaces (whose `targets` array
# still lists them) don't blow up at compile time. `copilot`/`codex` joined
# this set in 0.20.0 when holoctl narrowed to a Claude-only compiler — those
# assistants are now served by the `holoctl-foreign-bootstrap` skill instead.
_REMOVED_TARGETS = frozenset({"cursor", "windsurf", "devin", "generic", "copilot", "codex"})


def _filter_removed_targets(config: dict) -> dict:
    targets = config.get("targets") or []
    kept = [t for t in targets if t not in _REMOVED_TARGETS]
    if kept != targets:
        config["targets"] = kept
    return config


def load_config(project_root: Path) -> dict:
    # Migrate legacy `.projctl/` or `.projhub/` BEFORE reading so downstream
    # consumers (board, server) that hardcode `.holoctl/` don't get confused.
    _migrate_legacy_marker(project_root)
    marker = _existing_marker(project_root)
    if marker is None:
        raise FileNotFoundError(f"No .holoctl/config.json found at {project_root}")
    config_path = project_root / marker / "config.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    config = _deep_merge(copy.deepcopy(_DEFAULTS), raw)
    # Apply provider defaults additively — workspaces from v0.16 don't have
    # `providers` set; v0.17 auto-fills the 6 well-known ones on load.
    config = _apply_provider_defaults(config)
    # Filter targets removed in later versions (cursor/windsurf/devin/generic).
    return _filter_removed_targets(config)


def save_config(project_root: Path, config: dict) -> None:
    """Write config to .holoctl/. Auto-migrates legacy `.projctl/` or `.projhub/`."""
    _migrate_legacy_marker(project_root)
    canonical = project_root / ".holoctl"
    canonical.mkdir(parents=True, exist_ok=True)
    (canonical / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )


def get_defaults() -> dict:
    config = copy.deepcopy(_DEFAULTS)
    return _apply_provider_defaults(config)


def _deep_merge(target: dict, source: dict) -> dict:
    for key, val in source.items():
        if (
            isinstance(val, dict)
            and isinstance(target.get(key), dict)
        ):
            _deep_merge(target[key], val)
        else:
            target[key] = val
    return target
