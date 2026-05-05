---
name: decision
description: "Record a hard-locked decision"
arguments: "<description>"
---

# /decision — Record a decision

1. Read `.holoctl/context/decisions/` to check for duplicates.
2. Create a new file `.holoctl/context/decisions/YYYY-MM-DD-<slug>.md` with:

```markdown
---
date: YYYY-MM-DD
title: One-line summary
status: accepted
---

## Context

Why this decision was needed.

## Decision

What was decided.

## Implications

What changes in practice.
```

3. Confirm: "Decision recorded: {title}."

Decisions are **immutable** by default. To reverse, create a new decision that supersedes the original.
