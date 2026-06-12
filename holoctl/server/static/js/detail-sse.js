import { showToast } from './toast.js';
import { renderMermaid } from './mermaid-init.js';

// ── SSE Live Detail Updates ──
//
// Counterpart of sse.js for /project/<alias>/board/<ticket-id> pages: the
// board index is the only file the events endpoint watches, but every body
// edit (Board.set_body / update_section) bumps the ticket's index entry, so
// a changed entry is the signal to refetch this page's fragment. This is
// what makes a `kind=spec` ticket a live plan document while an agent
// authors it from chat.

export function initDetailSSE() {
  const content = document.querySelector('[data-detail-page] #detail-content');
  if (!content) return;

  const match = window.location.pathname.match(/\/project\/([^/]+)\/board\/([^/]+)$/);
  if (!match) return;
  const alias = match[1];
  const ticketId = content.getAttribute('data-ticket-id') || match[2];

  const source = new EventSource(`/api/project/${alias}/events`);
  // Serialized index entry of this ticket, as last seen. Comparing the whole
  // entry (not just `updated`) catches status/priority edits inside the same
  // second-granularity timestamp.
  let lastEntry = null;
  let lastUpdated = '';
  let inflight = false;
  let pending = false;

  async function refresh() {
    const target = document.getElementById('detail-content');
    if (!target) return;
    // Don't yank the DOM out from under an active inline edit; the change
    // is picked up on the next event (or the deferred retry below).
    if (target.contains(document.activeElement) && document.activeElement !== document.body) {
      pending = true;
      return;
    }
    if (inflight) return;
    inflight = true;
    try {
      const resp = await fetch(`/api/project/${alias}/board/${ticketId}/detail-html`, { cache: 'no-store' });
      if (!resp.ok) return;
      const html = (await resp.text()).trim();
      target.innerHTML = html;
      // Keep the seed marker fresh so an SSE reconnect doesn't refetch a
      // fragment we already rendered.
      target.setAttribute('data-updated', lastUpdated);
      renderMermaid(target);
      showToast('Plan updated', { reloadOnClick: true });
    } catch {
      // Fall through; next event retries.
    } finally {
      inflight = false;
    }
  }

  source.addEventListener('board-update', (e) => {
    let entry = null;
    try {
      const index = JSON.parse(e.data);
      entry = (index.tickets || []).find((t) => t.id === ticketId) || null;
    } catch {
      return;
    }
    if (!entry) {
      // Gone from the index — deleted while we were watching.
      if (lastEntry !== null) {
        showToast('Ticket deleted', { reloadOnClick: true });
        source.close();
      }
      return;
    }
    const serialized = JSON.stringify(entry);
    lastUpdated = entry.updated || '';
    if (lastEntry === null) {
      lastEntry = serialized;
      // First event mirrors what's already on screen — unless the ticket
      // changed in the window between server render and SSE connect.
      const renderedAt = content.getAttribute('data-updated') || '';
      if (!renderedAt || renderedAt === (entry.updated || '')) return;
    } else if (serialized === lastEntry && !pending) {
      return;
    }
    lastEntry = serialized;
    pending = false;
    refresh();
  });

  source.onerror = () => {
    source.close();
    setTimeout(() => initDetailSSE(), 5000);
  };
}
