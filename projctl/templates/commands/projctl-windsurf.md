---
description: Initialize or inspect projctl in the current project directory
---

Steps:
1. Run `projctl doctor` to check if `.projctl/` is already initialized.
2. If not initialized: run `projctl init`, then `projctl compile --target windsurf`.
3. If already initialized: run `projctl board ls` and show the board status.

Show all command output to the user.
