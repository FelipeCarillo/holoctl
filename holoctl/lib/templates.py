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
        ".holoctl/commands/spec.md": _cmd_spec_md(config),
        ".holoctl/commands/agent-new.md": _cmd_agent_new_md(config),
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
    cli_bin = cli.split()[0] if cli else "hctl"
    return f"""---
name: status
description: "Quick project status — counts + doing + next priorities"
allowed-tools: [Bash, mcp__holoctl__board_list]
---

# /status

Call (prefer MCP, fall back to CLI):

1. `mcp__holoctl__board_list({{}})` → all tickets. Group locally by status.
2. From `doing`: list `id + title + agent`.
3. From `backlog` with `priority` ∈ {{`p0`, `p1`}}: top 3 by priority.
4. From `doing` with any `depends`: check each dep's status (use `mcp__holoctl__board_get` on each); flag if not `done`.

CLI fallback if MCP unavailable: `{cli_bin} stat`, then `{cli} ls --status doing`, then `{cli} ls --status backlog p0` and `--status backlog p1`.

## Output (≤ 10 lines, no prose)

```
## {p['name']} — sessão

Board: X backlog · Y doing · Z review · W done
Doing: PRJ-NNN title (agent)
Next p0/p1: PRJ-NNN title, PRJ-NNN title
Blocked: PRJ-NNN waits on PRJ-MMM
```
"""


def _cmd_ticket_md(config: dict) -> str:
    p = config["project"]
    return f"""---
name: ticket
description: "Create a new ticket — single or parallel batch, decided by the parallel-evaluator + boardmaster"
arguments: "<title>"
allowed-tools: [Bash, mcp__holoctl__board_list, mcp__holoctl__board_create, mcp__holoctl__board_batch]
---

# /ticket

1. **Evaluate parallelization first.** Trigger the `holoctl-parallel-evaluator` skill: can this work split into N disjoint pieces? Propose the partition (or single) before calling boardmaster.

2. **Collect inputs** if not already clear from the argument and context: `title`, `priority` (`p0..p3`), `agent`, `acceptance` (1-5 verifiable criteria). Ask the user **once** with all gaps in one batched question. Never guess.

3. **Delegate to boardmaster**, passing the request + the parallel-evaluator's verdict (single OR candidate batch). The boardmaster calls `mcp__holoctl__board_create` or `mcp__holoctl__board_batch`.

4. **Confirm in one line per ticket**: `{p['prefix']}-NNN created: <title> (agent=<name>, priority=<pN>)`.

The boardmaster owns the schema — see `.claude/agents/boardmaster.md` for what fields are auto vs user-set. You never type `id`, `created`, `updated`, `status` — those come from the CLI/MCP.
"""


