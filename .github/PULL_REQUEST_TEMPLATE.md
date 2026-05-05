<!--
Thanks for the PR! A few notes before you submit:

- Read CONTRIBUTING.md if you haven't.
- holoctl ships TWO parallel implementations (Node + Python). If your change is behavioral, mirror it in both — or call out below why one side is intentionally untouched.
- Run the smoke test in CONTRIBUTING.md "Smoke test before opening a PR".
-->

## What this changes

<!-- 1-3 sentences. The "what", not the "why" — that goes below. -->

## Why

<!-- The user-facing reason. Link any related issue. -->

Closes #

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behavior change)
- [ ] Docs only
- [ ] Build / CI / chore

## Dual-stack parity

- [ ] Change is in **both** Node (`src/`) and Python (`holoctl/`)
- [ ] Change is **Node-only** (reason: ____)
- [ ] Change is **Python-only** (reason: ____)
- [ ] N/A (docs / CI / config / single-stack file)

## Smoke test

- [ ] Ran the smoke test from CONTRIBUTING.md and it passes
- [ ] Added/updated tests under `tests/` or `src/**/*.test.js`
- [ ] N/A

## Checklist

- [ ] Version bumped in `package.json` + `pyproject.toml` (if releasing)
- [ ] CHANGELOG.md updated (if user-visible change)
- [ ] README / ARCHITECTURE updated (if surface change)
- [ ] No secrets, tokens, or `~/.pypirc` content committed
