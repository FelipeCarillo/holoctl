# holoctl

> **A living project operating system for AI coding assistants.** One source of truth in `.holoctl/`, compiled to whatever Claude Code, Cursor, Windsurf, Copilot, Devin, Codex, Aider, Zed, Junie or any AGENTS.md-aware tool reads. Durable cross-assistant memory, autonomous curator, multi-target compile, MCP server, web dashboard — all version-controlled next to your code.

<p align="center">
  🇺🇸 <a href="README.md">English</a> |
  🇧🇷 <a href="docs/README.pt-br.md">Português</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/holoctl/"><img src="https://img.shields.io/pypi/v/holoctl?color=blue" alt="PyPI"/></a>
  <a href="https://pypi.org/project/holoctl/"><img src="https://img.shields.io/pypi/dm/holoctl?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://github.com/FelipeCarillo/holoctl/actions/workflows/ci.yml"><img src="https://github.com/FelipeCarillo/holoctl/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="MIT"/></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-≥3.11-brightgreen" alt="Python"/></a>
</p>

---

## TL;DR — three commands

```bash
# 1. Install (pick one — see "Installation" if `hctl` is not on PATH)
uv tool install holoctl                      # recommended
# or:  pipx install holoctl
# or:  pip install holoctl                   # ⚠️ requires an active venv (see below)

# 2. Plant the global router (once per machine, per assistant)
hctl setup-global --target all               # Claude + Copilot + Devin
# (Cursor/Windsurf are per-project only — no global step needed)

# 3. Initialize a project
cd ~/my-project && hctl init
```

Open Claude Code (or any supported assistant) in `~/my-project` and type `/holoctl`. The agent reads the workspace, runs discovery, suggests specialist personas, populates context, and shows the overview — autonomously.

---

## Table of contents

