---
name: holoctl-work-item-router
description: |
  Use when the user describes work to be tracked and the work kind isn't
  obvious. Infers whether it's a task, story, bug, spec, epic, or incident
  from the language used, then routes to the right entry point (`/ticket`,
  `/spec`, or direct boardmaster call) with the correct `kind` pre-set.
---

# Work item kind router

Holoctl supports a single work item type with a `kind` field. Choosing the right kind makes filtering, hierarchy, and downstream agents work correctly. This skill maps natural language to `kind`.

## Cheat sheet

| User language signals                                                                        | kind        | Default agent | Typical lifecycle               |
|----------------------------------------------------------------------------------------------|-------------|---------------|----------------------------------|
| "como usuário X eu quero Y porque Z" / "feature para…" / "user story:"                       | `story`     | architect     | groom → impl → delivered         |
| "não funciona", "tá com bug", "deveria X mas faz Y", "regressão", error/stack-trace pasted    | `bug`       | developer     | repro → fix → verified           |
| "preciso definir como vai funcionar X", "spec do…", "documento de design"                    | `spec`      | architect     | draft → reviewing → approved     |
| "esse trabalho enorme tem várias frentes", several stories rolling up                        | `epic`      | architect     | scoping → in-progress → delivered|
| RFC formal proposal, breaking change discussion, "preciso de um RFC pra…"                    | `rfc`       | architect     | draft → review → accepted        |
| "tá fora do ar", "produção quebrada", oncall page, P0 alarm                                  | `incident`  | developer     | triage → mitigated → postmortem  |
| concrete small change, "preciso adicionar X" with clear scope                                | `task`      | developer     | backlog → doing → review → done  |

When unsure between two kinds, pick the broader/safer one. **Story over task** when story-sounding language is used; **spec over story** when the description is more about "how should we build this" than "what should it do".

## Routing decisions

- **kind = story / spec / epic / rfc** → invoke `/spec` (the structured Spec-Driven flow). These warrant the discuss-then-decompose pattern; don't shortcut to a task.
- **kind = bug / incident** → invoke `/ticket` with `kind` pre-set; boardmaster creates a single ticket with `agent=developer` and any reproduction steps in `context`.
- **kind = task** → invoke `/ticket` as normal. Triggers the parallel-evaluator on the way (multi-file work may split).

## External source detection

If the user pastes a URL or refs a card, **delegate URL parsing + MCP fetch to the `holoctl-provider-mcp` skill** — it consults the configured provider catalog (`mcp__holoctl__config_show()` → `providers`), parses the URL, probes the provider's MCP tool, and either fetches the card body directly or falls back to paste with `source_*` pre-filled.

Don't reimplement URL parsing here — the catalog is the source of truth and the user may have added custom providers (internal boards) via `hctl provider add` that aren't in any hardcoded list.

When a source is set on a spec/story/epic, the boardmaster propagates it to all child tasks via `shared.source_*` in `board_batch`. Children inherit; round-trip traceability preserved.

## Don't

- Don't ask the user "what kind should this be?" — infer and proceed. They redirect if wrong.
- Don't create a `spec` for a tiny one-file change — that's just a `task`.
- Don't conflate `parent` (containment) with `depends` (sequencing). A child of a spec has `parent: SPEC-ID`. A task that has to run after another has `depends: [<other-id>]`.
