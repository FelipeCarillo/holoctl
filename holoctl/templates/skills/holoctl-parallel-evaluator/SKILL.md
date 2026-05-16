---
name: holoctl-parallel-evaluator
description: |
  Use when the user describes work that touches multiple files or modules,
  BEFORE committing to a single-ticket creation. Evaluates parallelization
  potential and proposes a batch decomposition if independent file sets
  exist. Hands the candidate decomposition to the boardmaster.
---

# Parallel evaluator — decide single vs batch before creating tickets

Run this evaluation any time you're about to call the boardmaster (`/ticket`, or implicitly when the user announces work). The boardmaster will repeat the check, but doing it here means the decomposition arrives **pre-formed** rather than the boardmaster having to derive it from scratch.

## Decision

Ask yourself: *can this work split into N pieces that touch **disjoint files** and have **independent acceptance** (no piece's DoD references another's output)?*

- **Yes (N ≥ 2)** → propose batch with the file partition.
- **No** → single ticket.
- **Unsure** → present both options to the user with the candidate decomposition pre-formed. Never push the decomposition work back.

## Signals for batch

- Pedido has factored conjunctions: "add X **and** Y", "implement A, B, **and** C", "fix bugs in foo **and** bar".
- Modular structure exists: separate packages/layers/modules.
- DoD naturally fragments into implement / test / document, on different files.

## Signals against batch (=> single)

- Refactor that rewrites a structure (renaming across the codebase, lifting an abstraction).
- Acceptance only makes sense if all pieces snap together (cross-cutting changes).
- Pedido is explicitly "small change", "quick fix", "one-liner".
- Fewer than 3 identifiable files to touch.

## How to present

If you're calling the boardmaster:

```
Boardmaster: decompose request "{user_request}" into single OR batch.
Candidate batch (if applicable):
  - {ticket-1-title} (files: {files-1})
  - {ticket-2-title} (files: {files-2})
  - {ticket-3-title} (files: {files-3})
User has NOT been asked yet; if you find the partition non-obvious, ask
the user with this candidate vs single side-by-side, then proceed.
```

If you're talking directly to the user:

> "This work can split into 3 parallel tickets:
> - **JWT signing** (`src/auth/jwt.py`)
> - **Auth middleware** (`src/middleware/auth.py`)
> - **Integration tests** (`tests/test_auth.py`)
>
> Or create as 1 single ticket. Which?"

Never invent files. Use what the codebase actually has (or what the request explicitly names). If you can't enumerate the files yet, default to single — batch without files declared will be rejected by the CLI.
