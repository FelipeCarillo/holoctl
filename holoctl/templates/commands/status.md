---
name: status
description: "Quick project status — counts + doing + next priorities"
allowed-tools: [Bash, mcp__holoctl__board_list]
---

# /status

Call (prefer MCP, fall back to CLI):

1. `mcp__holoctl__board_list({})` → all tickets. Group locally by status.
2. From `doing`: list `id + title + agent`.
3. From `backlog` with `priority` ∈ {`p0`, `p1`}: top 3 by priority.
4. From `doing` with any `depends`: check each dep's status (use `mcp__holoctl__board_get` on each); flag if not `done`.

CLI fallback if MCP unavailable: `{{commands.boardCliBin}} stat`, then `{{commands.boardCli}} ls --status doing`, then `{{commands.boardCli}} ls --status backlog p0` and `--status backlog p1`.

## Output (≤ 10 lines, no prose)

```
## {{project.name}} — sessão

Board: X backlog · Y doing · Z review · W done
Doing: PRJ-NNN title (agent)
Next p0/p1: PRJ-NNN title, PRJ-NNN title
Blocked: PRJ-NNN waits on PRJ-MMM
```
