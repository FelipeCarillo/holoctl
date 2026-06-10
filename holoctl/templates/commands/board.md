---
name: board
description: "View board (kanban) or inspect/move a ticket. Always via MCP/CLI — never read ticket .md files directly."
arguments: "[<ID> | @agent | #tag | sprint:<name> | p0..p3 | move <ID> <status> | new <title>]"
allowed-tools: [Bash, mcp__holoctl__board_list, mcp__holoctl__board_show, mcp__holoctl__board_move]
---

# /board

## No argument → kanban view

`mcp__holoctl__board_list({})`. Group locally by status; output compact:

```
Backlog (N)         | Doing (N)          | Review (N)       | Done (N)
{{project.prefix}}-019 p1 title  | {{project.prefix}}-018 title    |                  | {{project.prefix}}-016 title
```

Any `doing` with `updated` >5d ago → prefix `⚠ stalled`.

## `<ID>` → inspect

`mcp__holoctl__board_show({"id":"<ID>"})`. Show frontmatter + body as-is. **Never** open `.holoctl/board/tickets/*.md` directly.

## Filters

- `@<agent>` → `board_list({"agent":"<agent>"})`
- `#<tag>` → `board_list({"tag":"<tag>"})`
- `sprint:<name>` → `board_list({"sprint":"<name>"})`
- `p0..p3` → `board_list({"priority":"<pN>"})`

## `move <ID> <status>`

`mcp__holoctl__board_move({"id":"<ID>","status":"<status>"})`. Confirm in 1 line.

## `new <title>` → delegate to `/ticket`
