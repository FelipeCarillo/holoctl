export function getTemplates(config) {
  const p = config.project;
  const cli = config.commands.boardCli;

  return {
    // Board
    '.holoctl/board/WORKFLOW.md': workflowMd(config),
    '.holoctl/board/tickets/_template.md': ticketTemplateMd(config),

    // Agents
    '.holoctl/agents/developer.md': agentDeveloperMd(p),
    '.holoctl/agents/reviewer.md': agentReviewerMd(p),
    '.holoctl/agents/architect.md': agentArchitectMd(p),
    '.holoctl/agents/researcher.md': agentResearcherMd(p),

    // Commands
    '.holoctl/commands/status.md': cmdStatusMd(cli, p),
    '.holoctl/commands/ticket.md': cmdTicketMd(cli, p),
    '.holoctl/commands/board.md': cmdBoardMd(cli, p),
    '.holoctl/commands/sprint.md': cmdSprintMd(cli, p),
    '.holoctl/commands/decision.md': cmdDecisionMd(),
    '.holoctl/commands/close.md': cmdCloseMd(cli, p),

    // Context
    '.holoctl/context/objective.md': contextObjectiveMd(p),
    '.holoctl/context/architecture.md': contextArchitectureMd(p),
    '.holoctl/context/conventions.md': contextConventionsMd(p),

    // Instructions
    '.holoctl/instructions.md': instructionsMd(config),
  };
}

// ── Agents ────────────────────────────────────────────────────

function agentDeveloperMd(p) {
  return `---
name: developer
description: "General-purpose code implementation agent. Takes tickets with clear specs and produces working code following project conventions."
model: standard
tools: [read, search, edit, write, shell]
trigger: ticket
---

# Identity

You are the **Developer** for ${p.name}. You implement features from tickets with clear specifications. You follow existing patterns and conventions — you don't invent architecture.

# Guard Rail

You only begin work if you receive a ticket from \`.holoctl/board/tickets/${p.prefix}-XXX-*.md\` with **Start** and **Goal (Definition of Done)** sections filled in. If the ticket is missing or the Goal is vague, REFUSE and ask the orchestrator to complete the ticket first.

Before any action:
1. Read the entire ticket.
2. Confirm that the Start section matches the current codebase state.
3. If it diverged, stop and report — do not guess.

# Scope

- Create and edit source files within the project
- Follow coding conventions defined in the project instruction file
- Run linter and build checks after changes

**Does not**: create new architectural abstractions (that's \`architect\`), write test data (that's \`mock-data-curator\`), do QA (that's \`qa\`).

# Work Order

1. Read the ticket. Confirm Start.
2. Read relevant interfaces/contracts — you consume, not modify.
3. Implement the changes.
4. Run lint + build. Fix failures.
5. Mark Definition of Done items.

# Report Format

Three sections:
- **Done**: bullets with file:line references.
- **Definition of Done**: each Goal item marked \`[x]\` or \`[ ]\`.
- **Suggested next step**: 1 line.
`;
}

function agentReviewerMd(p) {
  return `---
name: reviewer
description: "Code review agent. Reviews changes for correctness, conventions, security, and performance."
model: reasoning
tools: [read, search, shell]
trigger: ticket
---

# Identity

You are the **Code Reviewer** for ${p.name}. You review code changes after implementation, checking for correctness, security, performance, and adherence to project conventions.

# Guard Rail

You only review if pointed to a specific ticket or set of files. You do NOT write code — you flag issues for the developer to fix.

# Checklist

For every review, check:
- [ ] Changes match the ticket's Definition of Done
- [ ] No security vulnerabilities (injection, XSS, auth bypass)
- [ ] No hardcoded secrets or credentials
- [ ] Follows project naming conventions
- [ ] No unnecessary complexity or premature abstraction
- [ ] Error handling at system boundaries
- [ ] Types are correct (no \`any\` in TypeScript)
- [ ] Lint and build pass

# Report Format

- **Verdict**: approve / request-changes / comment
- **Issues**: numbered list with file:line, severity (critical/warning/nit), description
- **Positive notes**: what was done well (1-2 bullets)
`;
}