def _cmd_spec_md(config: dict) -> str:
    p = config["project"]
    return f"""---
name: spec
description: "Spec-Driven Development entry point — turn an external board item (or a fresh idea) into a spec + child tasks ready to execute"
arguments: "[<external-board-url-or-ref>]"
allowed-tools: [Bash, Read, Glob, mcp__holoctl__board_create, mcp__holoctl__board_batch, mcp__holoctl__board_show, mcp__holoctl__board_children, mcp__holoctl__board_list]
---

# /spec

Turn a request from an external board (Trello/Linear/Azure DevOps/Jira/GitHub/Slack — or just a pasted user story) into a structured **spec** in `.holoctl/`, then decompose it into parallel-safe child tasks ready for execution.

## Step 1 — Source intake

**Always try MCP first.** Invoke the `holoctl-provider-mcp` skill before asking for paste:

1. Pass the user's input (URL or ref) to the provider-mcp skill.
2. The skill consults `mcp__holoctl__config_show()` for the provider catalog, matches the URL against each provider's `url_pattern`, and probes the configured `mcp_fetch_tool`.
3. If the MCP tool is connected → use the returned body directly, with `source_*` pre-filled.
4. If the MCP tool isn't connected → fall back to "paste the content here" with `source_*` still set from the URL match (so traceability is preserved even without MCP).

If no argument is given: assume the user is pasting a story / request in the conversation. Set `source_provider="manual"`.

## Step 2 — Discuss to refine

Reach agreement on (one batched question, never piecewise):

- **Scope** — what's in, what's out
- **Acceptance criteria** — 3-7 verifiable items
- **Files / modules** — paths the work will touch (use `Glob` to confirm they exist)
- **Edge cases** worth surfacing
- **Risks / unknowns** worth flagging

Don't ask if you can already infer from the source content. Default to executing, ask only when ambiguity is real.

## Step 3 — Materialize the spec

```
mcp__holoctl__board_create({{
  "title": "<spec title>",
  "kind": "spec",
  "agent": "architect",
  "priority": "<pN>",
  "acceptance": ["<refined criterion 1>", "<refined criterion 2>", ...],
  "context": "<consolidated discussion + scope + edge cases>",
  "out_of_scope": "<what NOT to do>",
  "files": ["<file 1>", "<file 2>"],
  "source_provider": "<provider or 'manual'>",
  "source_ref": "<ref or null>",
  "source_url": "<url or null>",
  "source_label": "<label or null>"
}})
```

Capture the returned `SPEC_ID` ({p['prefix']}-NNN).

## Step 4 — Hand off to boardmaster for decomposition

Trigger the `holoctl-parallel-evaluator` skill. Then delegate to boardmaster with the spec as parent:

```
mcp__holoctl__board_batch({{
  "shared": {{
    "parent": "<SPEC_ID>",
    "kind": "task",
    "source_provider": "<inherited>",
    "source_ref": "<inherited>",
    "tags": ["spec:<SPEC_ID>"]
  }},
  "tickets": [
    {{"title": "...", "agent": "developer", "priority": "p1",
      "files": ["..."], "acceptance": ["..."]}},
    ...
  ]
}})
```

Children inherit `parent` + `source_*` from `shared` — no need to repeat per-ticket.

## Step 5 — Confirm and propose execution

Report in one block:

```
Spec: {p['prefix']}-NNN <title> (source: <provider>:<ref>)
Children: <N> tasks created
  {p['prefix']}-NNN+1: <title> (agent=developer, files=...)
  {p['prefix']}-NNN+2: <title> (agent=developer, files=...)
  ...

Next: activate <developer> on {p['prefix']}-NNN+1? (or `hctl agent add` first)
```

End with the actionable proposal. The execution itself happens via subagent (Task tool) — not your job here.
"""


def _cmd_agent_new_md(config: dict) -> str:
    cli_bin = (config["commands"]["boardCli"].split()[0]
               if config.get("commands", {}).get("boardCli") else "hctl")
    return f"""---
name: agent-new
description: "Design a brand-new specialized persona tailored to this project's stack. Delegates to the agent-designer persona, which reads the repo and drafts a schema-correct .md."
arguments: "<name> [<one-line-description>]"
allowed-tools: [Bash, Read, Glob, Grep, Write, mcp__holoctl__agent_list_available, mcp__holoctl__agent_add, mcp__holoctl__agent_create]
---

# /agent-new

Creates a new specialized persona that doesn't exist in the library — tailored to this specific project.

## Step 1 — Collect inputs (one batched question if missing)

- **`name`** (from argument): kebab-case, no spaces.
- **`description`** (one line): what this persona does and when it should fire.
- **`signals`** (optional): paths/dirs the persona will own (else agent-designer discovers).

## Step 2 — Library check

`mcp__holoctl__agent_list_available()`. If `name` is already in the library, **don't draft a new one** — offer to activate it:

> "`<name>` already exists in the library. Activate via `{cli_bin} agent add <name>` (or `mcp__holoctl__agent_add`)?"

Otherwise proceed.

## Step 3 — Activate `agent-designer` if needed

Check the response of `agent_list_available`:
- If `agent-designer` is in `library` but not `active`: activate first via `mcp__holoctl__agent_add({{"name": "agent-designer"}})`.
- If already active: continue.

## Step 4 — Delegate the draft

Invoke `agent-designer` (via Claude Code's subagent / Task tool) with this brief:

```
Design a persona named "<name>".
Description: "<one-line description>".
Signals (if provided): <paths>.

Discover the repo first (README, package files, top-level dirs).
Cross-check against active personas (via mcp__holoctl__agent_list_available).
Produce the full .md body — frontmatter + sections — per the schema in your own prompt.
Return ONLY the body, no preamble.
```

The agent-designer returns the persona body.

## Step 5 — Save as draft, preview, confirm

Write the returned body to `.holoctl/agents/<name>.draft.md` (note the `.draft` suffix — not active yet).

Show the user a preview:
- Frontmatter summary: `model`, `tools`, `paths` (3-5 globs).
- Identity paragraph + Scope bullets.

Ask: **"Apply this persona? (y / edit / cancel)"**

## Step 6 — Activate

On `y`:
1. Read the `.draft.md`.
2. Call `mcp__holoctl__agent_create({{"name": "<name>", "body": <full content>}})`. This validates frontmatter and writes `.holoctl/agents/<name>.md` (without the `.draft.`).
3. Delete the `.draft.md`.
4. Run `{cli_bin} compile --target claude` to emit `.claude/agents/<name>.md`.
5. Report: `Activated <name> (model=<model>, paths=<N globs>).`

On `edit`: offer to open the `.draft.md` for hand-editing; user can run `/agent-new <name>` again to finalize.

On `cancel`: delete the `.draft.md`. Report nothing changed.
"""


