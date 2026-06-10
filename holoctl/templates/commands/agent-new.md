---
name: agent-new
description: "Design a brand-new specialized persona tailored to this project's stack. Delegates to the agent-designer persona, which reads the repo and drafts a schema-correct .md."
arguments: "<name> [<one-line-description>]"
allowed-tools: [Bash, Read, Glob, Grep, Write, mcp__holoctl__agent_list_available, mcp__holoctl__agent_add, mcp__holoctl__agent_create]
---

# /agent-new

Creates a new specialized persona that doesn't exist in the library — tailored to this specific project.

## Step 1 — Collect inputs (one batched question if missing)

- **`name`** (from argument): kebab-case, no spaces.
- **`description`** (one line): what this persona does and when it should fire.
- **`signals`** (optional): paths/dirs the persona will own (else agent-designer discovers).

## Step 2 — Library check

`mcp__holoctl__agent_list_available()`. If `name` is already in the library, **don't draft a new one** — offer to activate it:

> "`<name>` already exists in the library. Activate via `{{commands.boardCliBin}} agent add <name>` (or `mcp__holoctl__agent_add`)?"

Otherwise proceed.

## Step 3 — Activate `agent-designer` if needed

Check the response of `agent_list_available`:
- If `agent-designer` is in `library` but not `active`: activate first via `mcp__holoctl__agent_add({"name": "agent-designer"})`.
- If already active: continue.

## Step 4 — Delegate the draft

Invoke `agent-designer` (via Claude Code's subagent / Task tool) with this brief:

```
Design a persona named "<name>".
Description: "<one-line description>".
Signals (if provided): <paths>.

Discover the repo first (README, package files, top-level dirs).
Cross-check against active personas (via mcp__holoctl__agent_list_available).
Produce the full .md body — frontmatter + sections — per the schema in your own prompt.
Return ONLY the body, no preamble.
```

The agent-designer returns the persona body.

## Step 5 — Save as draft, preview, confirm

Write the returned body to `.holoctl/agents/<name>.draft.md` (note the `.draft` suffix — not active yet).

Show the user a preview:
- Frontmatter summary: `model`, `tools`, `paths` (3-5 globs).
- Identity paragraph + Scope bullets.

Ask: **"Apply this persona? (y / edit / cancel)"**

## Step 6 — Activate

On `y`:
1. Read the `.draft.md`.
2. Call `mcp__holoctl__agent_create({"name": "<name>", "body": <full content>})`. This validates frontmatter and writes `.holoctl/agents/<name>.md` (without the `.draft.`).
3. Delete the `.draft.md`.
4. Run `{{commands.boardCliBin}} compile --target claude` to emit `.claude/agents/<name>.md`.
5. Report: `Activated <name> (model=<model>, paths=<N globs>).`

On `edit`: offer to open the `.draft.md` for hand-editing; user can run `/agent-new <name>` again to finalize.

On `cancel`: delete the `.draft.md`. Report nothing changed.
