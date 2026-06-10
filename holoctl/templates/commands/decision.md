---
name: decision
description: "Record a hard-locked ADR in .holoctl/context/decisions/"
arguments: "<one-line summary>"
allowed-tools: [Bash, Read, Write, Glob]
---

# /decision

ADRs are **immutable**. To reverse, create a new ADR that supersedes the original.

## Steps

1. List existing decisions: `Glob .holoctl/context/decisions/*.md`. Skim titles for duplicates — refuse if the same decision exists.
2. Slugify the title (lowercase, dashes, ≤ 40 chars).
3. Create `.holoctl/context/decisions/YYYY-MM-DD-<slug>.md`:

```markdown
---
date: YYYY-MM-DD
title: <one-line summary>
status: accepted
---

## Context

<why this decision was needed — surrounding constraint, what triggered it>

## Decision

<what was decided, concretely>

## Implications

<what changes in practice; rules that follow from this>
```

4. Confirm in one line: `Decision recorded: YYYY-MM-DD-<slug>`.
