---
name: sprint
description: "Plan or review a sprint via the board MCP/CLI"
arguments: "[plan|review]"
allowed-tools: [Bash, mcp__holoctl__board_list, mcp__holoctl__board_set]
---

# /sprint

## No argument (status of current sprint)

`board_list({"status":"doing"})` + `board_list({"status":"review"})`. Group by `sprint`. Per sprint: `X/Y completed (Z%)`. Flag tickets with undone `depends`.

## `plan`

1. `board_list({"status":"backlog"})`.
2. Suggest selection by: dependencies done first, p0 > p1 > p2 > p3, capacity.
3. After user approval: `board_set({"id":"<ID>","field":"sprint","value":"<name>"})` per ticket.

## `review`

1. `board_list({"sprint":"<current>"})`.
2. Report: completed (with dates), carried over (with reasons), velocity.
3. Suggest next-sprint adjustments.
