Initialize or inspect projctl in the current project directory.

Steps:
1. Run `projctl doctor` to check if `.projctl/` is already initialized in the current directory or any parent.
2. If **not initialized**: run `projctl init`, then `projctl compile --target claude` to generate Claude-specific files.
3. If **already initialized**: run `projctl board ls` to show the current board status, then suggest running `projctl serve` to open the dashboard.

Always show the output of each command to the user.
