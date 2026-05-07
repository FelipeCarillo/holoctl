from __future__ import annotations

from .agent_library import materialize_agent


def get_templates(config: dict) -> dict[str, str]:
    """Return the dict of (rel_path → content) materialized at ``hctl init``.

    Only **essential** scaffolding is included — the board's WORKFLOW, ticket
    template, slash commands, context placeholders, ``instructions.md``, and
    the single always-essential persona ``boardmaster``. Non-essential
    personas (developer, reviewer, architect, researcher, …) live latent in
    the library at ``holoctl/templates/agents/*.md`` and are activated on
    demand via ``hctl agent add <name>``.
    """
    p = config["project"]
    cli = config["commands"]["boardCli"]

    boardmaster_body = materialize_agent("boardmaster", config) or ""

    return {
        ".holoctl/board/WORKFLOW.md": _workflow_md(config),
        ".holoctl/board/tickets/_template.md": _ticket_template_md(config),
        ".holoctl/agents/boardmaster.md": boardmaster_body,
        ".holoctl/commands/status.md": _cmd_status_md(cli, p),
        ".holoctl/commands/ticket.md": _cmd_ticket_md(config),
        ".holoctl/commands/board.md": _cmd_board_md(cli, p),
        ".holoctl/commands/sprint.md": _cmd_sprint_md(cli),
        ".holoctl/commands/decision.md": _cmd_decision_md(),
        ".holoctl/commands/close.md": _cmd_close_md(cli, p),
        ".holoctl/context/objective.md": _context_objective_md(p),
        ".holoctl/context/architecture.md": _context_architecture_md(p),
        ".holoctl/context/conventions.md": _context_conventions_md(p),
        ".holoctl/instructions.md": _instructions_md(config),
    }


def _cmd_status_md(cli: str, p: dict) -> str:
    return f"""---
name: status
description: "Quick project status overview"
arguments: ""
---

# /status — Project status overview

1. Run `{cli} stat` for ticket counts.
2. Run `{cli} ls --status doing` for active work.
3. Run `{cli} ls --status backlog p0` and `{cli} ls --status backlog p1` for next priorities.
4. For tickets with dependencies, use `{cli} get <ID>` to check if deps are done.

## Output format

```
## {p['name']} — Status {{{{date}}}}

**Board:** X backlog · Y doing · Z review · W done
**Doing now:** {{{{list of ID title (agent)}}}}
**Next (p1):** {{{{top 3 backlog p1}}}}
**Blocked:** {{{{tickets with undone deps, or "none"}}}}
```

Maximum 10 lines. No prose.
"""


def _cmd_ticket_md(config: dict) -> str:
    p = config["project"]
    cli = config["commands"]["boardCli"]
    statuses = " | ".join(config["board"]["statuses"])
    priorities = " | ".join(config["board"]["priorities"])
    return f"""---
name: ticket
description: "Create a new ticket on the board"
arguments: "<title>"
---

# /ticket — Create a ticket

The board CLI rejects malformed values. Pass exact strings from the lists below.

## Valid values

- **status**: `{statuses}` (default: `{config["board"]["statuses"][0]}` — omit unless the user explicitly asks)
- **priority**: `{priorities}`
- **agent**: must match a file under `.holoctl/agents/` (run `{cli.split()[0]} agent list` to see them)

## Required fields the user must supply

If any of the below is missing **and** you can't infer it from clear context, ASK the user **once** in a single batched question. Don't guess. Don't pick a default silently.

- **title** (verb + object — derive from the slash command argument)
- **priority** (`p0`-`p3`)
- **agent** (one of the defined agents, single value preferred)
- **Goal — Definition of Done** (at least one `- [ ]` item)

## Optional, fill if you have it

- **projects**: subdir names this ticket touches (run `{cli.split()[0]} repo list` to see them); leave empty if workspace-wide.
- **Start**: state of the codebase before work begins, files that will be touched.
- **Context**: why this exists, non-obvious info.
- **Out of scope**: what NOT to do.

If you don't have content for an optional section, **omit it entirely** — don't write `(...)` placeholders.

## Procedure — single CLI call, no follow-up edit

The CLI accepts body content directly in the JSON. **Do not** create a bare ticket and then edit the .md file — that's two passes and slow. Pass the body in the same `add` call:

```bash
{cli} add '{{
  "title": "Add JWT auth flow",
  "agent": "developer",
  "priority": "p1",
  "projects": ["backend"],
  "files": ["src/auth/jwt.py", "tests/test_jwt.py"],
  "goal": [
    "JWT signing implemented with HS256",
    "Tests cover happy path + invalid token",
    "lint and build pass"
  ],
  "context": "Sessions are cookie-based today; OAuth landing requires bearer tokens.",
  "outOfScope": "Refresh tokens (separate ticket)."
}}'
```

Recognized body fields (all optional except `title`):
- `goal: [str, ...]` — each item becomes a `- [ ]` line under `# Goal — Definition of Done`.
- `start: str` — current state / files that will be touched.
- `context: str` — why this exists, non-obvious info.
- `outOfScope: str` — what NOT to do.
- `executionNotes: str` — kept blank at creation; agents fill it during work.
- `body: str` — full markdown override; if set, all the above are ignored.

Frontmatter scope field (used by parallel batch validation):
- `files: [str, ...]` — explicit list of file paths this ticket will touch. Optional for single `add`; **required** for `{cli} batch` (the validator uses it to prove non-overlap between sibling tickets). Even on single tickets, populating `files` helps downstream agents (developer, reviewer) confirm `Start` matches the codebase.

If you genuinely don't have content for an optional section, **omit the field**. The dashboard already hides empty/placeholder sections.

To edit the body afterward without touching the .md file by hand:
```bash
echo '# Goal — Definition of Done
- [ ] new criterion
- [x] previously done' | {cli} body {p['prefix']}-001
```

Confirm: "Ticket {p['prefix']}-NNN created: {{title}}. Agent: {{name}}. Priority: {{pN}}."
"""


