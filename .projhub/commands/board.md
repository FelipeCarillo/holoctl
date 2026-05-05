---
name: board
description: "View and manage the project board — kanban view, filters, ticket inspect, move"
arguments: "[<ID> | @agent | #tag | sprint:<name> | p0..p3 | move <ID> <status> | new <title>]"
---

# /board — Project board

## No argument → kanban view

1. Run `projctl board stat` for counts by status.
2. Run `projctl board ls --status backlog`, `--status doing`, `--status review`, `--status done` to group by column.
3. Format as compact table:
   ```
   Backlog (N)          | Doing (N)             | Review (N)       | Done (N)
   TST-019 p1 title   | TST-018 title       |                  | TST-016 title
   TST-020 p1 fix     |                       |                  | (+ N more)
   ```
4. Any ticket in `doing` with `updated` >5 days ago → prefix with `⚠ stalled`.

## /board `<ID>` → inspect ticket

1. Run `projctl board get <ID>` for metadata (status, priority, agent, sprint, deps).
2. Read the ticket file `.projctl/board/tickets/<ID>-*.md` for full body.
3. Show all sections: Start, Goal (Definition of Done), Context, Out of scope, Execution notes.

## Filters: `@agent` | `#tag` | `sprint:<name>` | `p0`–`p3`

- `@developer` → `projctl board ls --agent developer`
- `#tag` → `projctl board ls --tag tag`
- `sprint:s1` → `projctl board ls --sprint s1`
- `p0`–`p3` → `projctl board ls <pN>`

## /board move `<ID>` `<status>` → move ticket

Run `projctl board move <ID> <status>`.
Confirm: "<ID>: from → to"

## /board new `<title>` → create ticket

Follow the same flow as `/ticket`. See /ticket for full spec.
