# Board Workflow

Rules for how the board operates and how agents interact with it.

## Architecture

```
.projctl/board/
  index.json          <- computed index (fast reads, filters)
  WORKFLOW.md         <- this file (rules)
  tickets/
    _template.md      <- ticket template
    TST-XXX-slug.md  <- source of truth per ticket (frontmatter + body)
```

**Source of truth**: YAML frontmatter in each `tickets/TST-XXX-*.md`.

**index.json**: compact array derived from frontmatters. Every operation (create, move, close) updates both the ticket .md AND index.json. Never edit index.json manually.

## Dual-write protocol

Every state-changing operation follows this protocol:

1. Update the ticket .md frontmatter.
2. Update index.json reflecting the same change + recalculate counts.
3. Confirm to the user in 1 line.

Never update only one. Always both.

## Statuses

- `backlog`
- `doing`
- `review`
- `done`
- `cancelled`

Allowed transitions: backlog→doing→review→done, any→cancelled, review→doing (rejection).

## Priorities

- `p0`: critical, blocks release
- `p1`: current sprint
- `p2`: next sprint
- `p3`: someday

## How to create a ticket

1. Get next ID: `projctl board next-id`
2. Prepare ticket data as JSON.
3. Create: `projctl board add '<json>'`
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
projctl board stat                              # counts by status
projctl board get TST-001               # single ticket (JSON)
projctl board ls [--sprint X] [--status X]      # list with filters
          [--agent X] [--tag X] [pN]
projctl board move TST-001 doing        # move + dual-write
projctl board set TST-001 sprint s1     # update field
projctl board add '<json>'                      # create ticket (auto-ID)
projctl board next-id                           # next available ID
projctl board rebuild-index                     # rebuild from .md files
```
