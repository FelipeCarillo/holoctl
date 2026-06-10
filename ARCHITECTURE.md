# Architecture

`holoctl` is a CLI + small web server that turns the directory you `init` in into a structured workspace for AI coding agents. The whole product lives inside `.holoctl/` next to your code. The only command that writes outside the workspace is the opt-in `hctl setup-global`, which installs the `/holoctl` router into Claude Code's user-level config (`~/.claude/`) — everything else stays in `.holoctl/`. There is **no machine-wide registry of projects**.

This document covers the **internal design**. For user-facing usage see [README.md](README.md).

## One implementation, one product

holoctl is a single Python package distributed via PyPI (`pip install holoctl`, `uv tool install holoctl`, or `pipx install holoctl`). The CLI is built with `typer`; the web dashboard with `fastapi` + `uvicorn`; tests with `pytest`.

> **History**: holoctl started life as a Node CLI (`projctl` on npm). Versions 0.3.0 through 0.5.x shipped a parallel Node mirror under `src/` for compatibility. The Node tree was removed in 0.6.0 — Python is the only implementation going forward. If you need a JS-only entrypoint, an older release tag is available, but it is no longer maintained.

## Layout

```
.
├── holoctl/                      Python package (canonical)
│   ├── __main__.py               typer app, registers subcommands
│   ├── cli/                      init, board, agent, memory, journal, curate, repo,
│   │                             provider, compile, sync, upgrade, serve, doctor,
│   │                             overview, boot, handoff, coverage, setup, setup-global
│   ├── lib/
│   │   ├── config.py             find_project_root, load/save config, marker auto-migrate
│   │   ├── board/                ticket CRUD package: store.py (index I/O, cache, lock),
│   │   │                         create.py, ops.py (mutations), markdown_sync.py,
│   │   │                         validate.py — composed by the Board facade in __init__.py
│   │   ├── ticket.py             typed Ticket schema (TypedDict) shared by board + server
│   │   ├── memory.py             durable cross-assistant memory (MEMORY.md + topics/)
│   │   ├── journal.py            append-safe JSONL event log (curator input)
│   │   ├── curator.py            + curator_rules/   pattern → meta:curate suggestions
│   │   ├── agent_library.py      latent persona library (templates/agents/*.md)
│   │   ├── discover.py           auto-scan workspace for project markers
│   │   ├── git.py                git info per subdir (fast parse + full subprocess)
│   │   ├── markdown.py           frontmatter parse/serialize
│   │   ├── filetree.py           file tree with tech-stack badges (used internally)
│   │   ├── templates.py          template loader + SYNC_TARGETS allow-list
│   │   └── compiler/             one module per AI tool target + *_emit helpers
│   ├── server/                   FastAPI dashboard (app, routes/, views/, templates/, static/)
│   │   └── mcp.py                hand-written JSON-RPC-over-stdio MCP server
│   └── templates/                agents/, commands/, hooks/, skills/ shipped with the package
│
├── tests/                        pytest suite
├── pyproject.toml                package metadata
└── .holoctl/                     dogfood — this repo uses holoctl on itself
```

## Core concepts

### Workspace = directory with `.holoctl/`

`find_project_root` walks up from cwd looking for `.holoctl/config.json`. For backwards compat it also accepts `.projctl/` and `.projhub/` (older names of this product) and **renames them in place** to `.holoctl/` on the next config save.

There is **no machine-wide registry**. The workspace IS the directory you `init`ed in. This is deliberate: removing the global registry was the headline change in 0.5.0 (see [CHANGELOG.md](holoctl/CHANGELOG.md)).

### Subprojects = direct subdirs with project markers

`discover_repos(root)` walks the **direct children** of the workspace (depth=1) and includes every subdir that contains at least one of:

```
.git, package.json, pyproject.toml, Cargo.toml, go.mod,
composer.json, Gemfile, pubspec.yaml, mix.exs,
build.gradle, pom.xml, CMakeLists.txt
```

Skip-list (always excluded): `node_modules`, `.venv`, `venv`, `dist`, `build`, `target`, `__pycache__`, `.holoctl`, `.projctl`, `.projhub`, `.git`, `coverage`, `.next`, `.nuxt`, `.cache`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`.

Discovery runs **live on every command** — no cache, no `refresh` step. Cost is O(direct children) + 1 stat per marker, typically <50ms even on workspaces with 30+ subdirs.

`config.project.repos[]` is an **optional override list** that gets union-merged with auto-discovery, deduplicated by relative path. Use it to (a) register subdirs the scan misses or (b) override the display name of one that was found.

### Tickets

Every ticket is a Markdown file at `.holoctl/board/tickets/<ID>-<slug>.md` with YAML frontmatter:

```yaml
---
id: PRJ-001
title: Add authentication
kind: task                  # task | story | bug | spec | epic | rfc | ...
parent: null                # ID of a containing work item (e.g. a spec), if any
agent: developer            # one of the personas in .holoctl/agents/
projects: backend, shared   # array → which discovered subprojects this touches
files: src/auth/jwt.py      # array → paths this ticket touches
status: doing               # one of config.board.statuses
priority: p1
sprint: sprint-1
created: 2026-05-04T00:00:00Z
updated: 2026-05-04T00:00:00Z
completed: null
depends: null
tags: auth, security
---

