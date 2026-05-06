# Architecture

`holoctl` is a CLI + small web server that turns the directory you `init` in into a structured workspace for AI coding agents. The whole product lives inside `.holoctl/` next to your code; nothing is ever written to `$HOME`.

This document covers the **internal design**. For user-facing usage see [README.md](README.md).

## One implementation, one product

holoctl is a single Python package distributed via PyPI (`pip install holoctl`, `uv tool install holoctl`, or `pipx install holoctl`). The CLI is built with `typer`; the web dashboard with `fastapi` + `uvicorn`; tests with `pytest`.

> **History**: holoctl started life as a Node CLI (`projctl` on npm). Versions 0.3.0 through 0.5.x shipped a parallel Node mirror under `src/` for compatibility. The Node tree was removed in 0.6.0 — Python is the only implementation going forward. If you need a JS-only entrypoint, an older release tag is available, but it is no longer maintained.

## Layout

```
.
├── holoctl/                      Python package (canonical)
│   ├── __main__.py               typer app, registers subcommands
│   ├── cli/                      init, board, repo, agent, compile, serve, sync, doctor, overview
│   ├── lib/
│   │   ├── config.py             find_project_root, load/save config, marker auto-migrate
│   │   ├── board.py              ticket CRUD, frontmatter <-> index.json sync
│   │   ├── discover.py           auto-scan workspace for project markers
│   │   ├── git.py                git info per subdir
│   │   ├── markdown.py           frontmatter parse/serialize
│   │   ├── filetree.py           file tree with tech-stack badges (used internally)
│   │   ├── templates.py          init-time templates for agents/commands/context/instructions
│   │   └── compiler/             one file per AI tool target
│   ├── server/                   FastAPI dashboard
│   └── templates/commands/       /holoctl bootstrap commands per tool target
│
├── tests/                        pytest suite
├── pyproject.toml                package metadata
└── .holoctl/                     dogfood — this repo uses holoctl on itself
```

## Core concepts

### Workspace = directory with `.holoctl/`

`find_project_root` walks up from cwd looking for `.holoctl/config.json`. For backwards compat it also accepts `.projctl/` and `.projhub/` (older names of this product) and **renames them in place** to `.holoctl/` on the next config save.

There is **no machine-wide registry**. The workspace IS the directory you `init`ed in. This is deliberate: removing the global registry was the headline change in 0.5.0 (see [CHANGELOG.md](CHANGELOG.md)).

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
agent: developer            # one of the personas in .holoctl/agents/
projects: backend, shared   # array → which discovered subprojects this touches
status: doing               # one of config.board.statuses
priority: p1
sprint: sprint-1
created: 2026-05-04
updated: 2026-05-04
completed: null
depends: null
tags: auth, security
---

# Start
…files this will touch, current state…
# Goal — Definition of Done
- [ ] criteria
# Context
…why…
# Out of scope
…what NOT to do…
# Execution notes
…filled by the agent…
```

The `index.json` next to it is a denormalized projection used for fast filtering by the CLI and dashboard. It is **rebuilt** from the .md files by `holoctl board rebuild-index`. The .md is always the source of truth.

**Migration**: tickets with the legacy `scope: <string>` field are read transparently as `projects: [<string>]` and rewritten on the next `board set` or `rebuild-index`.

### Compile pipeline

`holoctl compile --target X` is the bridge from `.holoctl/` to whatever the target tool reads at startup.

```
.holoctl/agents/*.md         ──┐
.holoctl/commands/*.md       ──┼──> compiler/X ──> CLAUDE.md, .claude/commands/*.md, ...
.holoctl/instructions.md     ──┤                  AGENTS.md, .devin/skills/*/SKILL.md, ...
.holoctl/context/*.md        ──┤                  .cursor/rules/holoctl.md, .cursor/commands/*.md
holoctl/templates/commands/  ──┘                  .windsurfrules, .windsurf/workflows/*.md
                                                  .github/copilot-instructions.md, .github/prompts/*.md
```

Each compiler module is a pure function from `(project_root, config) → list of (rel_path, content)`. Adding a new target is a single new module + an entry in the dispatch dict in `compiler/__init__.py`. See [CONTRIBUTING.md](CONTRIBUTING.md#adding-a-compile-target).

The `/holoctl` bootstrap slash command per target lives in `holoctl/templates/commands/holoctl-<target>.md` and is loaded at compile time via `compiler.template.load_bootstrap()`.

The output is **always** prefixed with `<!-- Generated by holoctl. Do not edit directly. Source: .holoctl/ -->` so users know the file is regenerated.

### Templates and `sync`

The contents of `.holoctl/board/WORKFLOW.md`, `.holoctl/commands/*.md`, and `.holoctl/board/tickets/_template.md` come from `holoctl/lib/templates.py`. When you upgrade holoctl, run `holoctl sync` to refresh those template-managed files **without** touching user-owned files (tickets, agent customizations, context docs, instructions.md).

The list of synced files is hardcoded in `holoctl/cli/sync_.py` (`_SYNC_TARGETS`). Add a new template-managed file there if you introduce one.

## Web dashboard

Single-page-app served from `holoctl/server/app.py` (FastAPI + uvicorn). All state read live from `.holoctl/`. Real-time board updates use **SSE** (Server-Sent Events) — the stream tails `index.json` `mtime` and pushes the new contents on change.

Static assets live in `holoctl/server/static/holoctl.css` + `holoctl-ui.js`.

The server binds to `127.0.0.1` by default. `--host 0.0.0.0` is opt-in and prints a warning, since the dashboard has no auth.

## What's deliberately NOT here

- **No global registry of projects.** Removed in 0.5.0. Workspace = `.holoctl/` next to your code, period.
- **No global slash command installer.** The old `holoctl setup-global` is gone. Slash commands are per-workspace, generated by `compile`.
- **No telemetry, no auto-update check, no network calls** outside what `compile` writes to your filesystem.
- **No daemon.** `holoctl serve` is a foreground process you start when you want the dashboard.

## File responsibility cheat sheet

| Concern | File |
|---|---|
| Find `.holoctl/` upwards from cwd | `holoctl/lib/config.py` `find_project_root` |
| Auto-rename `.projctl`/`.projhub` → `.holoctl` | `_migrate_legacy_marker` (in `config.py`) |
| Auto-discover subprojects | `holoctl/lib/discover.py` `discover_repos` |
| Ticket CRUD + .md ↔ index.json sync | `holoctl/lib/board.py` |
| Generate AI-tool files | `holoctl/lib/compiler/*.py` |
| `/holoctl` bootstrap per target | `holoctl/templates/commands/holoctl-*.md` + `compiler/template.py:load_bootstrap` |
| Refresh template-managed files | `holoctl/cli/sync_.py` `_SYNC_TARGETS` |
| Web dashboard server | `holoctl/server/app.py` |
