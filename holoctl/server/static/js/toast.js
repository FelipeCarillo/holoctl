// ── Toast Notifications ──

import { el } from './dom.js';

/**
 * Show a transient toast.
 * @param {string} message
 * @param {{reloadOnClick?: boolean}} [opts]  when true, clicking the toast
 *        body reloads the page (used only by the SSE "Board updated" toast).
 */
export function showToast(message, { reloadOnClick = false } = {}) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.setAttribute('role', 'status');
    container.setAttribute('aria-live', 'polite');
    container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(container);
  }

  const dot = el('span', { class: 'toast-dot' });
  // Message is set via textContent (createElement path) — no HTML injection.
  const msg = el('span', {}, [String(message)]);
  const dismiss = el('button', { class: 'toast-dismiss', 'aria-label': 'Dismiss' }, ['×']);
  const toast = el('div', { class: 'toast' }, [dot, msg, dismiss]);

  dismiss.addEventListener('click', (e) => {
    e.stopPropagation();
    toast.remove();
  });

  if (reloadOnClick) {
    toast.addEventListener('click', (e) => {
      if (e.target.closest('.toast-dismiss')) return;
      window.location.reload();
    });
  } else {
    toast.style.cursor = 'default';
  }

  container.appendChild(toast);

  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, 8000);
}