# Acceptance — Definition of Done
- [ ] criteria
# Context
…why this ticket exists; current state; files it touches…
# Out of scope
…what NOT to do…
# Notes
…appended by `hctl board note` during work…
```

The `index.json` next to it is a denormalized projection used for fast filtering by the CLI and dashboard. It is **rebuilt** from the .md files by `holoctl board rebuild-index`. The .md is always the source of truth.

**Migration**: tickets with the legacy `scope: <string>` field are read transparently as `projects: [<string>]` and rewritten on the next `board set` or `rebuild-index`.

The `Ticket` shape itself is pinned as a `TypedDict` in `holoctl/lib/ticket.py` — pure typing, zero runtime change; tickets stay plain dicts on the wire (index JSON, MCP responses, Jinja contexts).

### Board state machine & locking

`holoctl/lib/board/` is a package: `store.py` owns index persistence, `create.py` / `ops.py` own mutations, `markdown_sync.py` owns the ticket `.md` side, `validate.py` the pure checks; the `Board` facade in `__init__.py` composes them.

- **Statuses come from config** (`config.board.statuses`) — there is no hardcoded state set. Entering `done` stamps `completed`; leaving `done` clears it.
- **One cross-process lock** — `.holoctl/board/index.json.lock` — must be held across the entire load→mutate→save window, so concurrent CLI + MCP + dashboard writers never lose updates to last-write-wins. Readers don't lock.
- **Reads are cached, torn-read-proof**: `index.json` parses are cached per path keyed on `(mtime_ns, size)` and revalidated by `stat()` on every read; saves go through a temp file + `os.replace`, so a reader sees either the old index or the new one — never a mix.
- **Dual write, `.md` wins**: frontmatter mutations save the index first then patch the `.md`; body edits (`ack` / `note` / `set body`) write the `.md` first then refresh the index. A crash between the two is always recoverable because the `.md` is the source of truth (`board rebuild-index`). The `activity.jsonl` entry is logged only after both writes persist.

Module docstrings in `holoctl/lib/board/store.py` and `ops.py` state these invariants next to the code.

### Compile pipeline

`holoctl compile --target X` is the bridge from `.holoctl/` to whatever the target tool reads at startup.

```
.holoctl/agents/*.md         ──┐                  claude → CLAUDE.md, .claude/{agents,commands,
.holoctl/commands/*.md       ──┤                           skills,rules}/*, .claude/settings.json
.holoctl/instructions.md     ──┼──> compiler/X ──>
.holoctl/context/*.md        ──┤                  agents → minimal AGENTS.md discovery shim
.holoctl/memory/*            ──┤                           + .holoctl/foreign-bootstrap.md
holoctl/templates/           ──┘
```

There are **two** supported targets: `claude` (the deep, native compiler) and `agents` (a minimal AGENTS.md discovery shim that points non-Claude assistants at the `holoctl-foreign-bootstrap` skill). Both are registered in `compiler/__init__.py:_COMPILERS`. The retired `cursor` / `windsurf` / `devin` / `generic` / `copilot` / `codex` targets are filtered out of legacy configs on load (`config._REMOVED_TARGETS`).

Each compiler module is a pure function from `(project_root, config) → list of (rel_path, content)`. holoctl intentionally maintains a native compiler only for Claude Code; every other assistant self-configures from `.holoctl/` via the `holoctl-foreign-bootstrap` skill (shipped in `holoctl/templates/skills/`, emitted to `.claude/skills/` and `.holoctl/foreign-bootstrap.md`). See [CONTRIBUTING.md](CONTRIBUTING.md#adding-support-for-an-assistant).

The `/holoctl` bootstrap slash command lives in `holoctl/templates/commands/holoctl-claude.md` and is loaded at compile time via `compiler.template.load_bootstrap()`.

### Manifest lifecycle

The output files are emitted **clean** — no header comment. Instead, holoctl records what it generated in `.holoctl/.compiled.json` (the compile manifest: each output's POSIX rel-path, content hash, source, and target). One `CompileLedger` runs per target per compile:

1. **Load** the previous manifest.
2. **Decide per output**: absent or owned-unmodified (on-disk hash == recorded hash) → write + record; legacy-headered (pre-manifest `<!-- Generated by holoctl -->` file) → adopt; hand-edited (tracked but hash drifted) → preserve, carrying the old entry forward so `doctor` keeps flagging it; foreign (never tracked) → preserve, never recorded.
3. **Prune orphans**: previously-owned paths not written this run are deleted only while still owned-unmodified; entries belonging to a different target are untouched.
4. **Finalize**: merge this run's entries with the other targets' previous entries and persist (skipped when nothing changed, preserving mtime).

Hashes travel on two channels — `write` hashes logical text, `write_bytes` raw bytes — and a path must stick to one channel for life; switching reads as a hand-edit. See the module docstring of `holoctl/lib/compiler/manifest.py`.

### Templates and `sync`

The contents of `.holoctl/board/WORKFLOW.md`, `.holoctl/commands/*.md`, and `.holoctl/board/tickets/_template.md` come from `holoctl/lib/templates.py`. When you upgrade holoctl, run `holoctl sync` to refresh those template-managed files **without** touching user-owned files (tickets, agent customizations, context docs, instructions.md).

The list of synced files is a single shared constant — `SYNC_TARGETS` in `holoctl/lib/templates.py` — imported by all three call sites (`cli/sync_.py`, `cli/init_.py`, `cli/upgrade_.py`). Add a new template-managed file there once and every path picks it up.

## MCP server

`hctl serve --mcp` runs `holoctl/server/mcp.py`: a hand-rolled JSON-RPC 2.0 server over stdio — deliberately no dependency on the `mcp` package. The client (Claude Code, Copilot, Codex, …) spawns one short-lived process per session and drives `initialize` → `tools/list` → `tools/call` as line-delimited JSON.

- **Imports are function-local**: every assistant call pays a fresh process spawn, so module import stays near-instant; holoctl-lib imports happen inside the tool handlers.
- **Declarative tool registry**: `TOOLS` lists name, description, JSON schema, handler, and a `write` flag; write tools are routed into the client's `permissions.ask` gate at compile time. Results are JSON-stringified text content.
- **Concurrency**: the stdio loop handles one request at a time. Safety against the CLI / dashboard / other MCP processes comes from the board lock taken inside `Board` mutators — the MCP server holds no lock of its own.

## Web dashboard

Single-page-app served from `holoctl/server/app.py` (FastAPI + uvicorn, Jinja2 templates in `server/templates/`, route handlers in `server/routes/`, view builders in `server/views/`). All state read live from `.holoctl/`.

Static assets live in `holoctl/server/static/css/*.css` and `holoctl/server/static/js/*.js` (ES modules).

The server binds to `127.0.0.1` by default. `--host 0.0.0.0` is opt-in and prints a warning, since the dashboard has no auth.

### Dashboard SSE

Real-time board updates use **SSE** (Server-Sent Events) via `GET /api/project/{alias}/events`. The stream polls `index.json`'s `mtime` every 2s (stat-first, file I/O off the event loop) and pushes a compacted `board-update` payload only when it changed; a `: keepalive` comment every 25s stops proxies/browsers reaping idle streams. Connections are capped (32 slots, 503 when full) so abandoned tabs can't starve the event loop. The browser side swaps in board/list fragments rendered by the regular routes — no client-side state store.

## What's deliberately NOT here

- **No global registry of projects.** Removed in 0.5.0. Workspace = `.holoctl/` next to your code, period.
- **No telemetry, no auto-update check, no network calls** outside what `compile` writes to your filesystem.
- **No daemon.** `holoctl serve` is a foreground process you start when you want the dashboard. The MCP server (`hctl serve --mcp`) is a short-lived stdio process each assistant spawns on demand — no PID files.

Per-workspace slash commands are generated by `compile`. The optional `hctl setup-global` additionally installs the `/holoctl` *router* into user-level tool configs so the command works in any folder (even before `hctl init`) — this is the one exception to "everything in `.holoctl/`".

## File responsibility cheat sheet

| Concern | File |
|---|---|
| Find `.holoctl/` upwards from cwd | `holoctl/lib/config.py` `find_project_root` |
| Auto-rename `.projctl`/`.projhub` → `.holoctl` | `_migrate_legacy_marker` (in `config.py`) |
| Auto-discover subprojects | `holoctl/lib/discover.py` `discover_repos` |
| Ticket CRUD + .md ↔ index.json sync | `holoctl/lib/board/` (facade: `Board` in `__init__.py`) |
| Ticket schema (TypedDict) | `holoctl/lib/ticket.py` |
| Generate AI-tool files | `holoctl/lib/compiler/*.py` |
| Compile manifest / ownership ledger | `holoctl/lib/compiler/manifest.py` (`CompileLedger`) |
| MCP stdio server | `holoctl/server/mcp.py` |
| `/holoctl` bootstrap per target | `holoctl/templates/commands/holoctl-*.md` + `compiler/template.py:load_bootstrap` |
| Refresh template-managed files | `holoctl/lib/templates.py` `SYNC_TARGETS` |
| Web dashboard server | `holoctl/server/app.py` |
