Initialize or inspect projhub in the current project directory.

Steps:
1. Run `projhub doctor` to check if `.projhub/` is already initialized in the current directory or any parent.
2. If **not initialized**: run `projhub init`, then `projhub compile --target cursor` to generate Cursor-specific files.
3. If **already initialized**: run `projhub board ls` to show the current board status, then suggest running `projhub serve` to open the dashboard.

Always show the output of each command to the user.
