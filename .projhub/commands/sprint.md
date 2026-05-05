---
name: sprint
description: "Plan or review a sprint"
arguments: "[plan|review]"
---

# /sprint — Sprint management

## No argument (current sprint)

1. Run `projctl board ls --status doing` and `projctl board ls --status review` for active tickets.
2. For each sprint found, run `projctl board ls --sprint <name>`.
3. Show progress: X/Y completed (Z%).
4. Highlight blocked tickets.

## Plan

1. Run `projctl board ls --status backlog` to list the backlog.
2. Prioritize by: dependencies (done first), priority (p0 > p1 > p2 > p3), capacity.
3. Suggest selection with justification and sprint name.
4. After approval: `projctl board set <ID> sprint <sprint-name>` for each ticket.

## Review

1. Run `projctl board ls --sprint <current>` to list all sprint tickets.
2. Report: completed (with dates), left behind (with reasons), velocity.
3. Suggest adjustments for next sprint.
