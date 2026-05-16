---
name: holoctl-spec-flow
description: |
  Use when the user pastes content from an external board (Trello/Linear/
  Azure DevOps/Jira/GitHub/Slack), or shares a multi-paragraph request that
  needs structuring before coding. Drives the Spec-Driven Development flow:
  intake → discuss → spec → decompose → execute. Companion to the `/spec`
  slash command and the `holoctl-work-item-router` skill.
---

# Spec-Driven Development flow

This is the canonical pipeline for "user has an idea or external board card → holoctl makes it executable":

```
External source (Trello/Linear/Azure/Jira/GitHub/Slack/manual)
     │
     ▼  user pastes content (or future MCP fetches it)
   /spec  ← entry point
     │
     ▼
 1. Intake — detect source_provider/ref/url/label
 2. Discuss — refine scope, acceptance, files, edge cases (one batched question)
 3. Materialize spec — board_create({kind:'spec', source_*, acceptance, context, ...})
 4. Decompose — parallel-evaluator + boardmaster + board_batch({shared:{parent:SPEC_ID, ...}})
 5. Execute — activate developer/reviewer subagents on the first child task
```

## When to trigger

Fires automatically (auto-trigger via description) when the user:

- Pastes a card-like block (with terms like "as a user", "I want", "story:", "acceptance:") OR
- Pastes a URL from a known external board (see `holoctl-work-item-router` for patterns) OR
- Shares a multi-paragraph request describing work that touches multiple files / modules OR
- Explicitly says "vou trabalhar nessa" / "tem esse card aqui" / "vamos planejar essa feature"

Doesn't fire for:

- One-line bug reports → that's a single ticket (`/ticket` or `kind=bug`)
- Already-decomposed work where tasks are explicit → that's batch `/ticket`

## Step-by-step

### 1. Intake

Read what the user pasted. Extract:

- **source_provider** — see `holoctl-work-item-router` URL patterns.
- **source_ref** / **source_url** / **source_label** when present.
- **Raw request body** — the prose itself.

If a URL is given but no body, ask the user to paste the body (until the provider has an MCP we can fetch from).

### 2. Discuss

Reach agreement on:

| Element            | Required?  | Notes                                                     |
|---------------------|-----------|-----------------------------------------------------------|
| Scope               | yes       | What's in / what's out                                    |
| Acceptance criteria | yes       | 3-7 verifiable items                                       |
| Files / modules     | recommended | `Glob` to confirm existence                              |
| Edge cases          | optional  | Surface the non-obvious ones                              |
| Risks / unknowns    | optional  | Flag what could derail                                    |
| Decomposition hint  | optional  | If user already mentioned split, capture                  |

**One batched question only.** Pre-populate from the source content; ask only for what you genuinely cannot infer.

### 3. Materialize the spec

```
mcp__holoctl__board_create({
  "title": "<spec title — verb + object, derived from source>",
  "kind": "spec",
  "agent": "architect",
  "priority": "<inferred or default p1>",
  "acceptance": ["<criterion 1>", ...],
  "context": "<consolidated discussion>",
  "out_of_scope": "<what NOT to do>",
  "files": ["<file 1>", ...],
  "source_provider": "<provider>",
  "source_ref": "<ref>",
  "source_url": "<url>",
  "source_label": "<label>"
})
```

Save the returned ID as `SPEC_ID`.

### 4. Decompose

Run `holoctl-parallel-evaluator` against the spec body. It returns a candidate partition (or "single" if monolithic).

If single: nothing else to create; the spec itself is the unit of work.

If batch: delegate to boardmaster:

```
mcp__holoctl__board_batch({
  "shared": {
    "parent": SPEC_ID,
    "kind": "task",
    "source_provider": "<inherited>",
    "source_ref": "<inherited>",
    "source_url": "<inherited>",
    "source_label": "<inherited>",
    "tags": [`spec:${SPEC_ID}`]
  },
  "tickets": [
    { "title": "...", "agent": "developer", "priority": "p1",
      "files": ["..."], "acceptance": ["..."] },
    ...
  ]
})
```

The CLI rejects if files overlap. If rejected, refine and retry (max 2).

### 5. Execute

Confirm what was created (the `/spec` command spec details this). Then propose **one** next action:

- If a `developer` persona is active and there's a first child task → "Activate developer on `<first-task-id>`?"
- If no `developer` active → "Activate developer first: `mcp__holoctl__agent_add({\"name\":\"developer\"})`?"

You don't run the execution yourself. You set up the runway; the user (or subagent dispatch) does the takeoff.

## Round-trip back to the source

When all child tasks of a spec are `done`, the spec can be moved to `done`. If the spec has `source_*`, surface that fact:

> "Spec `<SPEC_ID>` complete. Source: `<provider>:<ref>` — remember to close the original card on `<provider>`."

(Future MCP integration: the closing could be automated via the provider's MCP. Today: it's a reminder.)

## Don't

- Don't create the spec without consolidating the discussion into `context`. The spec body is the durable record of the decision; the chat history will be cleared.
- Don't skip step 4 (decomposition) for spec-kind items. If you really can't decompose, the item should be `kind=task`, not `kind=spec`.
- Don't propagate `source_*` to tasks created later (after the initial batch) unless the user explicitly asks — those are follow-ups, often unrelated.
