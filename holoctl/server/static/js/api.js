// ── Shared board API helpers ──
//
// Centralises the project-alias lookup and the ticket move/patch fetches that
// were previously duplicated (and called cross-module without import) across
// card-menu.js, inline-add.js, inline-edit.js and list-selection.js.

/** Extract the project alias from the current URL, or null when off-project. */
export function projectAlias() {
  const m = window.location.pathname.match(/\/project\/([^/]+)\//);
  return m ? m[1] : null;
}

function projectAliasOrThrow() {
  const a = projectAlias();
  if (!a) throw new Error('No project alias on this page');
  return a;
}

/** Move a ticket to a new status (server recounts columns). */
export async function moveTicket(id, status) {
  const alias = projectAliasOrThrow();
  const resp = await fetch(`/api/project/${encodeURIComponent(alias)}/tickets/${encodeURIComponent(id)}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `move failed (${resp.status})`);
  }
  return resp.json();
}

/**
 * Move many tickets to one status in a single request.
 *
 * Resolves with the server's batch result —
 * `{moved: [...], errors: [{id, error}, ...], count}` — which is 200 even on
 * partial failure. Throws an Error with `.status` set to the HTTP status on
 * request-level failure (404/405 → older server without the endpoint).
 */
export async function bulkMoveTickets(ids, status) {
  const alias = projectAliasOrThrow();
  const resp = await fetch(`/api/project/${encodeURIComponent(alias)}/tickets/bulk-move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, status }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    const err = new Error(data.detail || `bulk move failed (${resp.status})`);
    err.status = resp.status;
    throw err;
  }
  return resp.json();
}

/** Patch a single ticket field (priority / sprint / tags / agent / projects). */
export async function patchTicket(id, field, value) {
  const alias = projectAliasOrThrow();
  const resp = await fetch(`/api/project/${encodeURIComponent(alias)}/tickets/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field, value }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `patch failed (${resp.status})`);
  }
  return resp.json();
}
