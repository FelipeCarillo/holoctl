---
name: holoctl-ticket-discipline
description: |
  Use when the user announces non-trivial work (refactor, feature, bugfix,
  improvement) and no ticket has been created for it yet. Checks if a ticket
  already exists; if not, suggests creating one (or a parallel batch) before
  implementation starts. Tracks work that would otherwise vanish.
---

# Ticket discipline — track non-trivial work before doing it

## When this fires

The user said something that sounds like committed work, but no ticket exists yet:

- "vou refatorar X", "let me clean up Y", "preciso adicionar Z"
- "tenho que arrumar W", "let's fix this", "I'll add support for V"
- "implementa U pra mim", "add a feature that does T"

If the work is **trivial** (typo fix, one-line config change, formatting), skip — don't ticket-spam.

If the work is **non-trivial** (touches code logic, takes more than a few minutes, has acceptance worth verifying), continue.

## Step 1 — Check if a ticket already exists

Search for an open ticket that covers this work:

```
mcp__holoctl__board_list({"status": "doing"})
mcp__holoctl__board_list({"status": "backlog"})
```

Skim titles for overlap with the announced work. If found:
- Tell the user: "There's already PRJ-NNN ({title}) — that's the same thing, right? Moving to `doing`?"
- If yes: `mcp__holoctl__board_move`, hand off to the right agent.

## Step 2 — No existing ticket — pick the right entry

Before creating anything, check the work item kind via `holoctl-work-item-router`:

- **story / spec / epic / rfc** → invoke `/spec` (Spec-Driven flow with discussion + decomposition). Don't shortcut to a single ticket.
- **bug / incident** → invoke `/ticket` with `kind` pre-set.
- **task** → run `holoctl-parallel-evaluator` to decide single vs batch, then call the boardmaster.

For tasks (the common case):

> "I'll create a ticket for this first so we have something to track against. Boardmaster: {request} — candidate {single|batch:N}."

Get the ID back. State it once: "Tracking as PRJ-NNN. Starting now."

For specs/stories/epics, the `/spec` flow takes over and runs its own steps. Don't duplicate work here.

## Step 3 — During the work

- Mark acceptance items via `mcp__holoctl__board_ack` as you verify them.
- Append decision notes via `mcp__holoctl__board_note`.
- **Never edit the `.md` file directly** — `permissions.deny` blocks it.

## Don't

- Don't create tickets retroactively for trivial work.
- Don't ask the user "should I create a ticket?" every time — make the call, announce the decision, proceed. If they don't want one, they'll say so once and you respect it for the rest of the session.
- Don't fall back to creating without checking for duplicates — that's how the board gets polluted.