def _cmd_board_md(cli: str, p: dict) -> str:
    return f"""---
name: board
description: "View and manage the project board — kanban view, filters, ticket inspect, move"
arguments: "[<ID> | @agent | #tag | sprint:<name> | p0..p3 | move <ID> <status> | new <title>]"
---

# /board — Project board

## No argument → kanban view

1. Run `{cli} stat` for counts by status.
2. Run `{cli} ls --status backlog`, `--status doing`, `--status review`, `--status done` to group by column.
3. Format as compact table:
   ```
   Backlog (N)          | Doing (N)             | Review (N)       | Done (N)
   {p['prefix']}-019 p1 title   | {p['prefix']}-018 title       |                  | {p['prefix']}-016 title
   {p['prefix']}-020 p1 fix     |                       |                  | (+ N more)
   ```
4. Any ticket in `doing` with `updated` >5 days ago → prefix with `⚠ stalled`.

## /board `<ID>` → inspect ticket

1. Run `{cli} get <ID>` for metadata (status, priority, agent, sprint, deps).
2. Read the ticket file `.holoctl/board/tickets/<ID>-*.md` for full body.
3. Show all sections: Start, Goal (Definition of Done), Context, Out of scope, Execution notes.

## Filters: `@agent` | `#tag` | `sprint:<name>` | `p0`–`p3`

- `@developer` → `{cli} ls --agent developer`
- `#tag` → `{cli} ls --tag tag`
- `sprint:s1` → `{cli} ls --sprint s1`
- `p0`–`p3` → `{cli} ls <pN>`

## /board move `<ID>` `<status>` → move ticket

Run `{cli} move <ID> <status>`.
Confirm: "<ID>: from → to"

## /board new `<title>` → create ticket

Follow the same flow as `/ticket`. See /ticket for full spec.
"""


def _cmd_sprint_md(cli: str) -> str:
    return f"""---
name: sprint
description: "Plan or review a sprint"
arguments: "[plan|review]"
---

# /sprint — Sprint management

## No argument (current sprint)

1. Run `{cli} ls --status doing` and `{cli} ls --status review` for active tickets.
2. For each sprint found, run `{cli} ls --sprint <name>`.
3. Show progress: X/Y completed (Z%).
4. Highlight blocked tickets.

## Plan

1. Run `{cli} ls --status backlog` to list the backlog.
2. Prioritize by: dependencies (done first), priority (p0 > p1 > p2 > p3), capacity.
3. Suggest selection with justification and sprint name.
4. After approval: `{cli} set <ID> sprint <sprint-name>` for each ticket.

## Review

1. Run `{cli} ls --sprint <current>` to list all sprint tickets.
2. Report: completed (with dates), left behind (with reasons), velocity.
3. Suggest adjustments for next sprint.
"""


def _cmd_decision_md() -> str:
    return """---
name: decision
description: "Record a hard-locked decision"
arguments: "<description>"
---

# /decision — Record a decision

1. Read `.holoctl/context/decisions/` to check for duplicates.
2. Create a new file `.holoctl/context/decisions/YYYY-MM-DD-<slug>.md` with:

```markdown
---
date: YYYY-MM-DD
title: One-line summary
status: accepted
---

## Context

Why this decision was needed.

## Decision

What was decided.

## Implications

What changes in practice.
```

3. Confirm: "Decision recorded: {title}."

Decisions are **immutable** by default. To reverse, create a new decision that supersedes the original.
"""