1. [Why holoctl](#why-holoctl)
2. [Anatomy of `.holoctl/`](#anatomy-of-holoctl)
3. [Installation](#installation) — including the **`pip` venv gotcha**
4. [Per-machine global setup](#per-machine-global-setup)
5. [Per-project initialization](#per-project-initialization)
6. [The `/holoctl` slash command — what it actually does](#the-holoctl-slash-command)
7. [Cross-tool compilation](#cross-tool-compilation)
8. [MCP vs CLI — design choice](#mcp-vs-cli)
9. [Daily workflows](#daily-workflows)
10. [Command reference](#command-reference)
11. [Configuration](#configuration)
12. [Lifecycle hooks](#lifecycle-hooks)
13. [Per-assistant guide](#per-assistant-guide) — Claude / Cursor / Windsurf / Copilot / Devin
14. [Coverage and doctor](#coverage-and-doctor)
15. [Privacy & coexistence](#privacy--coexistence)
16. [Troubleshooting](#troubleshooting)
17. [FAQ](#faq)
18. [Migration from projctl / projhub](#migration-from-projctl--projhub)
19. [Roadmap](#roadmap)
20. [Documentation & license](#documentation--license)

---

## Why holoctl

Every AI coding assistant defines its own native primitives — Claude Code skills, Cursor rules, Windsurf workflows, Copilot prompts, Devin skills. Maintaining the same project context across all of them is **manual, error-prone, and never up-to-date**.

`holoctl` is the **abstraction that's missing from the ecosystem**: you write project context **once** in `.holoctl/`, the compiler materializes the right native files for every tool. Plus a CLI, a Kanban board, a memory layer that survives across sessions, an event journal, an autonomous curator that proposes structural improvements, an MCP server, and a web dashboard — all built around the same source of truth.

**It's "living" because it wakes up between sessions:**

- **Durable memory** at `.holoctl/memory/` — the same notes appear in Claude, Cursor, Windsurf, Copilot, Devin in each one's native shape.
- **Event journal** captures every tool use, edit, and session boundary via hooks plumbed automatically.
- **Autonomous curator** watches the journal and proposes new personas, path-scoped rules, or topic archives as `meta:curate` tickets on the board. Approve a suggestion by moving the ticket to `done` — it auto-executes.
- **Token-economy boot** prints ≤1KB of session-zero context (top pendings, recent decisions, available topics) so the assistant doesn't burn tokens loading the whole `CLAUDE.md`.
- **MCP server** exposes board / memory / journal / curator as standard tools (with per-tool permission gating in Claude Code).

---

## Anatomy of `.holoctl/`

```
your-project/
├── .holoctl/                       ← single source of truth, committed to git
│   ├── config.json                 ← project name, prefix, board statuses, targets
│   ├── instructions.md             ← compiled to CLAUDE.md / AGENTS.md / .windsurfrules / ...
│   │
│   ├── board/                      ← Kanban + tickets
│   │   ├── WORKFLOW.md             ← state machine doc (template-managed)
│   │   ├── index.json              ← auto-rebuilt projection of tickets/*.md
│   │   └── tickets/PRJ-001-*.md    ← each ticket = one Markdown file with frontmatter
│   │
│   ├── agents/                     ← active personas (only `boardmaster` after `hctl init`)
│   │   └── boardmaster.md          ← others (developer/reviewer/architect/researcher) added on demand
│   │
│   ├── commands/                   ← /board, /ticket, /sprint, /close, /decision, /status
│   │
│   ├── context/                    ← project-level prose
│   │   ├── objective.md            ← What / Why / Success criteria
│   │   ├── architecture.md         ← Tech stack / Structure / Patterns / Boundaries
│   │   ├── conventions.md          ← Code style, naming, testing
│   │   ├── decisions/              ← ADR-style hard locks
│   │   └── documents/              ← free-form supporting docs
│   │
│   ├── memory/                     ← durable cross-assistant notes
│   │   ├── MEMORY.md               ← always-on index
│   │   ├── .gitignore              ← excludes `_archived/` by default
│   │   └── topics/                 ← lazy / glob / always_on topics
│   │
│   ├── journal/                    ← daily JSONL of session events
│   │   └── 2026-05-08.jsonl
│   │
│   ├── curator/                    ← curator state + per-ticket metadata
│   │
│   ├── hooks/                      ← (optional) declarative hooks per lifecycle event
│   ├── rules/                      ← (optional) path-scoped rules with `paths:` frontmatter
│   ├── skills/                     ← (optional) custom skills with progressive disclosure
│   ├── output_styles/              ← (optional) Claude-specific output styles
│   ├── ignore                      ← (optional) gitignore-style for .cursorignore/.windsurfignore
│   │
│   └── activity.jsonl              ← raw activity log (low-level)
│
├── …your code
│
└── (compiled outputs — usually .gitignored)
    ├── AGENTS.md                   ← cross-tool universal (20+ assistants)
    ├── CLAUDE.md                   ← Claude Code
    ├── .claude/                    ← Claude Code agents/commands/settings.json
    ├── .cursor/                    ← Cursor rules/commands/mcp.json/hooks.json
    ├── .windsurf/                  ← Windsurf rules/workflows/mcp.json
    ├── .windsurfrules              ← Windsurf legacy
    ├── .github/                    ← Copilot instructions/prompts
    ├── .vscode/mcp.json            ← MCP server config for VS Code
    └── .devin/                     ← Devin skills/agents/hooks/mcp.json
```

> **Optional folders** (`hooks/`, `rules/`, `skills/`, `output_styles/`, `ignore`) are **not created by `hctl init`**. They're opt-in surfaces you create when you need them. Compilers only emit what exists in the source — empty input produces empty output (anti-overengineering).

---

## Installation

**Requires Python ≥ 3.11.**

### Option A — `uv tool` *(recommended)*

```bash
uv tool install holoctl
hctl --version
```

`uv tool` creates an isolated venv automatically and puts `hctl` on your PATH. **Nothing else needed.**

### Option B — `pipx`

```bash
pipx install holoctl
hctl --version
```

Same isolation as `uv tool`. Requires `pipx` (`pip install pipx && pipx ensurepath`).

### Option C — `pip` *(⚠️ requires an active venv)*

> **`pip install holoctl` from a "naked" Python on a modern OS will fail with `error: externally-managed-environment` (PEP 668), or — if you bypass that — install into the system Python and `hctl` may end up in a directory not on your PATH.**

The reliable way is to create a venv **specifically for holoctl** and activate it before running `hctl`:

```bash
# Linux / macOS
python3 -m venv ~/.venvs/holoctl
source ~/.venvs/holoctl/bin/activate
pip install holoctl
hctl --version

# Windows (PowerShell)
python -m venv $HOME\.venvs\holoctl
& $HOME\.venvs\holoctl\Scripts\Activate.ps1
pip install holoctl
hctl --version

# Windows (cmd.exe)
python -m venv %USERPROFILE%\.venvs\holoctl
%USERPROFILE%\.venvs\holoctl\Scripts\activate.bat
pip install holoctl
hctl --version
```

**Caveat with venv-based pip install:** `hctl` only works **while the venv is activated**. To make it always available, add a wrapper:

```bash
# Linux/macOS — add to ~/.bashrc or ~/.zshrc
alias hctl="$HOME/.venvs/holoctl/bin/hctl"
```

```powershell
# Windows — add to $PROFILE
function hctl { & "$HOME\.venvs\holoctl\Scripts\hctl.EXE" $args }
```

This is exactly the kind of friction that `uv tool` and `pipx` avoid. **If you have any choice, use one of those.**

### Optional ML extra

```bash
uv tool install "holoctl[ml]"        # ~250MB — adds ONNX paraphrase detection to the curator
```

### Verifying the install

```bash
hctl --version              # 0.14.0+
hctl --help                 # full command list
hctl doctor --global        # checks ~/.claude, ~/.copilot, ~/.config/devin (will report 'missing' until step 2)
```

---

## Per-machine global setup

`hctl setup-global` plants the **`/holoctl` router** in each AI tool's user-level config, so the slash command works in any folder — even before `hctl init`.

```bash
hctl setup-global --target all              # Claude + Copilot + Devin
hctl setup-global --target claude           # only Claude Code
hctl setup-global --target copilot          # only Copilot CLI
hctl setup-global --target devin            # only Devin CLI
hctl setup-global --target all --dry-run    # preview without writing
```

What gets installed:

| Tool      | File                                                | Format                              | Idempotent block |
|-----------|-----------------------------------------------------|-------------------------------------|------------------|
| Claude Code | `~/.claude/commands/holoctl.md`                  | Skill with full frontmatter         | replaces file    |
| Copilot   | `~/.copilot/AGENTS.md`                              | Markdown section appended           | `<!-- holoctl:start … end -->` markers |
| Devin     | `~/.config/devin/skills/holoctl/SKILL.md`           | Devin skill with frontmatter        | replaces file    |

Cursor and Windsurf have **no official user-level surface** for slash commands/skills — they're covered by per-project `hctl compile`.

**Detecting drift:**

```bash
hctl doctor --global
```

Output:

```
holoctl: global-check
  ✓ Claude         router up-to-date (~/.claude/commands/holoctl.md)
  ✓ Copilot        holoctl block present (~/.copilot/AGENTS.md)
  ✗ Devin          skill stale (drift) — run `hctl setup-global --target devin`

  1 issue(s). Run hctl setup-global --target all to fix.
```

---

## Per-project initialization

Inside a project folder:

```bash
cd ~/my-project
hctl init
```

What `init` does, in order:

1. Creates `.holoctl/` structure (board, agents, commands, context, memory, journal).
2. Writes `config.json` with inferred project name (= `cwd.name`) and prefix (= initials).
3. Seeds `boardmaster.md` (the only mandatory persona — owns ticket lifecycle).
4. Seeds `instructions.md`, `WORKFLOW.md`, ticket `_template.md`, six default commands.
5. Plants Claude lifecycle hooks (`SessionStart` → `hctl boot`, `Stop` → `hctl handoff`, deny-list for derived files).
6. Writes MCP server config (`.claude/settings.json:mcpServers.holoctl`).
7. Compiles default targets (`agents` + `claude`).

**Flags:**

```bash
hctl init --name "My Project" --prefix "MP"           # explicit
hctl init --targets agents,claude,cursor,windsurf     # custom target set
hctl init --bare                                       # skeleton only — skip compile/hooks/MCP
hctl init --skip-compile                               # init but don't compile yet
```

Re-running `hctl init` in an already-initialized workspace is **idempotent** — it re-syncs template-managed files (`commands/*.md`, `WORKFLOW.md`, `_template.md`, `boardmaster.md`) without touching user-owned files (tickets, hand-edited agents, context docs, custom rules/skills/hooks).

If you upgrade `holoctl` after `init`, run:

```bash
hctl upgrade --check     # show CHANGELOG slice
hctl upgrade             # apply migrations + recompile
```

---

## The `/holoctl` slash command

This is the **routing brain**. After steps 2 + 3 above, type `/holoctl` (or invoke the equivalent skill) in any assistant. The agent runs:

```text
hctl doctor
```

The first line of output is router-friendly — one of:

| First line                        | Flow      | What the agent does next                                                            |
|-----------------------------------|-----------|-------------------------------------------------------------------------------------|
| `holoctl: not initialized`        | Flow A    | `hctl init` → discover codebase → suggest personas → seed memory → `hctl overview`  |
| `holoctl: outdated`               | Flow B    | `hctl upgrade --check`, ask for confirmation, then `hctl upgrade` + `hctl boot`     |
| `holoctl: ok`                     | Flow C    | `hctl boot` (≤1KB teaser), react to pending tickets / curator suggestions          |

**Flow A in detail** (the most important one — first time in a project):

1. **Detect.** `hctl doctor` returns `not initialized`.
2. **Init.** `hctl init --name "<inferred>" --prefix "<PRX>"`.
3. **Discover.** Reads in parallel: README, package files (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, …), top-level dirs, lint configs, existing AI configs (read-only — never overwrites).
4. **Configure.**
   - Sub-repos: if multiple sub-projects detected, **one aggregated question** ("Found backend/, frontend/, mobile/. Register all?"), then `hctl repo add` for each approved.
   - Context files: writes `.holoctl/context/{objective,architecture,conventions}.md` and `.holoctl/instructions.md` directly from what was read. No per-file confirmation.
   - Ambiguity escape: if README is generic/missing, **one question** to clarify objective. Otherwise no questions.
5. **Suggest personas.** `hctl agent suggest` (or equivalent inline heuristic) maps detected stack → personas. Example: "Detected Python + FastAPI + pytest — activate `developer` and `reviewer`?" → on yes, runs `hctl agent add developer && hctl agent add reviewer`.
6. **Memory seed.** Creates `.holoctl/memory/topics/project-overview.md` with a 3-5 line paragraph derived from README + package files. This is what `hctl boot` reads in session 2 so the agent "wakes up" knowing what the project is.
7. **Overview & next action.** Runs `hctl overview` (canonical snapshot) and `hctl boot` (teaser). Reacts: proposes creating the first ticket, or surfaces curator suggestions, or points to next p1.

**Total time**: ~30 seconds, with 1-2 questions in the path.

---

## Cross-tool compilation

`hctl compile` reads `.holoctl/` and emits files in each target's native format. Targets:

```bash
hctl compile --target agents              # AGENTS.md (cross-tool universal)
hctl compile --target claude              # CLAUDE.md + .claude/...
hctl compile --target cursor              # .cursor/...
hctl compile --target windsurf            # .windsurf/... + .windsurfrules
hctl compile --target copilot             # .github/copilot-instructions.md + .github/prompts/...
hctl compile --target devin               # .devin/...
hctl compile --target generic             # .agents/<name>/... — fallback for unknown tools
hctl compile                              # all targets in config.targets[]
```

**The `agents` target** emits `AGENTS.md` at the repo root — the [agents.md](https://agents.md/) standard adopted by 20+ tools (Claude Code, Codex, Copilot, Cursor, Devin, Zed, Aider, Junie, Jules, Factory, goose, Windsurf, UiPath, VS Code, …). Always include it in your `targets` (the default config does).

**Coverage matrix** — what each compiler emits from each `.holoctl/` source:

| `.holoctl/` source        | claude                         | cursor                         | windsurf                       | copilot                                     | devin                                  | agents                              |
|---------------------------|--------------------------------|--------------------------------|--------------------------------|---------------------------------------------|----------------------------------------|-------------------------------------|
| `instructions.md`         | `CLAUDE.md`                    | `.cursor/rules/holoctl.md`     | `.windsurfrules`               | `.github/copilot-instructions.md`           | (via `agents` target)                  | `AGENTS.md` (Objective/Architecture)|
| `agents/*.md`             | `.claude/agents/<n>.md`        | —                              | —                              | —                                           | `.devin/agents/<n>/AGENT.md`           | —                                   |
| `commands/*.md`           | `.claude/commands/<n>.md`      | `.cursor/commands/<n>.md`      | `.windsurf/workflows/<n>.md`   | `.github/prompts/<n>.prompt.md`             | `.devin/skills/<n>/SKILL.md`           | —                                   |
| `context/*.md`            | (via instructions/memory)      | (via instructions)             | (via instructions)             | (via instructions)                          | (via instructions)                     | `AGENTS.md` body                    |
| `memory/topics/*.md`      | `.claude/skills/holoctl-mem-*` | `.cursor/rules/holoctl-mem-*`  | `.windsurf/rules/holoctl-mem-*`| `.github/instructions/holoctl-mem-*`        | `.devin/rules/holoctl-mem-*`           | —                                   |
| `hooks/*.json` *(opt)*    | `.claude/settings.json` merge  | `.cursor/hooks.json` merge     | `.windsurf/hooks.json` merge   | `.copilot/config.json` merge                | `.devin/hooks.v1.json` merge           | —                                   |
| `rules/*.md` *(opt)*      | `.claude/rules/<n>.md`         | (Cursor uses native rules)     | (Windsurf uses native rules)   | —                                           | —                                      | —                                   |
| `skills/<n>/SKILL.md` *(opt)* | `.claude/skills/<n>/...`   | —                              | —                              | —                                           | —                                      | —                                   |
| `output_styles/*.md` *(opt)* | `.claude/output_styles/`    | —                              | —                              | —                                           | —                                      | —                                   |
| MCP servers (config)      | `.claude/settings.json:mcp`    | `.cursor/mcp.json`             | `.windsurf/mcp.json`           | `.vscode/mcp.json`                          | `.devin/mcp.json`                      | —                                   |

> See `hctl coverage` for a live, workspace-specific version of this table.

---

## MCP vs CLI

### Current design: agents use the CLI

In holoctl 0.14, **agents and slash commands are instructed to use `hctl` CLI**, not MCP tools. Examples:

- Boardmaster says `hctl board add '<json>'`, not `mcp__holoctl__board_create`.
- The `/holoctl` router runs `hctl doctor`, `hctl init`, `hctl boot`.
- Memory updates: `hctl memory add`, not `holoctl.memory_add`.

### The MCP server still exists and runs in parallel

`hctl init` writes the MCP config so each assistant can spawn `hctl serve --mcp` on demand. The server exposes **14 tools**:

| Read tools (auto-approved)       | Write tools (`permissions.ask`) |
|----------------------------------|----------------------------------|
| `holoctl.board_list`             | `holoctl.board_create`           |
| `holoctl.board_get`              | `holoctl.board_move`             |
| `holoctl.memory_list_topics`     | `holoctl.board_set`              |
| `holoctl.memory_read_topic`      | `holoctl.memory_add`             |
| `holoctl.memory_search`          | `holoctl.agent_add`              |
| `holoctl.journal_recent`         | `holoctl.curate_silence`         |
| `holoctl.agent_list_available`   |                                  |
| `holoctl.curate_suggestions`     |                                  |

### Why CLI-first?

| Concern | CLI                                                       | MCP                                                          |
|---|---|---|
| Universality | Runs in any terminal, any agent, any shell.        | Requires MCP-aware client.                                   |
| Reproducibility | Human can re-run the exact same command.        | Tool calls are JSON-RPC, less human-friendly.                |
| Speed | Fork of Python (~80-150ms cold).                       | In-process after handshake (faster after first call).        |
| Permission gating | Coarse — relies on shell allow-lists.       | **Fine-grained** — per-tool, write-tools land in `ask`.      |
| Output | Rich text formatted for humans.                       | Structured JSON for machines.                                |

**Today, holoctl optimizes for universality.** Agents work the same way whether the MCP server is running or not.

### Roadmap: prefer MCP when available

A future release will update the agent/command templates to **prefer MCP when the server is detected**, with CLI fallback. This requires:

1. Updating `holoctl/templates/agents/*.md` to declare both invocation styles.
2. Adding a probe step in `/holoctl` (Step 1.5: "is `mcp__holoctl__board_list` available?").
3. Updating `holoctl/templates/commands/*.md` to use the chosen invocation.

If you want to try MCP-preferred today, edit `.holoctl/agents/boardmaster.md` (after `hctl agent add`) and replace `hctl board add ...` calls with `mcp__holoctl__board_create` — your local change survives upgrades (only library-managed files are sync'd).

---

## Daily workflows

### Create a ticket

```bash
hctl board add '{
  "title": "Add JWT auth",
  "agent": "developer",
  "priority": "p1",
  "projects": ["backend"],
  "goal": [
    "JWT signing implemented",
    "Unit tests cover happy + invalid token",
    "Lint and build pass"
  ],
  "context": "Sessions are cookie-based today; OAuth landing requires bearer."
}'
```

Or in chat: *"create a p1 ticket for JWT auth, developer persona, with goal: signing, tests, lint"*. The agent (boardmaster) translates and runs the command.

### Parallel-safe batch creation

```bash
hctl board batch '{
  "shared": { "tags": ["par:auth-flow"], "projects": ["backend"] },
  "tickets": [
    { "title":"JWT signing", "agent":"developer", "priority":"p1", "files":["src/auth/jwt.py"], "goal":["sign() emits HS256","tests"] },
    { "title":"Auth middleware", "agent":"developer", "priority":"p1", "files":["src/middleware/auth.py"], "goal":["verify+expiry","tests"] },
    { "title":"Auth integration tests", "agent":"reviewer", "priority":"p1", "files":["tests/test_auth.py"], "goal":["happy/expired/invalid"] }
  ]
}'
```

The CLI **rejects the batch** if any two tickets touch the same file (proves non-overlap before creating anything).

### Move tickets

```bash
hctl board move PRJ-001 doing
hctl board set PRJ-001 priority p0
hctl board ls --status doing --priority p1
```

### Memory

```bash
hctl memory add api-conventions --scope glob -g "src/api/**" \
  -d "API naming, error envelope, pagination"
hctl memory list
hctl memory search "JWT"
hctl memory get api-conventions          # read body
hctl memory archive old-topic            # moves to topics/_archived/
```

Topic scopes:

- `always_on` — always included in the assistant's context (use sparingly).
- `lazy` — referenced in MEMORY.md, agent loads when relevant.
- `glob` — only loaded when the assistant is editing files matching the glob.

### Personas

```bash
hctl agent list                          # active vs library
hctl agent suggest                       # heuristic — what to activate based on codebase
hctl agent suggest --json                # machine-readable for automation
hctl agent add developer                 # materialize from library
hctl agent add custom --from developer   # copy active agent as base
hctl agent remove developer              # deactivate (still in library)
```

### Closing a session

```bash
hctl handoff                             # appends 1 line to memory/topics/session-trail.md
hctl handoff --note "Shipped 0.14"       # plus a custom note
```

If lifecycle hooks are installed (`hctl init` does this for Claude), `Stop` runs `hctl handoff --auto` automatically — you don't need to remember.

### Session boot (cross-session continuity)

```bash
hctl boot                                # ≤1KB teaser
hctl boot --target claude                # records source in journal
hctl boot --plain                        # ASCII (no Rich color codes — used by hooks)
```

Output example:

```text
## My Project — sessão 7
Pendências p0/p1: PRJ-003 Add JWT auth, PRJ-005 Fix N+1 in /tickets
Decisões recentes: 2026-05-04-jwt-vs-sessions, 2026-05-01-monorepo
Topics: api-conventions, decisions, session-trail
Personas ativas: boardmaster, developer, reviewer
⚡ 2 sugestão do curador (PRJ-042, PRJ-043) — `hctl curate show`
```

### Curator

```bash
hctl curate run --auto                   # rate-limited (1/day, 14-day suppression per pattern)
hctl curate show                         # open meta:curate tickets
hctl curate apply PRJ-042                # run the proposed action manually
hctl curate silence <pattern_id>         # 14-day suppression
hctl board move PRJ-042 done             # ← approval auto-executes the action
```

### Web dashboard

```bash
hctl serve                               # http://127.0.0.1:4242
hctl serve --host 0.0.0.0 --port 8000    # opt-in network exposure (warns: no auth)
```

Tabs: **Board** (Kanban / List / Tree views with SSE updates), **Repos**, **Agents**, **Commands**, **Context**.

### MCP server

```bash
hctl serve --mcp                         # stdio MCP server — assistants spawn this on demand
```

Configured automatically by `hctl init` so you don't run it manually. Test it standalone with `--mcp`.

---

## Command reference

| Command                              | What it does                                                                |
|--------------------------------------|------------------------------------------------------------------------------|
| `hctl init`                          | Create or sync `.holoctl/` (idempotent).                                    |
| `hctl setup`                         | Plant `/holoctl` skill in every detected assistant (legacy — see `setup-global`). |
| `hctl setup-global --target X`       | Install the global router for tool X (Claude / Copilot / Devin / all).      |
| `hctl upgrade`                       | Migrate workspace + recompile to installed version.                         |
| `hctl compile --target X`            | Generate AI-tool integration files. Default = `config.targets[]`.           |
| `hctl serve [--mcp]`                 | Web dashboard (4242), or stdio MCP server.                                  |
| `hctl doctor [--global]`             | Health check. First line = router-friendly.                                 |
| `hctl coverage [--only-present] [--target X]` | Matrix of `.holoctl/` source → per-target outputs.                |
| `hctl overview`                      | One-screen workspace snapshot.                                              |
| `hctl boot [--target X]`             | ≤1KB session-zero context. Recorded in journal.                             |
| `hctl handoff [--note "..."]`        | Append session-trail line. Auto-called by Stop hook.                        |
| `hctl board <ls\|add\|move\|set\|batch\|get\|body\|stat\|rebuild-index>` | Tickets.       |
| `hctl agent <list\|suggest\|add\|remove>` | Personas.                                                              |
| `hctl memory <list\|add\|get\|search\|archive\|seed>` | Durable memory.                                          |
| `hctl journal <record\|show\|count\|tail\|import>` | Event journal.                                              |
| `hctl curate <run\|show\|apply\|silence>` | Autonomous curator.                                                    |
| `hctl repo <list\|add\|info>`        | Subprojects (auto-discovered + manual overrides).                           |

Every command supports `--help`.

---

## Configuration

`.holoctl/config.json` — only override what you need:

```json
{
  "holoctlVersion": "0.14.0",
  "project": {
    "name": "My Project",
    "prefix": "MP",
    "repos": [
      { "path": "./backend", "name": "backend", "description": "FastAPI service" }
    ]
  },
  "board": {
    "statuses": ["backlog", "doing", "review", "done", "cancelled"],
    "priorities": ["p0", "p1", "p2", "p3"],
    "idPadding": 3
  },
  "git": { "checkDirty": false },
  "targets": ["agents", "claude", "cursor", "windsurf", "copilot", "devin"],
  "server": { "port": 4242, "theme": "dark" }
}
```

**Notes:**

- `targets` controls what `hctl compile` emits when called with no `--target`. Adding a target requires `hctl compile --target X` once to materialize.
- `git.checkDirty` defaults to **false** — holoctl reads `.git/HEAD`/`refs`/`config` directly without spawning `git status`. Instant on Windows + corporate AV.
- `board.idPadding: 3` produces `MP-001` (vs 2 → `MP-01`).
- Adding a new field to a ticket: just write it in the `.md` frontmatter and run `hctl board rebuild-index`.

---

## Lifecycle hooks

`hctl init` writes `.claude/settings.json` with hooks plumbed by default:

```json
{
  "hooks": {
    "SessionStart": [
      { "type": "command", "command": "hctl journal record session_start --source claude --quiet" },
      { "type": "command", "command": "hctl boot --plain --target claude",
        "description": "Print session-zero teaser before user types" }
    ],
    "PreToolUse": [
      { "type": "command", "matcher": "Edit|Write",
        "command": "hctl journal record write_attempt --stdin --quiet --deny-glob '.holoctl/board/index.json,.holoctl/memory/MEMORY.md,.holoctl/activity.jsonl'",
        "description": "Block direct writes to derived state — force CLI usage" }
    ],
    "PostToolUse": [
      { "type": "command", "command": "hctl journal record tool_use --stdin --quiet" }
    ],
    "Stop": [
      { "type": "command", "command": "hctl journal record stop --quiet" },
      { "type": "command", "command": "hctl handoff --quiet --auto",
        "description": "Persist session-trail on every Stop. --auto skips trivial sessions." }
    ]
  },
  "permissions": {
    "ask": [ "mcp__holoctl__board_create", "mcp__holoctl__memory_add", "..." ],
    "deny": [ "Write(.holoctl/board/index.json)", "Edit(.holoctl/memory/MEMORY.md)", "..." ]
  }
}
```

**The deny list is the enforcement** for the rule "never edit derived state by hand" — even if the agent forgets the instruction, the harness blocks the tool call.

Cursor receives equivalent hooks in `.cursor/hooks.json`. Windsurf, Copilot, Devin: see the matrix above (some don't have a public hooks API — emit best-effort).

---

## Per-assistant guide

### Claude Code

After `hctl setup-global --target claude` and `hctl init`:

- **Slash command**: `/holoctl` (your global router).
- **Project context**: `CLAUDE.md` + `@.holoctl/memory/MEMORY.md` reference (auto).
- **Subagents**: `.claude/agents/<name>.md` — invokable via the `Agent` tool.
- **Hooks**: `.claude/settings.json:hooks` (boot teaser on SessionStart, handoff on Stop, deny-list on PreToolUse).
- **MCP**: `.claude/settings.json:mcpServers.holoctl` runs `hctl serve --mcp`.

```bash
# Verify
hctl doctor                        # workspace health
hctl doctor --global               # router install drift
ls .claude/                        # agents/, commands/, settings.json
```

### Cursor

After `hctl init` (Cursor doesn't have a global step — per-project only):

- **Project rules**: `.cursor/rules/holoctl.md` (compiled from `instructions.md`).
- **Slash commands**: `.cursor/commands/<name>.md`.
- **Hooks**: `.cursor/hooks.json`.
- **MCP**: `.cursor/mcp.json`.

```bash
hctl compile --target cursor       # if not in config.targets
```

### Windsurf

Per-project:

- **Rules (legacy)**: `.windsurfrules`.
- **Workflows**: `.windsurf/workflows/<name>.md`.
- **Memory rules**: `.windsurf/rules/holoctl-memory-*.md`.
- **MCP**: `.windsurf/mcp.json`.

Holoctl coexists with Cascade (Windsurf's built-in memory) — your `.windsurf/rules/` files are **versioned with the repo** while Cascade keeps `~/.codeium/windsurf/memories/` machine-local. The curator can promote a long-lived Cascade memory (≥7 days) into a versioned topic.

### GitHub Copilot

After `hctl setup-global --target copilot` and `hctl init`:

- **Global**: `~/.copilot/AGENTS.md` — appended block with `<!-- holoctl:start … end -->` markers.
- **Project**: `.github/copilot-instructions.md`, `.github/prompts/<name>.prompt.md`.
- **Memory**: `.github/instructions/holoctl-memory-*.instructions.md` with `applyTo:` glob.
- **MCP**: `.vscode/mcp.json`.
- **Permissions**: deny-list and allow-list flags via `.copilot/config.json`.

Copilot accumulates AGENTS.md content (doesn't overwrite) — the holoctl block coexists with anything else you have.

### Devin

After `hctl setup-global --target devin` and `hctl init`:

- **Global skill**: `~/.config/devin/skills/holoctl/SKILL.md`.
- **Project AGENTS.md**: emitted by `hctl compile --target agents` (the universal one).
- **Skills**: `.devin/skills/<name>/SKILL.md`.
- **Subagents**: `.devin/agents/<name>/AGENT.md`.
- **Hooks**: `.devin/hooks.v1.json`.
- **MCP**: `.devin/mcp.json`.

Devin imports skills from `.claude/`, `.cursor/`, `.windsurf/` automatically — so even if you don't compile `--target devin`, basic interop works.

### Codex / Aider / Zed / Junie / Jules / Factory / goose / others

Any tool that respects `AGENTS.md` reads the file emitted by `hctl compile --target agents`. No tool-specific config needed for these — just include `agents` in your `config.targets`.

---

## Coverage and doctor

### `hctl coverage`

Shows the fork between source and target:

```bash
hctl coverage                        # all sources × all targets
hctl coverage --only-present         # only sources that exist in this workspace
hctl coverage --target claude        # only one target column
```

Output (filtered):

```text
hctl coverage (source → per-target outputs)
  workspace: /home/me/my-project
  active targets: agents, claude, cursor

  Source                             | agents     | claude     | cursor
  ────────────────────────────────────────────────────────────────────────
  instructions.md                    | ✓ AGENTS   | ✓ CLAUDE.md | ✓ .cu/rules
  agents/*.md                        | —          | ✓ .cl/agents | —
  commands/*.md                      | —          | ✓ .cl/comma | ✓ .cu/comma
  …
```

### `hctl doctor`

```bash
hctl doctor                # workspace health
hctl doctor --global       # global router install drift
```

First line is **router-friendly** (parsed by `/holoctl`):

- `holoctl: not initialized` → no `.holoctl/` found at or above cwd.
- `holoctl: outdated` → workspace `holoctlVersion` < installed `hctl --version`.
- `holoctl: ok` → workspace at current version.
- `holoctl: global-check` → `--global` mode.

---

## Privacy & coexistence

- **`hctl init` writes nothing to `$HOME`.** Only `hctl setup-global` does — and only the router files in user-scope locations of detected assistants.
- **No machine-wide registry, no daemon, no telemetry, no auto-update check.** Workspace = `.holoctl/` next to your code. That's the entire footprint.
- **`.holoctl/memory/.gitignore`** ships with `_archived/` excluded by default. Privacy-strict workspaces uncomment two lines to make the whole memory tree local-only.
- **Coexists with native auto-memory.** Claude Code's auto-memory is **not** disabled. `holoctl` adds a `@.holoctl/memory/MEMORY.md` reference to `CLAUDE.md` so Claude reads both sources.
- **Compiled outputs** are best `.gitignore`'d (`.claude/`, `.cursor/`, `.windsurf/`, `AGENTS.md`, `CLAUDE.md`) — they're regenerated from `.holoctl/`. Some teams prefer to commit them for new contributors who don't have `holoctl` installed yet.

---

## Troubleshooting

### `hctl: command not found`

- **`uv tool` / `pipx`**: should be on PATH automatically. If not, run `uv tool update-shell` or `pipx ensurepath` and reopen the terminal.
- **`pip` install**: if you didn't use a venv, you hit PEP 668 or installed into the wrong Python. Re-do it via the venv method in [Installation](#installation).
- **Workaround**: `python -m holoctl <subcommand>` works regardless of PATH (as long as the venv is active).

### `/holoctl` does nothing

- Run `hctl doctor --global`. Probably you skipped `hctl setup-global`. Run it.
- For Cursor/Windsurf: those don't have a global router — they only work after `hctl init` in a specific folder.

### `No .holoctl/ found`

- You're not in a project that's been `hctl init`'d. Either run `hctl init` here, or `cd` into a project that has `.holoctl/`.
- `find_project_root` walks up the tree looking for `.holoctl/config.json`. If you're inside a subfolder of a project, it should still find it.

### `hctl init` says "Refusing to downgrade"

- The workspace was created with a newer `hctl`. Either upgrade your `hctl` (`uv tool upgrade holoctl`) or manually edit `.holoctl/config.json:holoctlVersion` (not recommended).

### Compile produces stale outputs / `hctl doctor --global` always says "drift"

- The user-edited their global router by hand → drift detected. Run `hctl setup-global --target X --force` to overwrite, or accept the drift if intentional.

### `Window edition / Powershell` / hctl path issues

- The legacy global router (pre-0.14) had a hardcoded venv path. If you're upgrading from before 0.14: run `hctl setup-global --target claude` to replace it with the PATH-based version.

### MCP server not responding

- `hctl serve --mcp` is stdio-only. The assistant spawns it via the MCP config; check `.claude/settings.json:mcpServers.holoctl.command` resolves to a valid `hctl` (or `python -m holoctl`).
- Set `HOLOCTL_BIN=/abs/path/to/hctl` env var to override the auto-detection.

### Tests fail with `No module named 'httpx'`

- `tests/test_dashboard.py` uses `fastapi.testclient` which requires `httpx`. `httpx` is declared in `pyproject.toml`'s `[dependency-groups].dev` (PEP 735) — picked up automatically by `uv sync`. If you're using plain `pip` (no uv), install it manually: `pip install httpx pytest`. The CI matrix uses `uv sync --frozen` and runs the full test suite without skipping.

---

## FAQ

**Do I have to use the slash command? Can I use `hctl` directly?**

Yes. The CLI is the source of truth — slash commands are conveniences. Everything is doable from a terminal.

**Can I use this without the AI assistant?**

Yes. `hctl board`, `hctl memory`, `hctl serve` work fine standalone. You get a Kanban + memory layer + MCP server even without any AI tool.

**Does this conflict with Claude Code's auto-memory?**

No — they coexist. Claude reads both `CLAUDE.md` (which references `.holoctl/memory/MEMORY.md`) and its native auto-memory. The curator can promote durable patterns from auto-memory into versioned topics.

**Can I share `.holoctl/` across multiple repos in a monorepo?**

Yes — that's the design. `hctl init` at the monorepo root, then `hctl repo add ./backend ./frontend ./mobile`. Tickets can declare `projects: [backend, shared]`.

**How do I add a new compile target (e.g. for a new AI tool)?**

Add a module in `holoctl/lib/compiler/<name>.py` exposing `compile_<name>(project_root, config, dry_run)`, register in `compiler/__init__.py`. See `CONTRIBUTING.md`.

**Where's the data stored?**

Everything in `.holoctl/`, in your repo, version-controlled by you. No cloud, no database, no daemon.

**Can I customize the persona library?**

Yes. The library lives in `holoctl/templates/agents/` (read-only when installed via PyPI). To customize: clone the repo, edit, and `pip install -e .` for local dev. Or override per-project: `hctl agent add custom --from developer` then edit `.holoctl/agents/custom.md`.

**The agent ignores my context files**

Check that `.holoctl/instructions.md` is being compiled (not `.holoctl/context/objective.md` directly). The compile pipeline merges context → instructions → CLAUDE.md/AGENTS.md/etc. Run `hctl coverage --only-present` to see what's flowing where.

---

## Migration from projctl / projhub

Earlier names of this project. holoctl reads `.projctl/` and `.projhub/` directories and **auto-renames them to `.holoctl/`** on the next save. Tickets that used `scope: X` are read as `projects: [X]` and rewritten on the next `board set` or `rebuild-index`.

**No manual migration needed** — open a `projctl`/`projhub` workspace with `hctl` 0.14+ and it's silently upgraded.

If you had `~/.claude/commands/projctl.md` or `projhub.md`: run `hctl setup-global --target claude` to install the new `holoctl.md` and delete the legacy ones manually.

---

## Roadmap

- **MCP-first agent templates** (see [MCP vs CLI](#mcp-vs-cli)) — preferred MCP invocation with CLI fallback.
- **`hctl setup-global` for Cursor/Windsurf** if/when they expose a user-level surface.
- **Curator v2** — structural pattern detection (e.g., "you keep editing the same 3 files together; want a rule?").
- **`.holoctl/skills/` ecosystem** — community-shared skills with progressive disclosure (cross-tool by compile).
- **VS Code extension** — board view + memory navigation in the IDE.
- **Multi-workspace dashboard** — `hctl serve --multi` for monorepos with many subprojects.

---

## Documentation & license

- [CHANGELOG.md](holoctl/CHANGELOG.md) — release notes
- [ARCHITECTURE.md](ARCHITECTURE.md) — internal design, compile pipeline, threat model
- [SECURITY.md](SECURITY.md) — vulnerability reporting + threat model
- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, conventions, how to add a compile target
- [docs/README.pt-br.md](docs/README.pt-br.md) — Portuguese version of this README

MIT © [Felipe Carillo](https://github.com/FelipeCarillo)
