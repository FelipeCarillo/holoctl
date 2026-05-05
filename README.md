# holoctl

> Project structure for AI coding agents — board, tickets, agents, decisions, dossier — version-controlled in `.holoctl/` next to your code.

<p align="center">
  🇺🇸 <a href="README.md">English</a> |
  🇧🇷 <a href="README.pt-br.md">Português</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/holoctl/"><img src="https://img.shields.io/pypi/v/holoctl?color=blue" alt="PyPI"/></a>
  <a href="https://pypi.org/project/holoctl/"><img src="https://img.shields.io/pypi/dm/holoctl?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://github.com/FelipeCarillo/holoctl/actions/workflows/ci.yml"><img src="https://github.com/FelipeCarillo/holoctl/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="MIT"/></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-≥3.11-brightgreen" alt="Python"/></a>
</p>

Type `/holoctl` in your AI coding assistant and your project gets a Kanban board, named agents, slash commands, decision log, and a live web dashboard — all checked into git as plain Markdown + JSON.

Works in **Claude Code**, **Cursor**, **Windsurf**, **GitHub Copilot**, **Devin**, **Aider**, and any agent that reads `AGENTS.md` / `CLAUDE.md`.

```bash
holoctl init
```

That's it. `holoctl init` creates a single committed directory:

```
your-project/
├── .holoctl/                  ← single source of truth, committed to git
│   ├── config.json
│   ├── board/
│   │   ├── index.json         ← auto-rebuilt from ticket .md files
│   │   └── tickets/
│   │       └── PRJ-001-add-auth.md
│   ├── agents/                ← developer.md, reviewer.md, architect.md, researcher.md
│   ├── commands/              ← /board, /ticket, /sprint, /close, /decision, /status
│   ├── context/
│   │   ├── decisions/         ← ADR-style hard locks
│   │   └── documents/
│   └── activity.jsonl         ← append-only event log
└── …your code
```

Then `holoctl compile` translates that into whatever AI tool you use — `CLAUDE.md`, `AGENTS.md`, `.claude/commands/`, `.cursor/rules/`, `.windsurf/workflows/`, etc. Those outputs are **regenerated on demand**, so most users `.gitignore` them and let each clone run `holoctl compile` itself.

---

## Install

**Requires Python ≥ 3.11.**

```bash
uv tool install holoctl       # recommended — handles PATH automatically
# or
pipx install holoctl
# or
pip install holoctl
```

> **`holoctl: command not found`?** `uv tool` and `pipx` put the CLI on PATH for you. With plain `pip`, add `~/.local/bin` (Linux/Mac) or `~/AppData/Roaming/Python/Scripts` (Windows) to your PATH, or call `python -m holoctl`.

---

## Quick Start

```bash
cd your-project              # any directory with code in it
holoctl init                 # creates .holoctl/ — writes nothing to $HOME
holoctl compile              # generates CLAUDE.md / AGENTS.md / .claude/commands/
holoctl serve                # http://127.0.0.1:4242 — live kanban dashboard
```

Then open Claude Code (or Cursor, or Devin…) inside that directory and type `/holoctl`. The agent picks up the board, the ticket templates, and the agent definitions automatically.

> **No global state.** holoctl writes nothing to `$HOME`, keeps no machine-wide registry of projects. The workspace IS the directory you `init`ed in. Everything else — slash commands, AGENTS.md, the dashboard — is generated per-workspace by `holoctl compile`. Safe to run on shared machines, CI, devcontainers.

---

## Pick your AI tool

`holoctl compile` translates `.holoctl/` into the native format of each tool. Run it once per workspace; re-run after edits to regenerate.

| Tool | Compile target | Generated files |
|---|---|---|
| Claude Code | `--target claude` | `CLAUDE.md`, `.claude/commands/*.md`, `.claude/agents/*.md` |
| Cursor | `--target cursor` | `.cursor/rules/holoctl.md`, `.cursor/commands/*.md` |
| Windsurf | `--target windsurf` | `.windsurfrules`, `.windsurf/workflows/*.md` |
| GitHub Copilot | `--target copilot` | `.github/copilot-instructions.md`, `.github/prompts/*.md` |
| Devin | `--target devin` | `AGENTS.md`, `.devin/skills/*/SKILL.md` |
| Generic (Aider, etc.) | `--target generic` | `AGENTS.md` |

```bash
holoctl compile --target claude
holoctl compile                       # all targets in config.targets[]
```

---

## What you get

### 📋 Kanban board with ticket files

Tickets are Markdown files with frontmatter. The board index (`index.json`) is auto-rebuilt from them, so you can edit either side and they stay in sync. Every ticket can link to one or more **discovered subprojects** (see below).

