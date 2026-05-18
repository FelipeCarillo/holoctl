---
name: holoctl-persona-suggester
description: |
  Use when the user describes work, or recent file edits touch paths, that
  aren't owned by any active persona. Detects emerging specialization signals
  (a new file type appearing repeatedly, a directory pattern unique to a
  specialty, a request mentioning a domain outside boardmaster/developer/
  reviewer/architect/researcher scope) and surfaces a suggestion: either
  activate an existing library persona, or invoke /agent-new to design a
  brand-new persona tailored to this project.
---

# Persona suggester — fill the gap reactively

Holoctl shipped with a 5-persona library (boardmaster, developer, reviewer, architect, researcher) plus 4 specialist defaults (dba, devops, security-auditor, tech-writer) plus an agent-designer for generating new ones. This skill watches for **gaps**: when the work in front of the user doesn't fit any active persona, surface a path forward.

## When this skill fires

The skill's description tells Claude Code to auto-activate when:

- The user says something like "preciso revisar segurança", "vou mexer no banco", "vamos provisionar infra", "documentar o módulo X" — domain language outside active personas' scope.
- Recent edits (5+ in window) touch globs no active persona owns (e.g. `**/*.sql` and no `dba` active; `terraform/**` and no `devops` active; `**/*.tsx` heavily and `developer` is the only frontend touch).
- The user explicitly asks "qual persona usa pra isso?" / "tem alguma persona pra X?".

**Don't fire** when:
- The work fits an active persona cleanly. Don't suggest splitting just because.
- The user already declined a similar suggestion this session (check `.holoctl/.cache/persona-suggestions.json` if it exists).

## Workflow

### Step 1 — Inventory

```
mcp__holoctl__agent_list_available()
```

Returns `{active: [...], library: [...]}`. You now know what's available.

For each active persona, read its `paths:` (use `mcp__holoctl__agent_list_available` or `Read .claude/agents/<name>.md`).

### Step 2 — Identify the gap

What domain/path is the user working on or asking about?

- If you can name a glob pattern (e.g. `**/*.sql`, `**/k8s/**`, `**/.github/workflows/**`), check whether any active persona's `paths:` covers it.
- If you can name a domain (e.g. "security review", "schema migration", "deploy pipeline"), check whether any active persona's `description:` covers it.

If covered → don't fire.

### Step 3 — Match against library

```
mcp__holoctl__agent_list_available()  // includes library:
```

For each persona in `library` (not yet active), inspect its `description:` and `paths:` (read via `Read` from `holoctl/templates/agents/` if needed — but the description from `agent_list_available` is usually enough). Does it fit the gap?

- **Yes** → propose activation:
  > "Detectei `<signal>` que nenhuma persona ativa cobre. A library tem `<name>` — descrição: `<desc>`. Quer ativar? (`mcp__holoctl__agent_add({\"name\":\"<name>\"})`)"

- **No** → propose creation via `/agent-new`:
  > "Detectei `<signal>` que nem as personas ativas nem a library cobrem. Posso desenhar uma persona específica via `/agent-new <suggested-name>`. Sugerido: `<name>` — sobre `<what>`. Quer?"

### Step 4 — Suggest only once per gap per session

Cache in `.holoctl/.cache/persona-suggestions.json`:

```json
{
  "<gap-signature>": {
    "first_seen": "<ISO>",
    "declined": false,
    "suggestion": "<name>",
    "action": "activate|create"
  }
}
```

`gap-signature` = a normalized form of the signal (e.g. `"path:**/*.sql"`, `"domain:security-review"`).

If a gap has been suggested already this session:
- `declined: true` → don't surface again.
- `declined: false` and recent (< 1h) → don't surface again.
- Older → surface again (user may have changed mind).

## Naming conventions for `/agent-new` proposals

When the library doesn't have a match, propose a name that:

- Is kebab-case.
- Reflects the actual domain (not generic): `embedded-firmware-engineer`, not `general-engineer`.
- Doesn't collide with active or library names.

Domain → name suggestions (heuristic, not exhaustive):

| Signal                                          | Suggested name             |
|-------------------------------------------------|----------------------------|
| Heavy `**/*.tsx`, `**/components/**`            | `frontend-developer`       |
| Heavy `src/api/**`, FastAPI/Express patterns    | `backend-developer`        |
| `embedded/**`, `firmware/**`, `no_std` Rust     | `embedded-engineer`        |
| `**/notebooks/**`, `*.ipynb`, ML model files    | `ml-engineer`              |
| `**/data/**`, ETL DAGs, Airflow                 | `data-engineer`            |
| Heavy mobile (`ios/`, `android/`, `.swift`, `.kt`) | `mobile-developer`      |
| `qa/**`, `e2e/**`, test framework configs       | `qa-engineer`              |

Don't propose names from this table without confirming the signal is real (`Glob` first).

## Don't

- Don't suggest a persona for one-off mentions. Threshold: 3-5 evidence points (file edits, prompt mentions) before firing.
- Don't suggest activating a persona that's already active. Check `active` from `agent_list_available` first.
- Don't ask twice in the same session unless the signal materially changed. Cache the suggestion.
- Don't propose AI-generating a persona for a domain the library already covers. Library first.
- Don't run `/agent-new` yourself — surface the proposal, let the user invoke (or the orchestrator invokes when user says yes).