function agentArchitectMd(p) {
  return `---
name: architect
description: "Architecture and design agent. Defines contracts, interfaces, boundaries, and resolves coupling."
model: reasoning
tools: [read, search, edit, write]
trigger: ticket
---

# Identity

You are the **Architect** for ${p.name}. You decide *how* something should be built, not *what* to build. You think in contracts, dependencies, and boundaries before any implementation.

# Guard Rail

You only begin work if you receive a ticket with **Start** and **Goal** filled in. If missing, REFUSE.

# Scope

- Define and evolve interfaces and contracts
- Decide module/feature boundaries
- Refactor when coupling is detected
- Document architectural decisions

**Does not**: implement full UI (delegates to \`developer\`), write test data, do QA.

# Work Order

1. Read the ticket. Confirm Start.
2. List design decisions the ticket implies.
3. Write the interface/contract first, then skeleton implementation.
4. Document the extension point for future changes.

# Report Format

- **Done**: bullets with file:line references.
- **Definition of Done**: each Goal item marked \`[x]\` or \`[ ]\`.
- **Suggested next step**: 1 line.
`;
}

function agentResearcherMd(p) {
  return `---
name: researcher
description: "Research agent. Investigates topics, competitors, regulations, and synthesizes findings."
model: reasoning
tools: [read, search, browser]
trigger: natural-language
---

# Identity

You are the **Researcher** for ${p.name}. You investigate topics in depth and return structured, sourced findings. You do not write code.

# Scope

- Market research and competitor analysis
- Regulatory and compliance research
- Technology evaluation and comparison
- Domain-specific knowledge gathering

# Report Format

- **Summary**: 2-3 sentence answer
- **Key findings**: numbered list with sources
- **Implications for ${p.name}**: what this means for the project
- **Recommended next steps**: 1-2 actions
`;
}

// ── Commands ──────────────────────────────────────────────────

function cmdStatusMd(cli, p) {
  return `---
name: status
description: "Quick project status overview"
arguments: ""
---

# /status — Project status overview

1. Run \`${cli} stat\` for ticket counts.
2. Run \`${cli} ls --status doing\` for active work.
3. Run \`${cli} ls --status backlog p0\` and \`${cli} ls --status backlog p1\` for next priorities.
4. For tickets with dependencies, use \`${cli} get <ID>\` to check if deps are done.

## Output format

\`\`\`
## ${p.name} — Status {{date}}

**Board:** X backlog · Y doing · Z review · W done
**Doing now:** {{list of ID title (agent)}}
**Next (p1):** {{top 3 backlog p1}}
**Blocked:** {{tickets with undone deps, or "none"}}
\`\`\`

Maximum 10 lines. No prose.
`;
}

function cmdTicketMd(cli, p) {
  return `---
name: ticket
description: "Create a new ticket on the board"
arguments: "<title>"
---

# /ticket — Create a ticket

1. Run \`${cli} next-id\` to get the next number.
2. Fill in:
   - **title**: from the user's argument (verb + object)
   - **agent**: infer from the type of work, or ask
   - **projects**: list of subdir names this ticket touches (\`${cli.replace(' board', '')} repo list\` to see them); empty if workspace-wide
   - **priority**: infer or ask (p0|p1|p2|p3)
   - **Start**: fill if enough context, otherwise ask
   - **Goal (DoD)**: derive from title + context, each item as \`[ ]\`
3. Save the ticket: \`${cli} add '<json>'\`
4. Confirm: "Ticket ${p.prefix}-NNN created: {title}. Agent: {name}. Priority: {pN}."

If the user gave enough context, don't ask — fill and confirm.
`;
}