def _cmd_close_md(cli: str, p: dict) -> str:
    return f"""---
name: close
description: "End-of-session persistence — verify all work done, update tickets, record decisions, ready for context clear"
arguments: ""
---

# /close — Session close

Run this command before clearing the context. It ensures nothing is lost.

## Step 1 — Verify actual work via git

Run `git status` and `git diff HEAD` to list files actually changed this session.

If git is unavailable: skip this step and proceed from conversation memory only.

## Step 2 — Cross-reference with open tickets

Run `{cli} ls --status doing` and `{cli} ls --status review`.

For each open ticket, check whether the files listed in its **Start** section appear in the git diff (and that they belong to one of the ticket's `projects`).

## Step 3 — Update tickets

For each ticket where the work is verifiably done (DoD items met OR files changed match the ticket's projects/Start section):

1. Open the ticket file `.holoctl/board/tickets/<ID>-*.md`.
2. Mark completed DoD items: `[ ]` → `[x]`.
3. Append to **Execution notes**: a bullet summarizing what was done and any key decisions made.
4. Move status:
   - All DoD `[x]` → `{cli} move <ID> done`
   - Partially done → keep in `doing`, note what remains

For work done without a ticket (files changed, no ticket covers them):
- If substantial (feature, fix, refactor): `{cli} add '{{"title":"...","status":"done","agent":"..."}}'`
- If trivial (typo, config): skip

## Step 4 — Record decisions

For each non-obvious decision made this session (architecture, trade-off, direction change):

Create `.holoctl/context/decisions/YYYY-MM-DD-<slug>.md`:

```markdown
---
date: YYYY-MM-DD
title: One-line summary
status: accepted
---

## Context
Why this decision was needed.

## Decision
What was decided.

## Implications
What changes in practice.
```

## Step 5 — Final report

```
## {p['name']} — Session close YYYY-MM-DD

Tickets closed:    {p['prefix']}-001, {p['prefix']}-002  (or "none")
Tickets updated:   {p['prefix']}-003 (execution notes)  (or "none")
New tickets:       {p['prefix']}-004 (untracked work)    (or "none")
Decisions:         YYYY-MM-DD-foo.md                  (or "none")
Uncovered files:   (files changed with no ticket)      (or "none")

Ready for /clear.
```

If the session had no substantial work: output "Session trivial — nothing to save. Ready for /clear."
"""


def _context_objective_md(p: dict) -> str:
    desc = p.get("description") or f"(Describe what {p['name']} does in 1-2 sentences)"
    return f"""# Project Objective

## What

{desc}

## Why

(What problem does this solve? Who benefits?)

## Success criteria

- [ ] (Define what "done" looks like)
"""


def _context_architecture_md(p: dict) -> str:
    return """# Architecture

## Tech stack

(List the main technologies, frameworks, and services)

## Structure

```
(High-level directory/module layout)
```

## Key patterns

(Architectural patterns: feature-first, DI, event-driven, etc.)

## Boundaries

(What's in scope vs out of scope for this codebase)
"""


def _context_conventions_md(p: dict) -> str:
    return """# Coding Conventions

## Naming

- Files: (kebab-case, PascalCase, etc.)
- Functions: (camelCase, snake_case, etc.)
- Components: (PascalCase, etc.)

## Style

- Indentation: (2 spaces, 4 spaces, tabs)
- Quotes: (single, double)
- Semicolons: (yes, no)

## Imports

- Order: (stdlib, external, internal, relative)
- Aliases: (if any, e.g. @/ for src/)

## Comments

- Default to no comments. Only add when the WHY is non-obvious.

## Testing

- Framework: (vitest, jest, pytest, etc.)
- Convention: (co-located, __tests__/, etc.)
"""