def _cmd_board_md(cli: str, p: dict) -> str:
    return f"""---
name: board
description: "View board (kanban) or inspect/move a ticket. Always via MCP/CLI — never read ticket .md files directly."
arguments: "[<ID> | @agent | #tag | sprint:<name> | p0..p3 | move <ID> <status> | new <title>]"
allowed-tools: [Bash, mcp__holoctl__board_list, mcp__holoctl__board_show, mcp__holoctl__board_move]
---

# /board

## No argument → kanban view

`mcp__holoctl__board_list({{}})`. Group locally by status; output compact:

```
Backlog (N)         | Doing (N)          | Review (N)       | Done (N)
{p['prefix']}-019 p1 title  | {p['prefix']}-018 title    |                  | {p['prefix']}-016 title
```

Any `doing` with `updated` >5d ago → prefix `⚠ stalled`.

## `<ID>` → inspect

`mcp__holoctl__board_show({{"id":"<ID>"}})`. Show frontmatter + body as-is. **Never** open `.holoctl/board/tickets/*.md` directly.

## Filters

- `@<agent>` → `board_list({{"agent":"<agent>"}})`
- `#<tag>` → `board_list({{"tag":"<tag>"}})`
- `sprint:<name>` → `board_list({{"sprint":"<name>"}})`
- `p0..p3` → `board_list({{"priority":"<pN>"}})`

## `move <ID> <status>`

`mcp__holoctl__board_move({{"id":"<ID>","status":"<status>"}})`. Confirm in 1 line.

## `new <title>` → delegate to `/ticket`
"""


def _cmd_sprint_md(cli: str) -> str:
    return f"""---
name: sprint
description: "Plan or review a sprint via the board MCP/CLI"
arguments: "[plan|review]"
allowed-tools: [Bash, mcp__holoctl__board_list, mcp__holoctl__board_set]
---

# /sprint

## No argument (status of current sprint)

`board_list({{"status":"doing"}})` + `board_list({{"status":"review"}})`. Group by `sprint`. Per sprint: `X/Y completed (Z%)`. Flag tickets with undone `depends`.

## `plan`

1. `board_list({{"status":"backlog"}})`.
2. Suggest selection by: dependencies done first, p0 > p1 > p2 > p3, capacity.
3. After user approval: `board_set({{"id":"<ID>","field":"sprint","value":"<name>"}})` per ticket.

## `review`

1. `board_list({{"sprint":"<current>"}})`.
2. Report: completed (with dates), carried over (with reasons), velocity.
3. Suggest next-sprint adjustments.
"""


def _cmd_decision_md() -> str:
    return """---
name: decision
description: "Record a hard-locked ADR in .holoctl/context/decisions/"
arguments: "<one-line summary>"
allowed-tools: [Bash, Read, Write, Glob]
---

# /decision

ADRs are **immutable**. To reverse, create a new ADR that supersedes the original.

## Steps

1. List existing decisions: `Glob .holoctl/context/decisions/*.md`. Skim titles for duplicates — refuse if the same decision exists.
2. Slugify the title (lowercase, dashes, ≤ 40 chars).
3. Create `.holoctl/context/decisions/YYYY-MM-DD-<slug>.md`:

```markdown
---
date: YYYY-MM-DD
title: <one-line summary>
status: accepted
---

## Context

<why this decision was needed — surrounding constraint, what triggered it>

## Decision

<what was decided, concretely>

## Implications

<what changes in practice; rules that follow from this>
```

4. Confirm in one line: `Decision recorded: YYYY-MM-DD-<slug>`.
"""