```bash
holoctl board add '{"title":"Add auth flow","agent":"developer","projects":["backend"]}'
holoctl board add '{"title":"Wire SSE","agent":"developer","projects":["backend","frontend"]}'
holoctl board ls --project backend --status doing
holoctl board move PRJ-001 doing
holoctl board set PRJ-001 priority p0
holoctl board stat
```

```markdown
---
id: PRJ-001
title: Add authentication
agent: developer
projects: backend, shared
status: doing
priority: p1
sprint: sprint-1
---
# Start
…files this will touch, current state…
# Goal — Definition of Done
- [ ] JWT auth implemented
- [ ] Tests passing
# Context
…why this exists, decisions made…
```

### 📁 Auto-discovered multi-project workspace

The directory where you `init` is the workspace. Direct subdirectories with project markers (`.git`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `composer.json`, `Gemfile`, `pubspec.yaml`, `mix.exs`, `build.gradle`, `pom.xml`, `CMakeLists.txt`) are surfaced **automatically** in the dashboard's **Projects** view and as filters on the board — no `repo add` required.

```bash
holoctl repo list                          # see what was discovered
holoctl repo add ./infra --name infra      # optional: register a subdir without markers
holoctl repo info backend                  # git branch, dirty state, remote
```

### 🤖 Named agents with explicit roles

`.holoctl/agents/*.md` define personas: `developer`, `reviewer`, `architect`, `researcher`. Each has identity, scope, guard rails, and a report format. When a ticket is assigned to an agent, the slash commands route to the matching definition. You edit the personas like any other file in the repo.

### 🌐 Live web dashboard

```bash
holoctl serve                  # http://127.0.0.1:4242 (localhost only)
holoctl serve --host 0.0.0.0   # expose on local network
```

| Tab | What's there |
|---|---|
| **Board** | Kanban with real-time SSE updates, filter by project / agent / sprint |
| **Projects** | Auto-discovered subdirs with git branch, dirty state, ticket count |
| **Files** | File tree with tech-stack badges (Git, Node, React, Vue, Python, Go, Rust, Flutter, Docker, Terraform, iOS, Java, PHP) |
| **Agents** | Personas as cards |
| **Commands** | Slash command library |
| **Context** | Decisions log, free-form documents |

### 🔒 No global state, no surprise installs

- `holoctl init` writes nothing to `$HOME`. No `~/.holoctl/`, no machine-wide project registry.
- `holoctl install` doesn't exist. There's no postinstall hook either.
- The `/holoctl` slash command is a **per-workspace artifact** generated by `holoctl compile --target claude`. Want it in another workspace? Run compile there too.
- Safe to run on shared machines, CI runners, and devcontainers without leaking state.

---

## Commands

```
holoctl init               Initialize .holoctl/ in the current workspace
holoctl overview           One-screen workspace snapshot
holoctl board <cmd>        Tickets — add, ls, move, set, stat, get, rebuild-index
holoctl repo <cmd>         Discovered subprojects — list, add (override), info
holoctl compile            Generate AI-tool integration files (CLAUDE.md, etc.)
holoctl serve              Start the web dashboard
holoctl agent <cmd>        Manage agent definitions
holoctl sync               Refresh template-managed files after a holoctl upgrade
holoctl doctor             Health check
```

Run `holoctl <cmd> --help` for any of them.

---

## Configuration

Defaults live in code; only override what you need in `.holoctl/config.json`:

```json
{
  "project": {
    "name": "My Project",
    "prefix": "MP",
    "repos": [
      { "name": "backend",  "path": "./backend",  "description": "Node API" }
    ]
  },
  "board": {
    "statuses": ["backlog", "doing", "review", "done", "cancelled"],
    "priorities": ["p0", "p1", "p2", "p3"],
    "idPadding": 3
  },
  "targets": ["claude", "cursor"],
  "server": { "port": 4242, "theme": "dark" }
}
```

`project.repos` is **optional** — only needed to register subdirs the auto-scan misses or to override their display name. Auto-discovered subdirs already appear without it.

---

## Migrating from `projctl` / `projhub`

Earlier names of this project. holoctl reads `.projctl/` and `.projhub/` directories and auto-renames them to `.holoctl/` on the next save. Tickets that used `scope: X` are read as `projects: [X]` and rewritten on the next `board set` or `rebuild-index`.

---

## Documentation

- [CHANGELOG.md](CHANGELOG.md) — release notes
- [ARCHITECTURE.md](ARCHITECTURE.md) — internal design, dual-stack Node + Python implementation, compile pipeline
- [SECURITY.md](SECURITY.md) — vulnerability reporting + threat model
- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, conventions, how to add a compile target

---

## License

MIT © [Felipe Carillo](https://github.com/FelipeCarillo)
