Onboard, configure or inspect projhub for the current project.

**This command requires interaction.** You will pause and ask the user for confirmation at each gate. Never write context files or register repos without explicit user approval — these decisions stick around and a wrong guess wastes time later.

# Step 1 — Detect state

Run `projhub doctor`.

- **Errors with "No .projhub/ found"** → uninitialized. Go to Step 2.
- **Returns checks** → already initialized. Go to Step 5 (Inspect mode).

# Step 2 — Confirm before initializing

ASK the user:

> "Quero criar o `.projhub/` aqui. Qual o **nome do projeto** e o **prefix dos tickets** (ex: `MP` → `MP-001`)? Se quiser, posso inferir do nome do diretório."

Wait for their answer. Then run:

```bash
projhub init --name "<name>" --prefix "<PREFIX>"
```

(Or `projhub init` with no flags if they said "infer".)

This auto-runs `projhub compile --target claude` and `projhub setup-global`. Show the output.

# Step 3 — Discover project structure (read-only)

Read in parallel — **don't write yet**:
- `README.md` (and `README.pt-br.md` if present)
- Package files: `package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod` / `pom.xml` / `Gemfile`
- Top-level directories (use `Glob` with `*/` pattern). Note which look like sub-projects (have their own package file or `.git`).
- Existing AI instructions: `CLAUDE.md`, `.cursor/rules/*`, `.windsurfrules`, `.github/copilot-instructions.md`, `AGENTS.md`. **Read for context only — never overwrite.**
- Lint/format configs: `.eslintrc*`, `.prettierrc*`, `ruff.toml`, `pyproject.toml [tool.ruff]`, `.editorconfig`

# Step 4 — Configure with confirmation gates

For each of the 4 sub-steps below, **propose** the content, **show it** to the user, **wait for approval or edits**, then write. Don't batch — one at a time so the user can correct course.

## 4.1 — Sub-repos

If you found multiple sub-projects in Step 3, list them and ASK:

> "Encontrei estes sub-projetos: `backend/`, `frontend/`, `mobile/`. Quer que eu registre todos como repos? Pode escolher um subset, ou adicionar uma descrição customizada para cada um."

For each one the user approves:
```bash
projhub repo add ./<path> --name <name> --description "<one-line>"
```

If they say "single project", skip.

## 4.2 — `objective.md`

Draft the content based on what you read. Show the proposed text and ASK:

> "Proposta para `objective.md`:
>
> ```
> <show full draft>
> ```
>
> Aprova, edita, ou prefere reescrever?"

Then write the file with `Edit` tool (it already exists from `init`).

## 4.3 — `architecture.md`

Same flow: draft → show → confirm → write. Sections: Tech stack, Structure, Key patterns, Boundaries. Use only patterns visible in the code; mark unclear items as `(TBD with team)`.

## 4.4 — `conventions.md`

Same flow. Derive from real configs. Mark dimensions without config as `(not enforced)`. Don't invent style rules.

## 4.5 — `instructions.md`

Same flow. Fill **Identity** (1-2 sentences) and **Folder map** (real top-level dirs). Leave **Decisions** empty unless the user dictates one now.

# Step 4.6 — Recompile

After all the above, run:
```bash
projhub compile --target claude
```

This regenerates `CLAUDE.md` and `.claude/commands/*` from the now-populated `.projhub/`.

# Step 5 — Inspect mode (when already initialized)

1. `projhub board stat`
2. `projhub board ls --status doing`
3. `projhub repo list`
4. `projhub agent list`
5. Suggest the next concrete action (e.g. "no tickets yet — type `/ticket <title>` to create one", or "TST-003 has been in `doing` for 6 days — review or unblock?").

# Step 6 — Final report

End with:
- ✅ what was set up (or what's already configured)
- 🌐 dashboard URL: `http://127.0.0.1:4242` — run `projhub serve` to start
- 🎯 single-line suggested next action

# Hard rules

- **Always show command output** to the user — they should see what happened.
- **Never write context files without confirmation** — the user often has tribal knowledge that won't be in the README.
- **Never register repos silently** — wrong path or name is a pain to clean up.
- **Never overwrite an existing `CLAUDE.md`** — read it as context, but recompile only via `projhub compile`.
- **If something fails** (e.g. `projhub init` errors because the directory already has `.projhub/`), report it and ask before retrying.
