# Architecture

`holoctl` is a CLI + small web server that turns the directory you `init` in into a structured workspace for AI coding agents. The whole product lives inside `.holoctl/` next to your code; nothing is ever written to `$HOME`.

This document covers the **internal design**. For user-facing usage see [README.md](README.md).

## Two implementations, one product

Historical artifact: holoctl ships **two parallel implementations** of the same CLI:

| | Node | Python |
|---|---|---|
| Entrypoint | `bin/holoctl.js` | `holoctl/__main__.py` |
| CLI framework | `commander` | `typer` |
| Web server | `hono` (`src/server/`) | `fastapi` + `uvicorn` (`holoctl/server/`) |
| Distribution | npm (`holoctl`, alias `hctl`) | PyPI (`holoctl`, alias `hctl`) |
| Tests | `node --test src/**/*.test.js` | `pytest tests/` |

Currently the **PyPI** distribution is the canonical one (`pip install holoctl`); the Node tree is kept in sync but not yet published to npm. Either may be deprecated in a future release — track [#deprecation](https://github.com/FelipeCarillo/holoctl/issues) discussion.

Every change to a `lib/` or CLI surface should be applied to **both** trees, or the diff explicitly noted as Python-only / Node-only.

## Layout

```
.
├── bin/holoctl.js                Node CLI entrypoint
├── src/                          Node implementation
│   ├── cli/
│   │   ├── index.js              registers all subcommands with commander
│   │   └── commands/             init, board, repo, agent, compile, serve, sync, doctor
│   ├── lib/
│   │   ├── config.js             find_project_root, load/save config, marker auto-migrate
│   │   ├── board.js              ticket CRUD, frontmatter <-> index.json sync
│   │   ├── discover.js           auto-scan workspace for project markers
│   │   ├── git.js                git info per subdir
│   │   ├── markdown.js           frontmatter parse/serialize
│   │   ├── filetree.js           dashboard file tree with tech-stack badges
│   │   └── compiler/             one file per AI tool target
│   ├── server/                   Hono web dashboard
│   └── templates/                board WORKFLOW, slash commands, agents, instructions
│
├── holoctl/                      Python implementation (mirror of src/)
│   ├── __main__.py               typer app, registers subcommands
│   ├── cli/                      init_, board, repo, agent, compile_, serve, sync_, doctor, overview
│   ├── lib/                      config, board, discover, git, markdown, filetree, templates, compiler/
│   └── server/                   FastAPI dashboard
│
├── pyproject.toml                Python package metadata
├── package.json                  Node package metadata
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
.holoctl/agents/*.md       ──┐
.holoctl/commands/*.md     ──┼──> compiler/X ──> CLAUDE.md, .claude/commands/*.md, ...
.holoctl/instructions.md   ──┤                  AGENTS.md, .devin/skills/*/SKILL.md, ...
.holoctl/context/*.md      ──┘                  .cursor/rules/*.md, .cursor/commands/*.md
                                                .windsurfrules, .windsurf/workflows/*.md
                                                .github/copilot-instructions.md, .github/prompts/*.md
```

Each compiler module is a pure function from `(project_root, config) → list of (rel_path, content)`. Adding a new target is a single new module + an entry in the dispatch dict. See [CONTRIBUTING.md](CONTRIBUTING.md#adding-a-compile-target).

The output is **always** prefixed with `<!-- Generated by holoctl. Do not edit directly. Source: .holoctl/ -->` so users know the file is regenerated.

### Templates and `sync`

The contents of `.holoctl/board/WORKFLOW.md`, `.holoctl/commands/*.md`, and `.holoctl/board/tickets/_template.md` come from a template module embedded in the lib (`src/templates/index.js`, `holoctl/lib/templates.py`). When you upgrade holoctl, run `holoctl sync` to refresh those template-managed files **without** touching user-owned files (tickets, agent customizations, context docs, instructions.md).

The list of synced files is hardcoded in `src/cli/commands/sync.js` (`SYNC_TARGETS`). Add a new template-managed file there if you introduce one.

## Web dashboard

Single-page-app served from the language's stdlib HTTP server (Hono on Node, FastAPI on Python). All state read live from `.holoctl/`. Real-time board updates use **SSE** (Server-Sent Events), one stream that fans out events from `activity.jsonl` (which `board.js` / `board.py` append-write on every mutation).

Static assets:
- `src/server/static/holoctl.css` + `holoctl-ui.js` (Node)
- `holoctl/server/static/holoctl.css` + `holoctl-ui.js` (Python)

These are mostly mirrors. Keep them in sync.

## What's deliberately NOT here

- **No global registry of projects.** Removed in 0.5.0. Workspace = `.holoctl/` next to your code, period.
- **No global slash command installer.** The old `holoctl setup-global` is gone. Slash commands are per-workspace, generated by `compile`.
- **No npm postinstall hook.** Removed to keep installs side-effect-free.
- **No telemetry, no auto-update check, no network calls** outside what `compile` writes to your filesystem.
- **No daemon.** `holoctl serve` is a foreground process you start when you want the dashboard.

## File responsibility cheat sheet

| Concern | Node | Python |
|---|---|---|
| Find `.holoctl/` upwards from cwd | `src/lib/config.js` `findProjectRoot` | `holoctl/lib/config.py` `find_project_root` |
| Auto-rename `.projctl`/`.projhub` → `.holoctl` | `migrateLegacyMarker` (in config.js) | `_migrate_legacy_marker` (in config.py) |
| Auto-discover subprojects | `src/lib/discover.js` `discoverRepos` | `holoctl/lib/discover.py` `discover_repos` |
| Ticket CRUD + .md ↔ index.json sync | `src/lib/board.js` | `holoctl/lib/board.py` |
| Generate AI-tool files | `src/lib/compiler/*.js` | `holoctl/lib/compiler/*.py` |
| Refresh template-managed files | `src/cli/commands/sync.js` `SYNC_TARGETS` | `holoctl/cli/sync_.py` |
| Web dashboard server | `src/server/index.js` (Hono) | `holoctl/server/app.py` (FastAPI) |
