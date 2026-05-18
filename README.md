# holoctl

> **A living project operating system for AI coding assistants.** One source of truth in `.holoctl/`, compiled to whatever Claude Code, GitHub Copilot, OpenAI Codex, or any AGENTS.md-aware tool (Aider, Zed, Junie, Jules, Factory, goose…) reads. Durable cross-assistant memory, autonomous curator, multi-target compile, MCP server, web dashboard — all version-controlled next to your code.

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
hctl setup-global --target all               # Claude + Copilot
# (Codex picks up the per-project AGENTS.md + .codex/config.toml emitted by `hctl init`.)

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
13. [Per-assistant guide](#per-assistant-guide) — Claude / Copilot / Codex
14. [Coverage and doctor](#coverage-and-doctor)
15. [Privacy & coexistence](#privacy--coexistence)
16. [Troubleshooting](#troubleshooting)
17. [FAQ](#faq)
18. [Migration from projctl / projhub](#migration-from-projctl--projhub)
19. [Roadmap](#roadmap)
20. [Documentation & license](#documentation--license)

---

## Why holoctl

Every AI coding assistant defines its own native primitives — Claude Code skills, Copilot prompts, Codex `.codex/config.toml`, AGENTS.md for everything else. Maintaining the same project context across all of them is **manual, error-prone, and never up-to-date**.

`holoctl` is the **abstraction that's missing from the ecosystem**: you write project context **once** in `.holoctl/`, the compiler materializes the right native files for every tool. Plus a CLI, a Kanban board, a memory layer that survives across sessions, an event journal, an autonomous curator that proposes structural improvements, an MCP server, and a web dashboard — all built around the same source of truth.

**It's "living" because it wakes up between sessions:**

- **Durable memory** at `.holoctl/memory/` — the same notes appear in Claude (as skills), Copilot (as `.github/instructions/`), and Codex (via AGENTS.md) in each one's native shape.
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
│   ├── instructions.md             ← compiled to CLAUDE.md / AGENTS.md / .codex/AGENTS.override.md / .github/copilot-instructions.md
│   │
│   ├── board/                      ← Kanban + tickets
│   │   ├── WORKFLOW.md             ← state machine doc (template-managed)
│   │   ├── index.json              ← auto-rebuilt projection of tickets/*.md
│   │   └── tickets/PRJ-001-*.md    ← each ticket = one Markdown file with frontmatter
│   │
│   ├── agents/                     ← active personas (only `boardmaster` after `hctl init`)
│   │   └── boardmaster.md          ← library (developer / reviewer / architect / researcher / dba / devops / security-auditor / tech-writer / agent-designer) added on demand, or design a new one with `/agent-new`
│   │
│   ├── commands/                   ← /board, /ticket, /spec, /sprint, /close, /decision, /status, /agent-new
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
│   ├── ignore                      ← (optional) gitignore-style for assistant-specific ignore lists
│   │
│   └── activity.jsonl              ← raw activity log (low-level)
│
├── …your code
│
└── (compiled outputs — usually .gitignored)
    ├── AGENTS.md                   ← cross-tool universal (Codex / Aider / Zed / Junie / …)
    ├── CLAUDE.md                   ← Claude Code
    ├── .claude/                    ← Claude Code agents/commands/settings.json
    ├── .github/                    ← Copilot instructions + prompts + memory instructions
    ├── .vscode/mcp.json            ← MCP server config for Copilot-in-VSCode
    └── .codex/                     ← OpenAI Codex: AGENTS.override.md + config.toml (mcp_servers)
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
hctl --version              # 0.17.0+
hctl --help                 # full command list
hctl doctor --global        # checks ~/.claude and ~/.copilot install (will report 'missing' until step 2)
```

---

## Per-machine global setup

`hctl setup-global` plants the **`/holoctl` router** in each AI tool's user-level config, so the slash command works in any folder — even before `hctl init`.

```bash
hctl setup-global --target all              # Claude + Copilot
hctl setup-global --target claude           # only Claude Code
hctl setup-global --target copilot          # only Copilot CLI
hctl setup-global --target all --dry-run    # preview without writing
```

What gets installed:

| Tool        | File                                                | Format                                | Idempotent block |
|-------------|-----------------------------------------------------|---------------------------------------|------------------|
| Claude Code | `~/.claude/commands/holoctl.md` + `~/.claude/skills/holoctl-router/` | Slash command + skill with references | replaces files   |
| Copilot     | `~/.copilot/AGENTS.md`                              | Markdown section appended             | `<!-- holoctl:start … end -->` markers |

Codex and other AGENTS.md-aware assistants (Aider, Zed, Junie, Jules, Factory, goose) pick up the per-project `AGENTS.md` emitted by `hctl compile --target agents` — they have no documented user-level surface for slash routers, so `setup-global` is a no-op for them.

**Detecting drift:**

```bash
hctl doctor --global
```

Output:

```
holoctl: global-check
  ✓ Claude         router up-to-date (~/.claude/commands/holoctl.md)
  ✓ Copilot        holoctl block present (~/.copilot/AGENTS.md)

  All global routers up-to-date.
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
2. Writes `config.json` with inferred project name (= `cwd.name`), prefix (= initials), and the shipped **provider catalog** (Linear / GitHub / Trello / Azure DevOps / Jira / Slack — URL patterns mapped to MCP fetch tools).
3. Seeds `boardmaster.md` (the only mandatory persona — owns ticket lifecycle). All other personas (developer / reviewer / architect / researcher / dba / devops / security-auditor / tech-writer / agent-designer) stay latent in the library until `hctl agent add <name>` or `/agent-new` activates them.
4. Seeds `instructions.md`, `WORKFLOW.md`, ticket `_template.md`, and eight default commands (`/status`, `/ticket`, `/spec`, `/board`, `/sprint`, `/decision`, `/close`, `/agent-new`).
5. Plants Claude lifecycle hooks (`SessionStart` → `hctl boot`, `Stop` → `hctl handoff`, deny-list for derived files) and built-in reactive skills (`holoctl-router`, `holoctl-spec-flow`, `holoctl-provider-mcp`, `holoctl-work-item-router`, `holoctl-persona-suggester`, `holoctl-ticket-discipline`, `holoctl-memory-discipline`, `holoctl-parallel-evaluator`).
6. Writes MCP server config (`.claude/settings.json:mcpServers.holoctl`).
7. Compiles default targets (`agents` + `claude`).

**Flags:**

```bash
hctl init --name "My Project" --prefix "MP"           # explicit
hctl init --targets agents,claude,copilot,codex      # custom target set
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
5. **Suggest personas.** `hctl agent suggest` maps detected stack → personas from the expanded library (developer / reviewer / architect / researcher / dba / devops / security-auditor / tech-writer / agent-designer). Examples: SQL + `migrations/` → `dba`; `.github/workflows/` + `Dockerfile` + Terraform → `devops`; `docs/` with many `.md` → `tech-writer`. When no library entry fits the repo, `/agent-new <name>` invokes `agent-designer` to draft a persona tailored to your stack.
6. **Memory seed.** Creates `.holoctl/memory/topics/project-overview.md` with a 3-5 line paragraph derived from README + package files. This is what `hctl boot` reads in session 2 so the agent "wakes up" knowing what the project is.
7. **Overview & next action.** Runs `hctl overview` (canonical snapshot) and `hctl boot` (teaser). Reacts: proposes creating the first ticket, or surfaces curator suggestions, or points to next p1.

**Total time**: ~30 seconds, with 1-2 questions in the path.

---

## Cross-tool compilation

`hctl compile` reads `.holoctl/` and emits files in each target's native format. Targets:

```bash
hctl compile --target agents              # AGENTS.md (cross-tool universal)
hctl compile --target claude              # CLAUDE.md + .claude/...
hctl compile --target copilot             # .github/copilot-instructions.md + .github/prompts/... + .vscode/mcp.json
hctl compile --target codex               # .codex/AGENTS.override.md + .codex/config.toml (mcp_servers)
hctl compile                              # all targets in config.targets[]
```

**The `agents` target** emits `AGENTS.md` at the repo root — the [agents.md](https://agents.md/) standard adopted by OpenAI Codex, Aider, Zed, JetBrains Junie, Google Jules, Factory, goose, and other agents.md-aware tools. Always include it in your `targets` (the default config does).

**Coverage matrix** — what each compiler emits from each `.holoctl/` source:

| `.holoctl/` source            | claude                            | copilot                                      | codex                          | agents                              |
|-------------------------------|-----------------------------------|----------------------------------------------|--------------------------------|-------------------------------------|
| `instructions.md`             | `CLAUDE.md`                       | `.github/copilot-instructions.md`            | `.codex/AGENTS.override.md`    | `AGENTS.md` (Objective/Architecture)|
| `agents/*.md`                 | `.claude/agents/<n>.md`           | —                                            | —                              | —                                   |
| `commands/*.md`               | `.claude/commands/<n>.md`         | `.github/prompts/<n>.prompt.md`              | —                              | —                                   |
| `context/*.md`                | (via instructions/memory)         | (via instructions)                           | (via instructions override)    | `AGENTS.md` body                    |
| `memory/topics/*.md`          | `.claude/skills/holoctl-mem-*`    | `.github/instructions/holoctl-mem-*`         | —                              | —                                   |
| `hooks/*.json` *(opt)*        | `.claude/settings.json` merge     | `.copilot/config.json` merge                 | —                              | —                                   |
| `rules/*.md` *(opt)*          | `.claude/rules/<n>.md`            | —                                            | —                              | —                                   |
| `skills/<n>/SKILL.md` *(opt)* | `.claude/skills/<n>/...`          | —                                            | —                              | —                                   |
| `output_styles/*.md` *(opt)*  | `.claude/output_styles/`          | —                                            | —                              | —                                   |
| MCP servers (config)          | `.claude/settings.json:mcp`       | `.vscode/mcp.json`                           | `.codex/config.toml:mcp_servers` | —                                 |

> See `hctl coverage` for a live, workspace-specific version of this table.

---

## MCP vs CLI

### Current design: skills and agents prefer MCP, fall back to CLI / paste

Since v0.17, slash commands, agents, and reactive skills **prefer the MCP server when it's running**, falling back to `hctl` CLI (or paste, for external content) when not. Examples:

- Boardmaster calls `mcp__holoctl__board_create({...})` first; CLI `hctl board add '<json>'` is the documented fallback.
- `/spec` invokes the `holoctl-provider-mcp` skill to fetch an external card body via the provider's MCP (Linear / GitHub / Trello / Azure DevOps / Jira / Slack — or a custom internal board registered via `hctl provider add`); paste is the fallback, with `source_*` preserved either way. The MCP server is auto-spawned by Claude (via `.claude/settings.json:mcpServers`), Copilot (via `.vscode/mcp.json`), or Codex (via `.codex/config.toml:[mcp_servers.holoctl]`).
- `/agent-new` calls `mcp__holoctl__agent_create` to materialize a designed persona; manual `.md` editing remains the escape hatch.
- The `/holoctl` router still runs `hctl doctor` / `hctl init` / `hctl boot` over the shell — these don't have MCP equivalents because they bootstrap or terminate the assistant session itself.

The CLI remains the **source of truth** — every MCP tool maps 1:1 to a `hctl` subcommand — but MCP is the preferred path inside the assistant's loop because of finer permission gating, in-process speed after handshake, and structured JSON output that chains naturally.

### The MCP server

`hctl init` writes the MCP config so each assistant can spawn `hctl serve --mcp` on demand. The server exposes **25 tools**:

| Read tools (auto-approved)       | Write tools (`permissions.ask`)   |
|----------------------------------|-----------------------------------|
| `holoctl.board_list`             | `holoctl.board_create`            |
| `holoctl.board_children`         | `holoctl.board_batch`             |
| `holoctl.board_get`              | `holoctl.board_move`              |
| `holoctl.board_show`             | `holoctl.board_set`               |
| `holoctl.memory_list_topics`     | `holoctl.board_ack`               |
| `holoctl.memory_read_topic`      | `holoctl.board_note`              |
| `holoctl.memory_search`          | `holoctl.board_delete`            |
| `holoctl.journal_recent`         | `holoctl.board_batch_move`        |
| `holoctl.agent_list_available`   | `holoctl.board_batch_set`         |
| `holoctl.curate_suggestions`     | `holoctl.board_batch_delete`      |
| `holoctl.config_show`            | `holoctl.memory_add`              |
|                                  | `holoctl.agent_add`               |
|                                  | `holoctl.agent_create`            |
|                                  | `holoctl.curate_silence`          |

`holoctl.config_show` is what the `holoctl-provider-mcp` skill reads to discover the provider catalog at runtime — no hardcoded URL list inside the skill.

### MCP-preferred trade-offs

| Concern           | CLI                                                  | MCP                                                          |
|-------------------|------------------------------------------------------|--------------------------------------------------------------|
| Universality      | Runs in any terminal, any agent, any shell.         | Requires MCP-aware client.                                   |
| Reproducibility   | Human can re-run the exact same command.            | Tool calls are JSON-RPC, less human-friendly to replay.      |
| Speed             | Fork of Python (~80-150ms cold).                    | In-process after handshake (faster after first call).        |
| Permission gating | Coarse — relies on shell allow-lists.               | **Fine-grained** — per-tool, write-tools land in `ask`.      |
| Output            | Rich text formatted for humans.                     | Structured JSON for machines/chains.                         |

The CLI is **always** the fallback. If the MCP server is down (or never started), the assistant uses `hctl` directly and everything still works — including from a plain terminal with no AI tool at all.

---

## Daily workflows

### Spec-Driven Development (`/spec`)

Turn an external card or a multi-paragraph brief into a structured **spec** in `.holoctl/`, then automatically decompose it into parallel-safe child tasks.

```text
/spec https://linear.app/eng/issue/ENG-42
```

What happens:

1. **Provider MCP discovery.** The `holoctl-provider-mcp` skill matches the URL against the configured provider catalog (`hctl provider list`). If the Linear MCP is connected (`.mcp.json`), it fetches the card body directly. If not, it falls back to "paste the body here" — with `source_provider`, `source_ref`, `source_url`, `source_label` preserved either way.
2. **Discuss.** One batched question to refine scope, acceptance criteria, files touched, edge cases. Skips when the source content is already explicit.
3. **Materialize spec.** `mcp__holoctl__board_create({kind: "spec", source_*, acceptance, context, ...})`.
4. **Decompose.** `holoctl-parallel-evaluator` splits the work into disjoint child tasks; boardmaster calls `mcp__holoctl__board_batch({shared: {parent: SPEC_ID, source_*, ...}, tickets: [...]})`. The CLI rejects the batch if any two children touch the same file.
5. **Propose execution.** "Activate `developer` on `PRJ-NNN+1`?"

You can also `/spec` with free-form text (no URL) — same flow without the MCP fetch step.

### External board providers (`hctl provider`)

Manage the catalog that maps URL patterns → MCP fetch tool names. Shipped defaults cover Linear, GitHub, Trello, Azure DevOps, Jira, and Slack.

```bash
hctl provider list                          # show current catalog with status
hctl provider test linear https://linear.app/eng/issue/ENG-42  # dry-run the URL match
hctl provider enable linear                 # auto / always / disabled
hctl provider disable jira

# Add a custom internal board:
hctl provider add acme \
  --mcp-fetch mcp__acme__get_card \
  --url-pattern '^https?://board\.acme\.corp/c/(?P<ref>[A-Z0-9]+)' \
  --label-template '{ref}: {title}'
```

When the catalog and the MCP tool both line up, `/spec` and `holoctl-work-item-router` use the fetch transparently. When the MCP isn't connected, the skills fall back to paste — never silently fake a fetch.

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

Library (v0.17): `developer`, `reviewer`, `architect`, `researcher`, `dba`, `devops`, `security-auditor`, `tech-writer`, `agent-designer`. `hctl agent suggest` matches `paths:` globs against your repo (e.g. `**/*.sql` → `dba`, `**/.github/workflows/**` → `devops`).

When no library entry fits the repo, design a new one tailored to your stack:

```text
/agent-new payments-specialist
```

The slash command delegates to the `agent-designer` persona, which reads the repo (README, package files, top-level dirs), drafts a schema-correct persona body (`name` / `description` / `tools` / `paths` / `model`), saves it as `.holoctl/agents/<name>.draft.md`, and asks for confirmation before materializing via `mcp__holoctl__agent_create`. The reactive `holoctl-persona-suggester` skill also surfaces "want a new persona for this gap?" whenever work touches paths no active persona owns.

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
| `hctl setup-global --target X`       | Install the global router for tool X (Claude / Copilot / all).              |
| `hctl upgrade`                       | Migrate workspace + recompile to installed version.                         |
| `hctl compile --target X`            | Generate AI-tool integration files. Default = `config.targets[]`.           |
| `hctl serve [--mcp]`                 | Web dashboard (4242), or stdio MCP server.                                  |
| `hctl doctor [--global]`             | Health check. First line = router-friendly.                                 |
| `hctl coverage [--only-present] [--target X]` | Matrix of `.holoctl/` source → per-target outputs.                |
| `hctl overview`                      | One-screen workspace snapshot.                                              |
| `hctl boot [--target X]`             | ≤1KB session-zero context. Recorded in journal.                             |
| `hctl handoff [--note "..."]`        | Append session-trail line. Auto-called by Stop hook.                        |
| `hctl board <ls\|add\|move\|set\|batch\|get\|body\|stat\|rebuild-index>` | Tickets.       |
| `hctl agent <list\|suggest\|add\|remove>` | Personas (library + active).                                           |
| `hctl provider <list\|add\|enable\|disable\|test\|remove>` | External-board catalog — URL pattern → MCP fetch tool. |
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
  "holoctlVersion": "0.17.0",
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
  "targets": ["agents", "claude", "copilot", "codex"],
  "server": { "port": 4242, "theme": "dark" },
  "providers": {
    "linear":  { "enabled": "auto", "url_pattern": "...", "mcp_fetch_tool": "mcp__linear__get_issue",   "label_template": "{ref}: {title}" },
    "github":  { "enabled": "auto", "url_pattern": "...", "mcp_fetch_tool": "mcp__github__get_issue",   "label_template": "{org}/{repo}#{ref}: {title}" }
    /* trello, azure_devops, jira, slack shipped too — see `hctl provider list` */
  }
}
```

**Notes:**

- `targets` controls what `hctl compile` emits when called with no `--target`. Adding a target requires `hctl compile --target X` once to materialize.
- `git.checkDirty` defaults to **false** — holoctl reads `.git/HEAD`/`refs`/`config` directly without spawning `git status`. Instant on Windows + corporate AV.
- `board.idPadding: 3` produces `MP-001` (vs 2 → `MP-01`).
- `providers` is populated additively on `load_config` — workspaces from older versions get the shipped defaults automatically. Use `hctl provider add` / `enable` / `disable` instead of hand-editing.
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

Copilot receives `.copilot/config.json` (allow/deny lists). Codex doesn't expose a public per-project hooks API — its lifecycle is handled by the user agent and AGENTS.md content.

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

### GitHub Copilot

After `hctl setup-global --target copilot` and `hctl init`:

- **Global**: `~/.copilot/AGENTS.md` — appended block with `<!-- holoctl:start … end -->` markers.
- **Project**: `.github/copilot-instructions.md`, `.github/prompts/<name>.prompt.md`.
- **Memory**: `.github/instructions/holoctl-memory-*.instructions.md` with `applyTo:` glob.
- **MCP**: `.vscode/mcp.json`.
- **Permissions**: deny-list and allow-list flags via `.copilot/config.json`.

Copilot accumulates AGENTS.md content (doesn't overwrite) — the holoctl block coexists with anything else you have.

### OpenAI Codex

After `hctl init` with `codex` in `config.targets` (or `hctl compile --target codex`):

- **Project AGENTS.md** at the repo root (emitted by the `agents` target — Codex reads this natively per the spec).
- **Codex-specific override**: `.codex/AGENTS.override.md` — compiled from `.holoctl/instructions.md`. Codex merges this on top of the root `AGENTS.md`, so it's the right place for Codex-only guidance without polluting the cross-tool file.
- **MCP**: `.codex/config.toml:[mcp_servers.holoctl]` declares the holoctl stdio server. Codex loads `.codex/config.toml` once you trust the project (`codex trust .` or the prompt on first run).

No `setup-global` step — Codex has no documented user-level surface for slash routers.

### Aider / Zed / Junie / Jules / Factory / goose / others

Any tool that respects `AGENTS.md` reads the file emitted by `hctl compile --target agents`. No tool-specific config needed for these — just keep `agents` in your `config.targets` (it ships there by default).

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
  active targets: agents, claude, copilot, codex

  Source                             | agents     | claude       | copilot       | codex
  ─────────────────────────────────────────────────────────────────────────────────────────────
  instructions.md                    | ✓ AGENTS   | ✓ CLAUDE.md  | ✓ .gh/copi.md | ✓ .cx/AGENTS.override
  agents/*.md                        | —          | ✓ .cl/agents | —             | —
  commands/*.md                      | —          | ✓ .cl/comma  | ✓ .gh/prompts | —
  memory/topics/*.md                 | —          | ✓ .cl/skills | ✓ .gh/instr   | —
  (MCP servers)                      | —          | ✓ settings   | ✓ .vsc/mcp    | ✓ .cx/config.toml
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
- **Compiled outputs** are best `.gitignore`'d (`.claude/`, `.codex/`, `.github/copilot-instructions.md`, `AGENTS.md`, `CLAUDE.md`) — they're regenerated from `.holoctl/`. Some teams prefer to commit them for new contributors who don't have `holoctl` installed yet.

---

## Troubleshooting

### `hctl: command not found`

- **`uv tool` / `pipx`**: should be on PATH automatically. If not, run `uv tool update-shell` or `pipx ensurepath` and reopen the terminal.
- **`pip` install**: if you didn't use a venv, you hit PEP 668 or installed into the wrong Python. Re-do it via the venv method in [Installation](#installation).
- **Workaround**: `python -m holoctl <subcommand>` works regardless of PATH (as long as the venv is active).

### `/holoctl` does nothing

- Run `hctl doctor --global`. Probably you skipped `hctl setup-global`. Run it.
- For Codex/Aider/Zed/other AGENTS.md-aware tools: no global router — they consume the per-project `AGENTS.md` emitted by `hctl compile --target agents`.

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

- **Two-way provider sync** — close the original card on the external board when the holoctl spec reaches `done` (currently the assistant just gets a reminder).
- **Expanded provider catalog defaults** — community-contributed entries for less common boards (ClickUp, Asana, Notion, internal RFC systems).
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