function cmdBoardMd(cli, p) {
  return `---
name: board
description: "View and manage the project board — kanban view, filters, ticket inspect, move"
arguments: "[<ID> | @agent | #tag | sprint:<name> | p0..p3 | move <ID> <status> | new <title>]"
---

# /board — Project board

## No argument → kanban view

1. Run \`${cli} stat\` for counts by status.
2. Run \`${cli} ls --status backlog\`, \`--status doing\`, \`--status review\`, \`--status done\` to group by column.
3. Format as compact table:
   \`\`\`
   Backlog (N)          | Doing (N)             | Review (N)       | Done (N)
   ${p.prefix}-019 p1 title   | ${p.prefix}-018 title       |                  | ${p.prefix}-016 title
   ${p.prefix}-020 p1 fix     |                       |                  | (+ N more)
   \`\`\`
4. Any ticket in \`doing\` with \`updated\` >5 days ago → prefix with \`⚠ stalled\`.

## /board \`<ID>\` → inspect ticket

1. Run \`${cli} get <ID>\` for metadata (status, priority, agent, sprint, deps).
2. Read the ticket file \`.holoctl/board/tickets/<ID>-*.md\` for full body.
3. Show all sections: Start, Goal (Definition of Done), Context, Out of scope, Execution notes.

## Filters: \`@agent\` | \`#tag\` | \`sprint:<name>\` | \`p0\`–\`p3\`

- \`@developer\` → \`${cli} ls --agent developer\`
- \`#tag\` → \`${cli} ls --tag tag\`
- \`sprint:s1\` → \`${cli} ls --sprint s1\`
- \`p0\`–\`p3\` → \`${cli} ls <pN>\`

Multiple filters can be combined, e.g. \`/board @developer p1\`.

## /board move \`<ID>\` \`<status>\` → move ticket

Run \`${cli} move <ID> <status>\`.
Confirm: "<ID>: from → to"

## /board new \`<title>\` → create ticket

Follow the same flow as \`/ticket\`. See /ticket for full spec.
`;
}

function cmdSprintMd(cli) {
  return `---
name: sprint
description: "Plan or review a sprint"
arguments: "[plan|review]"
---

# /sprint — Sprint management

## No argument (current sprint)

1. Run \`${cli} ls --status doing\` and \`${cli} ls --status review\` for active tickets.
2. For each sprint found, run \`${cli} ls --sprint <name>\`.
3. Show progress: X/Y completed (Z%).
4. Highlight blocked tickets.

## Plan

1. Run \`${cli} ls --status backlog\` to list the backlog.
2. Prioritize by: dependencies (done first), priority (p0 > p1 > p2 > p3), capacity.
3. Suggest selection with justification and sprint name.
4. After approval: \`${cli} set <ID> sprint <sprint-name>\` for each ticket.

## Review

1. Run \`${cli} ls --sprint <current>\` to list all sprint tickets.
2. Report: completed (with dates), left behind (with reasons), velocity.
3. Suggest adjustments for next sprint.
`;
}

function cmdDecisionMd() {
  return `---
name: decision
description: "Record a hard-locked decision"
arguments: "<description>"
---

# /decision — Record a decision

1. Read \`.holoctl/context/decisions/\` to check for duplicates.
2. Create a new file \`.holoctl/context/decisions/YYYY-MM-DD-<slug>.md\` with:

\`\`\`markdown
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
\`\`\`

3. Confirm: "Decision recorded: {title}."

Decisions are **immutable** by default. To reverse, create a new decision that supersedes the original.
`;
}

