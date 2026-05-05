Initialize or inspect holoctl in the current project directory.

Steps:
1. Run `holoctl doctor` to check if `.holoctl/` is already initialized in the current directory or any parent.
2. If **not initialized**: run `holoctl init`, then `holoctl compile --target cursor` to generate Cursor-specific files.
3. If **already initialized**: run `holoctl board ls` to show the current board status, then suggest running `holoctl serve` to open the dashboard.

Always show the output of each command to the user.
