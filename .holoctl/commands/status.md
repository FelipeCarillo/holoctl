---
name: status
description: "Quick project status overview"
arguments: ""
---

# /status — Project status overview

1. Run `holoctl board stat` for ticket counts.
2. Run `holoctl board ls --status doing` for active work.
3. Run `holoctl board ls --status backlog p0` and `holoctl board ls --status backlog p1` for next priorities.
4. For tickets with dependencies, use `holoctl board get <ID>` to check if deps are done.

## Output format

```
## TestProject — Status {{date}}

**Board:** X backlog · Y doing · Z review · W done
**Doing now:** {{list of ID title (agent)}}
**Next (p1):** {{top 3 backlog p1}}
**Blocked:** {{tickets with undone deps, or "none"}}
```

Maximum 10 lines. No prose.