function cmdCloseMd(cli, p) {
  return `---
name: close
description: "End-of-session persistence — verify all work done, update tickets, record decisions, ready for context clear"
arguments: ""
---

# /close — Session close

Run this command before clearing the context. It ensures nothing is lost.

## Step 1 — Verify actual work via git

Run \`git status\` and \`git diff HEAD\` to list files actually changed this session.

If git is unavailable: skip this step and proceed from conversation memory only.

## Step 2 — Cross-reference with open tickets

Run \`${cli} ls --status doing\` and \`${cli} ls --status review\`.

For each open ticket, check whether the files listed in its **Start** section appear in the git diff (and that they belong to one of the ticket's \`projects\`).

## Step 3 — Update tickets

For each ticket where the work is verifiably done (DoD items met OR files changed match the ticket's projects/Start section):

1. Open the ticket file \`.holoctl/board/tickets/<ID>-*.md\`.
2. Mark completed DoD items: \`[ ]\` → \`[x]\`.
3. Append to **Execution notes**: a bullet summarizing what was done and any key decisions made.
4. Move status:
   - All DoD \`[x]\` → \`${cli} move <ID> done\`
   - Partially done → keep in \`doing\`, note what remains

For work done without a ticket (files changed, no ticket covers them):
- If substantial (feature, fix, refactor): \`${cli} add '{"title":"...","status":"done","agent":"...",...}'\`
- If trivial (typo, config): skip

## Step 4 — Record decisions

For each non-obvious decision made this session (architecture, trade-off, direction change):

Create \`.holoctl/context/decisions/YYYY-MM-DD-<slug>.md\`:

\`\`\`markdown
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
\`\`\`

## Step 5 — Final report

\`\`\`
## ${p.name} — Session close YYYY-MM-DD

Tickets closed:    ${p.prefix}-001, ${p.prefix}-002  (or "none")
Tickets updated:   ${p.prefix}-003 (execution notes)  (or "none")
New tickets:       ${p.prefix}-004 (untracked work)    (or "none")
Decisions:         YYYY-MM-DD-foo.md                  (or "none")
Uncovered files:   (files changed with no ticket)      (or "none")

Ready for /clear.
\`\`\`

If the session had no substantial work: output "Session trivial — nothing to save. Ready for /clear."
`;
}

// ── Context docs ──────────────────────────────────────────────

function contextObjectiveMd(p) {
  return `# Project Objective

## What

${p.description || `(Describe what ${p.name} does in 1-2 sentences)`}

## Why

(What problem does this solve? Who benefits?)

## Success criteria

- [ ] (Define what "done" looks like)
`;
}

function contextArchitectureMd(p) {
  return `# Architecture

## Tech stack

(List the main technologies, frameworks, and services)

## Structure

\`\`\`
(High-level directory/module layout)
\`\`\`

## Key patterns

(Architectural patterns: feature-first, DI, event-driven, etc.)

## Boundaries

(What's in scope vs out of scope for this codebase)
`;
}

function contextConventionsMd(p) {
  return `# Coding Conventions

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
`;
}

// ── Workflow & Instructions ───────────────────────────────────

function workflowMd(config) {
  const p = config.project;
  const cli = config.commands.boardCli;

  return `# Board Workflow

Rules for how the board operates and how agents interact with it.

## Architecture

\`\`\`
.holoctl/board/
  index.json          <- computed index (fast reads, filters)
  WORKFLOW.md          <- this file (rules)
  tickets/
    _template.md       <- ticket template
    ${p.prefix}-XXX-slug.md  <- source of truth per ticket (frontmatter + body)
\`\`\`

**Source of truth**: YAML frontmatter in each \`tickets/${p.prefix}-XXX-*.md\`.

**index.json**: compact array derived from frontmatters. Every operation (create, move, close) updates both the ticket .md AND index.json. Never edit index.json manually.

## Dual-write protocol

Every state-changing operation follows this protocol:

1. Update the ticket .md frontmatter.
2. Update index.json reflecting the same change + recalculate counts.
3. Confirm to the user in 1 line.

Never update only one. Always both.

## Statuses

${config.board.statuses.map(s => `- \`${s}\``).join('\n')}

Allowed transitions: backlog→doing→review→done, any→cancelled, review→doing (rejection).

## Priorities

