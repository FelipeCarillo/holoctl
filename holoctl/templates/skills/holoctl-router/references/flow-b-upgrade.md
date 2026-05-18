# Flow B — Upgrade after `hctl` was updated

`hctl doctor` returned `holoctl: outdated`. The installed `hctl` is newer than the workspace's recorded `holoctlVersion`.

## Steps

1. `hctl upgrade --check` — show the CHANGELOG slice to the user.
2. Ask: **"Apply?"** (one-line question, wait for confirmation).
3. If yes: `hctl upgrade`. Show the output. The upgrade applies migrations + recompiles.
4. After upgrade succeeds, run `hctl boot` and react like Flow C Step 6 — propose next action based on what `boot` shows.

If `hctl upgrade --check` shows breaking changes, surface them prominently before asking "Apply?".
