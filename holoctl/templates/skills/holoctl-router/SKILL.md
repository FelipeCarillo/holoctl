---
name: holoctl-router
description: |
  Use when the user types `/holoctl`, mentions "holoctl"/"hctl", asks for
  project status / what's pending / what's next, asks to create a ticket or
  close a session, or operates in a directory that looks like a holoctl
  workspace but the assistant isn't sure of its state. Detects workspace
  state via `hctl doctor` and routes to the right flow.
---

# Holoctl router

You are operating in (or near) a workspace managed by holoctl. Your job is to detect state and execute the right flow. Default mode = **execute**, not stop-and-ask.

The binary is `hctl` (in PATH).

## Step 1 — Detect state

Run `hctl doctor`. First line is one of:

| First line                   | Flow       | Action                                                       |
|------------------------------|------------|---------------------------------------------------------------|
| `holoctl: not initialized`   | **A**      | Read `references/flow-a-first-time.md` and follow it          |
| `holoctl: outdated`          | **B**      | Read `references/flow-b-upgrade.md` and follow it             |
| `holoctl: ok`                | **C**      | Stay here — handle the request inline (table below)          |

## Flow C — normal operation (most invocations)

Pick the right action from what the user said:

| User said                                            | Action                                                  |
|------------------------------------------------------|----------------------------------------------------------|
| "status", "what's pending"                           | `/status` or `mcp__holoctl__board_list`                  |
| "create ticket" / "/ticket"                          | `/ticket` (parallel-evaluator + boardmaster)            |
| pasted external board URL/card / "vamos planejar X"  | `/spec` (Spec-Driven flow: intake → discuss → decompose)|
| "show ticket X" / "show spec X"                      | `mcp__holoctl__board_show({"id":"X"})`                  |
| "what's inside spec X" / "children of X"             | `mcp__holoctl__board_children({"id":"X"})`              |
| "move X to <status>"                                 | `mcp__holoctl__board_move`                              |
| "delete X" / "exclui Y"                              | `mcp__holoctl__board_delete` (irreversible — confirm)   |
| "close session" / "/clear is next"                   | `/close`                                                 |
| "any suggestions?"                                   | `hctl curate show`                                      |
| "list personas"                                      | `hctl agent list`                                       |
| "activate <persona>"                                 | `mcp__holoctl__agent_add({"name":"<name>"})`           |
| "search memory <q>"                                  | `mcp__holoctl__memory_search({"query":"<q>"})`         |
| "overview" / "snapshot"                              | `hctl overview`                                          |

After any action, **react to its output**:
- If `board_list` showed p0 pendings, propose the next action (move to doing, delegate to agent).
- If `curate show` proposes a ticket, ask the user "approve? (move to done auto-executes the action)".

## Hard rules (never violate)

- **Never** edit `.holoctl/board/index.json` or `.holoctl/memory/MEMORY.md` by hand. Always via `mcp__holoctl__*` or `hctl <subcommand>`.
- **Never** read `.holoctl/board/tickets/<ID>-*.md` directly — use `mcp__holoctl__board_show` or `hctl board show <ID>`.
- **Never** overwrite hand-edited AI configs (`.cursor/rules/`, hand-edited `CLAUDE.md`, populated `AGENTS.md`). Read for context; don't rewrite.
- If `hctl` returns an error, **read the literal error**, report it, stop. Don't try alternatives silently.
- Don't end with "stop and wait." End with an actionable proposal.
