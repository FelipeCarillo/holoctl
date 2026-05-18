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

## Tiebreak — spec-flow × work-item-router × ticket-discipline

These three skills all fire on "user described work that needs tracking" and their descriptions overlap. Pick by **signal strength**, top-down — first row that matches wins:

| Signal in the user's turn                                                  | Skill to invoke         | Why                                                              |
|----------------------------------------------------------------------------|-------------------------|-------------------------------------------------------------------|
| URL pasted (Trello/Linear/Azure/Jira/GitHub Issue/Slack) **or** multi-paragraph brief **or** "vamos planejar / preciso definir como vai funcionar X" | `holoctl-spec-flow`     | External source or design-level scope → intake + decompose pipeline |
| Single sentence with ambiguous kind ("história de…", "bug em…", "epic de…", "RFC pra…") | `holoctl-work-item-router` | Just need to pick `kind` before routing                          |
| Short imperative ("vou refatorar X", "preciso adicionar Y") **and no ticket exists yet**, non-trivial scope                                | `holoctl-ticket-discipline` | Bare announce-then-do — wants a ticket created defensively       |
| Trivial change (typo, formatting, one-liner)                              | none — just do it       | Don't ticket-spam                                                |

**Rules of thumb when two could fire:**
- `spec-flow` always beats `work-item-router` when an external URL was pasted or the user gave a multi-paragraph brief. Don't downgrade to `work-item-router` just because the kind looks obvious.
- `work-item-router` beats `ticket-discipline` when the inferred kind is **not `task`** (story/spec/epic/rfc/bug/incident). Those kinds want the structured flow.
- `ticket-discipline` only fires for `task`-shaped work that the user is about to start without a ticket — its job is to insert the ticket, not to design the work.

## Hard rules (never violate)

- **Never** edit `.holoctl/board/index.json` or `.holoctl/memory/MEMORY.md` by hand. Always via `mcp__holoctl__*` or `hctl <subcommand>`.
- **Never** read `.holoctl/board/tickets/<ID>-*.md` directly — use `mcp__holoctl__board_show` or `hctl board show <ID>`.
- **Never** overwrite hand-edited AI configs (`.cursor/rules/`, hand-edited `CLAUDE.md`, populated `AGENTS.md`). Read for context; don't rewrite.
- If `hctl` returns an error, **read the literal error**, report it, stop. Don't try alternatives silently.
- Don't end with "stop and wait." End with an actionable proposal.
