---
name: close
description: "End-of-session persistence — verify open tickets reflect actual work via git diff + board MCP, then ready for /clear"
arguments: ""
allowed-tools: [Bash, mcp__holoctl__board_list, mcp__holoctl__board_show, mcp__holoctl__board_ack, mcp__holoctl__board_note, mcp__holoctl__board_move]
---

# /close

## Step 1 — Snapshot actual work

`git status` + `git diff --name-only HEAD`. If git unavailable: rely on conversation memory.

## Step 2 — Cross-reference open tickets

`mcp__holoctl__board_list({"status":"doing"})` + `mcp__holoctl__board_list({"status":"review"})`.

For each open ticket: `board_show({"id":"<ID>"})`. Compare `files:` in frontmatter with the git diff to identify which tickets had real work this session.

## Step 3 — Update tickets via MCP/CLI only

For each ticket with verified work:

1. `mcp__holoctl__board_ack({"id":"<ID>","idx":<n>})` for each acceptance item now verifiably done.
2. `mcp__holoctl__board_note({"id":"<ID>","text":"<one-line summary of what was done>"})` to append a session checkpoint.
3. If all acceptance items checked: `mcp__holoctl__board_move({"id":"<ID>","status":"done"})`. Otherwise leave in `doing`.

**Never edit the ticket `.md` directly.** The deny-list blocks it.

For substantial work without a ticket: create one retroactively (delegate to boardmaster). Trivial work (typo, config): skip.

## Step 4 — ADRs

For non-obvious decisions made this session, invoke `/decision <summary>` per decision. The slash command creates the ADR; don't write the file by hand here.

## Step 5 — Final report

```
## {{project.name}} — close YYYY-MM-DD

Closed:    {{project.prefix}}-001, {{project.prefix}}-002       (or "none")
Updated:   {{project.prefix}}-003 (acked 2, noted)         (or "none")
New:       {{project.prefix}}-004 (untracked work)         (or "none")
ADRs:      YYYY-MM-DD-foo                          (or "none")
Uncovered: <files changed with no ticket>          (or "none")

Ready for /clear.
```

If nothing of substance happened: "Session trivial — nothing to save. Ready for /clear."
