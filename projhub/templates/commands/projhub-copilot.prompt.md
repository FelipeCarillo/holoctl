---
mode: agent
description: Initialize or inspect projhub in the current project directory
---

Steps:
1. Run `projhub doctor` to check if `.projhub/` is already initialized in the current directory.
2. If **not initialized**: run `projhub init`, then `projhub compile --target copilot` to generate Copilot-specific files.
3. If **already initialized**: run `projhub board ls` to show the current board status, then suggest running `projhub serve` to open the dashboard.

Show all command output to the user.