- \`p0\`: critical, blocks release
- \`p1\`: current sprint
- \`p2\`: next sprint
- \`p3\`: someday

## How to create a ticket

1. Get next ID: \`${cli} next-id\`
2. Prepare ticket data as JSON.
3. Create: \`${cli} add '<json>'\`
4. The CLI handles dual-write automatically.

## How agents use the board

Agents **do not edit** the board. Only the orchestrator (main chat) does dual-write.

When spawning an agent, the orchestrator:
1. Reads the ticket.
2. Verifies dependencies are done.
3. Includes relevant ticket context in the agent prompt.
4. Moves ticket to \`doing\`.

When the agent reports back:
- All DoD items \`[x]\` → move to \`review\`. User validates.
- Some \`[ ]\` → keep in \`doing\`. Decide whether to re-run.

## CLI reference

\`\`\`bash
${cli} stat                              # counts by status
${cli} get ${p.prefix}-001               # single ticket (JSON)
${cli} ls [--sprint X] [--status X]      # list with filters
          [--agent X] [--tag X] [pN]
${cli} move ${p.prefix}-001 doing        # move + dual-write
${cli} set ${p.prefix}-001 sprint s1     # update field
${cli} add '<json>'                      # create ticket (auto-ID)
${cli} next-id                           # next available ID
${cli} rebuild-index                     # rebuild from .md files
\`\`\`
`;
}

function ticketTemplateMd(config) {
  const p = config.project;
  return `---
id: ${p.prefix}-XXX
title: <verb + object>
agent: <developer | reviewer | architect | researcher>
projects: null
status: backlog
priority: <p0 | p1 | p2 | p3>
sprint: null
created: YYYY-MM-DD
updated: YYYY-MM-DD
completed: null
depends: null
tags: null
---

# Start

Current state verified BEFORE starting. List:

- Files that will be touched (relative paths)
- Current relevant state
- Dependencies on other tickets (cite IDs)

# Goal — Definition of Done

Objective criteria. Each item will be marked \`[x]\` or \`[ ]\` in the final report.

- [ ] criterion 1
- [ ] criterion 2
- [ ] lint and build pass

# Context

Why this ticket exists. Non-obvious info the agent needs.

# Out of scope

What NOT to do in this task.

# Execution notes

(Agent fills: blockers, decisions made, pending questions)
`;
}

function instructionsMd(config) {
  const p = config.project;
  const cli = config.commands.boardCli;

  return `# ${p.name} — Project Context

This file is the source of truth for AI assistant instructions. It compiles to tool-specific formats via \`holoctl compile\`.

## Identity

${p.description || `${p.name} is a software project.`}

## Board — mandatory CLI access

**NEVER read \`.holoctl/board/index.json\` directly.** All board interaction goes through the CLI:

\`\`\`bash
${cli} stat                              # counts by status
${cli} get ${p.prefix}-001               # single ticket (JSON)
${cli} ls [--sprint X] [--status X]      # list with filters
          [--agent X] [--tag X] [pN]
${cli} move ${p.prefix}-001 doing        # move + dual-write
${cli} set ${p.prefix}-001 sprint s1     # update field
${cli} add '<json>'                      # create ticket (auto-ID)
${cli} next-id                           # next available ID
\`\`\`

## Available agents

See \`.holoctl/agents/\` for full definitions:

- \`developer\` (standard): General-purpose code implementation
- \`reviewer\` (reasoning): Code review for correctness and security
- \`architect\` (reasoning): Architecture, contracts, boundaries
- \`researcher\` (reasoning): Research, analysis, synthesis

## Available commands

- \`/status\` — Quick project overview
- \`/ticket <title>\` — Create a new ticket
- \`/board [ID|filter|move|new]\` — View and manage the board (kanban, inspect, filter, move)
- \`/sprint [plan|review]\` — Sprint management
- \`/decision <description>\` — Record a hard-locked decision
- \`/close\` — End-of-session persistence: verify work, update tickets, ready for /clear

## Decisions

(Add hard-locked decisions here as the project evolves)

## Folder map

(Customize this to describe your project structure)
`;
}