def _cmd_close_md(cli: str, p: dict) -> str:
    cli_bin = cli.split()[0] if cli else "hctl"
    return f"""---
name: close
description: "End-of-session persistence — verify open tickets reflect actual work via git diff + board MCP, then ready for /clear"
arguments: ""
allowed-tools: [Bash, mcp__holoctl__board_list, mcp__holoctl__board_show, mcp__holoctl__board_ack, mcp__holoctl__board_note, mcp__holoctl__board_move]
---

# /close

## Step 1 — Snapshot actual work

`git status` + `git diff --name-only HEAD`. If git unavailable: rely on conversation memory.

## Step 2 — Cross-reference open tickets

`mcp__holoctl__board_list({{"status":"doing"}})` + `mcp__holoctl__board_list({{"status":"review"}})`.

For each open ticket: `board_show({{"id":"<ID>"}})`. Compare `files:` in frontmatter with the git diff to identify which tickets had real work this session.

## Step 3 — Update tickets via MCP/CLI only

For each ticket with verified work:

1. `mcp__holoctl__board_ack({{"id":"<ID>","idx":<n>}})` for each acceptance item now verifiably done.
2. `mcp__holoctl__board_note({{"id":"<ID>","text":"<one-line summary of what was done>"}})` to append a session checkpoint.
3. If all acceptance items checked: `mcp__holoctl__board_move({{"id":"<ID>","status":"done"}})`. Otherwise leave in `doing`.

**Never edit the ticket `.md` directly.** The deny-list blocks it.

For substantial work without a ticket: create one retroactively (delegate to boardmaster). Trivial work (typo, config): skip.

## Step 4 — ADRs

For non-obvious decisions made this session, invoke `/decision <summary>` per decision. The slash command creates the ADR; don't write the file by hand here.

## Step 5 — Final report

```
## {p['name']} — close YYYY-MM-DD

Closed:    {p['prefix']}-001, {p['prefix']}-002       (or "none")
Updated:   {p['prefix']}-003 (acked 2, noted)         (or "none")
New:       {p['prefix']}-004 (untracked work)         (or "none")
ADRs:      YYYY-MM-DD-foo                          (or "none")
Uncovered: <files changed with no ticket>          (or "none")

Ready for /clear.
```

If nothing of substance happened: "Session trivial — nothing to save. Ready for /clear."
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
    return f"""---
# Auto — managed by hctl, never edit by hand
id: {p['prefix']}-XXX
status: backlog
created:
updated:
completed:

# User — set on creation (via mcp__holoctl__board_create / hctl board add)
title:
agent:
priority: p2
files:
projects:
depends:
tags:
---

# Acceptance — Definition of Done

- [ ]

# Context

# Out of scope

# Notes
"""


def _instructions_md(config: dict) -> str:
    p = config["project"]
    cli_bin = (config["commands"]["boardCli"].split()[0]
               if config.get("commands", {}).get("boardCli") else "hctl")
    desc = p.get("description") or f"{p['name']} is a software project."

    return f"""# {p['name']}

{desc}

## Invariantes (não negociáveis)

- O board é gerenciado **somente** pela CLI/MCP. Nunca edite `.holoctl/board/index.json` nem os `.md` em `.holoctl/board/tickets/` — o `permissions.deny` bloqueia, e seu edit não persiste.
- Tickets têm `acceptance` (Definition of Done) explícito. Trabalho sem ticket = trabalho não rastreado.
- Decisões duráveis viram ADRs em `.holoctl/context/decisions/` (use `/decision`). Imutáveis.
- Memória durável vai pra `.holoctl/memory/` via `{cli_bin} memory add` ou `mcp__holoctl__memory_add`. Não duplique no `CLAUDE.md`.

## Onde está o quê

- Tickets: `/board`, `/status`, ou `mcp__holoctl__board_list`
- Memória: @.holoctl/memory/MEMORY.md
- Decisões/ADRs: `.holoctl/context/decisions/`
- Personas: `{cli_bin} agent list` (ativas + library); `{cli_bin} agent add <name>` materializa da library

## Comandos rápidos

`/holoctl` `/status` `/ticket` `/spec` `/board` `/sprint` `/decision` `/close`

`/spec` é o ponto de entrada do **Spec-Driven Development**: cola uma história / card de board externo (Trello, Linear, Azure DevOps, Jira, GitHub, Slack) ou descreve o trabalho, e o fluxo discute → cria spec → decompõe em tasks filhas → propõe execução.

## Decisões fixadas

(esta seção é populada à medida que ADRs são criados em `.holoctl/context/decisions/`)
"""
