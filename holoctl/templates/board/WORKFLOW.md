# Board Workflow

Rules for how the board operates and how agents interact with it.

## Architecture

```
.holoctl/board/
  index.json          <- computed index (fast reads, filters)
  WORKFLOW.md         <- this file (rules)
  tickets/
    _template.md      <- ticket template
    {{project.prefix}}-XXX-slug.md  <- source of truth per ticket (frontmatter + body)
```

**Source of truth**: YAML frontmatter in each `tickets/{{project.prefix}}-XXX-*.md`.

**index.json**: compact array derived from frontmatters. Every operation (create, move, close) updates both the ticket .md AND index.json. Never edit index.json manually.

## Dual-write protocol

Every state-changing operation follows this protocol:

1. Update the ticket .md frontmatter.
2. Update index.json reflecting the same change + recalculate counts.
3. Confirm to the user in 1 line.

Never update only one. Always both.

## Statuses

{{board.statusesBullets}}

Allowed transitions: backlog→doing→review→done, any→cancelled, review→doing (rejection).

## Priorities

- `p0`: critical, blocks release
- `p1`: current sprint
- `p2`: next sprint
- `p3`: someday

## How to create a ticket

1. Get next ID: `{{commands.boardCli}} next-id`
2. Prepare ticket data as JSON.
3. Create: `{{commands.boardCli}} add '<json>'`
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
{{commands.boardCli}} stat                              # counts by status
{{commands.boardCli}} get {{project.prefix}}-001               # single ticket (JSON)
{{commands.boardCli}} ls [--sprint X] [--status X]      # list with filters
          [--agent X] [--tag X] [pN]
{{commands.boardCli}} move {{project.prefix}}-001 doing        # move + dual-write
{{commands.boardCli}} set {{project.prefix}}-001 sprint s1     # update field
{{commands.boardCli}} add '<json>'                      # create ticket (auto-ID)
{{commands.boardCli}} next-id                           # next available ID
{{commands.boardCli}} rebuild-index                     # rebuild from .md files
```
