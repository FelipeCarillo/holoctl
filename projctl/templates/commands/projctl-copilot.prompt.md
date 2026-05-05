---
mode: agent
description: Initialize or inspect projctl in the current project directory
---

Steps:
1. Run `projctl doctor` to check if `.projctl/` is already initialized in the current directory.
2. If **not initialized**: run `projctl init`, then `projctl compile --target copilot` to generate Copilot-specific files.
3. If **already initialized**: run `projctl board ls` to show the current board status, then suggest running `projctl serve` to open the dashboard.

Show all command output to the user.
