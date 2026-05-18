import { showToast } from './toast.js';

// ── SSE Live Board Updates ──

export function initSSE() {
  // Either view container anchors SSE.
  const anchor = document.getElementById('kanban')
              || document.getElementById('list-view');
  if (!anchor) return;

  const path = window.location.pathname;
  const match = path.match(/\/project\/([^/]+)\/board(?:\/[^/]+)?$/);
  // Skip on /board/<ticket-id> detail pages (no board there).
  if (!match) return;

  const alias = match[1];
  const source = new EventSource(`/api/project/${alias}/events`);
  let lastData = null;
  let inflight = false;

  source.addEventListener('board-update', async (e) => {
    // First event is the initial state — same as what's already on screen.
    if (lastData === null) {
      lastData = e.data;
      return;
    }
    if (e.data === lastData || inflight) return;
    lastData = e.data;
    inflight = true;
    try {
      const fragmentUrl = (window.__boardFragmentUrl && window.__boardFragmentUrl(alias))
        || `/api/project/${alias}/board-html`;
      const resp = await fetch(fragmentUrl, { cache: 'no-store' });
      if (!resp.ok) return;
      const html = (await resp.text()).trim();
      const wrapper = document.createElement('div');
      wrapper.innerHTML = html;
      const fresh = wrapper.firstElementChild;
      const current = document.getElementById('kanban')
                   || document.getElementById('list-view');
      if (fresh && current) current.replaceWith(fresh);
      // Reapply filter / sort / group state to the freshly-swapped DOM.
      if (window.__reapplyBoardControls) window.__reapplyBoardControls();
      showToast('Board updated');
    } catch (_) {
      // Fall through; next event retries.
    } finally {
      inflight = false;
    }
  });

  source.onerror = () => {
    source.close();
    setTimeout(() => initSSE(), 5000);
  };
}
