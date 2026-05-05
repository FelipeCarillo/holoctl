---
mode: agent
description: Initialize or inspect holoctl in the current project directory
---

Steps:
1. Run `holoctl doctor` to check if `.holoctl/` is already initialized in the current directory.
2. If **not initialized**: run `holoctl init`, then `holoctl compile --target copilot` to generate Copilot-specific files.
3. If **already initialized**: run `holoctl board ls` to show the current board status, then suggest running `holoctl serve` to open the dashboard.

Show all command output to the user.