def _workflow_md(config: dict) -> str:
    p = config["project"]
    cli = config["commands"]["boardCli"]
    statuses_list = "\n".join(f"- `{s}`" for s in config["board"]["statuses"])

    return f"""# Board Workflow

Rules for how the board operates and how agents interact with it.

## Architecture

```
.holoctl/board/
  index.json          <- computed index (fast reads, filters)
  WORKFLOW.md         <- this file (rules)
  tickets/
    _template.md      <- ticket template
    {p['prefix']}-XXX-slug.md  <- source of truth per ticket (frontmatter + body)
```

**Source of truth**: YAML frontmatter in each `tickets/{p['prefix']}-XXX-*.md`.

**index.json**: compact array derived from frontmatters. Every operation (create, move, close) updates both the ticket .md AND index.json. Never edit index.json manually.

## Dual-write protocol

Every state-changing operation follows this protocol:

1. Update the ticket .md frontmatter.
2. Update index.json reflecting the same change + recalculate counts.
3. Confirm to the user in 1 line.

Never update only one. Always both.

## Statuses

{statuses_list}

Allowed transitions: backlog→doing→review→done, any→cancelled, review→doing (rejection).

## Priorities

- `p0`: critical, blocks release
- `p1`: current sprint
- `p2`: next sprint
- `p3`: someday

## How to create a ticket

1. Get next ID: `{cli} next-id`
2. Prepare ticket data as JSON.
3. Create: `{cli} add '<json>'`
4. The CLI handles dual-write automatically.

## How agents use the board

Agents **do not edit** the board. Only the orchestrator (main chat) does dual-write.

When spawning an agent, the orchestrator:
1. Reads the ticket.
2. Verifies dependencies are done.
3. Includes relevant ticket context in the agent prompt.
4. Moves ticket to `doing`.

When the agent reports back:
- All DoD items `[x]` → move to `review`. User validates.
- Some `[ ]` → keep in `doing`. Decide whether to re-run.

## CLI reference

```bash
{cli} stat                              # counts by status
{cli} get {p['prefix']}-001               # single ticket (JSON)
{cli} ls [--sprint X] [--status X]      # list with filters
          [--agent X] [--tag X] [pN]
{cli} move {p['prefix']}-001 doing        # move + dual-write
{cli} set {p['prefix']}-001 sprint s1     # update field
{cli} add '<json>'                      # create ticket (auto-ID)
{cli} next-id                           # next available ID
{cli} rebuild-index                     # rebuild from .md files
```
"""


def _ticket_template_md(config: dict) -> str:
    p = config["project"]
    statuses = " | ".join(config["board"]["statuses"])
    priorities = " | ".join(config["board"]["priorities"])
    agents_dir = "./agents/*.md"
    return f"""---
id: {p['prefix']}-XXX
title: <verb + object>
agent: <one of {agents_dir}>
projects: null
files: <comma-separated paths this ticket touches, or null; required for `hctl board batch`>
status: <{statuses}>
priority: <{priorities}>
sprint: null
created: <ISO 8601 UTC, e.g. 2026-05-06T13:42:18Z>
updated: <ISO 8601 UTC>
completed: null
depends: null
tags: null
---

<!--
Replace each section below with real content, OR delete the entire section
(header + body) if it doesn't apply to this ticket. Don't leave HTML comments
or `(placeholder)` text — the dashboard hides empty/placeholder sections, but
the ticket .md should be clean for git diffs.

Goal — Definition of Done is REQUIRED. Everything else is optional.
-->

# Goal — Definition of Done

- [ ] <objective criterion>

# Start

<!-- Files that will be touched, current state, dependencies on other tickets. -->

# Context

<!-- Why this ticket exists. Non-obvious info the agent needs. -->

# Out of scope

<!-- What NOT to do in this task. -->

# Execution notes

<!-- Agent fills during work: blockers, decisions made, pending questions. -->
"""


def _instructions_md(config: dict) -> str:
    p = config["project"]
    cli = config["commands"]["boardCli"]
    cli_bin = cli.split()[0] if cli else "hctl"
    desc = p.get("description") or f"{p['name']} is a software project."

    return f"""# {p['name']} — Project Context

This file is the source of truth for AI assistant instructions. It compiles to tool-specific formats via `holoctl compile`.

## Identity

{desc}

## Board — mandatory CLI access

**NEVER read `.holoctl/board/index.json` directly.** All board interaction goes through the CLI:

```bash
{cli} stat                              # counts by status
{cli} get {p['prefix']}-001               # single ticket (JSON)
{cli} ls [--sprint X] [--status X]      # list with filters
          [--agent X] [--tag X] [pN]
{cli} move {p['prefix']}-001 doing        # move + dual-write
{cli} set {p['prefix']}-001 sprint s1     # update field
{cli} add '<json>'                      # create ticket (auto-ID)
{cli} next-id                           # next available ID
```

## Available agents

Active personas live in `.holoctl/agents/`. By default only `boardmaster` is materialized at `init` — additional personas are activated on demand from the latent library.

To see what's available and what's active:

```bash
{cli_bin} agent list                    # shows library + activated
{cli_bin} agent add <name>              # materialize a persona
{cli_bin} agent remove <name>           # remove an active persona
```

The latent library currently ships: `developer`, `reviewer`, `architect`, `researcher`. More personas will be added in future releases (open-ended catalog under `holoctl/templates/agents/`).

## Available commands

- `/status` — Quick project overview
- `/ticket <title>` — Create a new ticket
- `/board [ID|filter|move|new]` — View and manage the board (kanban, inspect, filter, move)
- `/sprint [plan|review]` — Sprint management
- `/decision <description>` — Record a hard-locked decision
- `/close` — End-of-session persistence: verify work, update tickets, ready for /clear

## Decisions

(Add hard-locked decisions here as the project evolves)

## Folder map

(Customize this to describe your project structure)
"""
