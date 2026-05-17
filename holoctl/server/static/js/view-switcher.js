// ── View switcher: kanban ↔ list ──

export function currentView() {
  const panel = document.getElementById('board-controls');
  if (panel && panel.dataset.currentView) return panel.dataset.currentView;
  const url = new URL(window.location.href);
  return url.searchParams.get('view') || 'kanban';
}

export function initViewSwitcher() {
  const switcher = document.querySelector('.view-switcher');
  if (!switcher) return;
  switcher.addEventListener('click', (e) => {
    const tab = e.target.closest('.view-tab');
    if (!tab || tab.disabled || tab.classList.contains('active')) return;
    const view = tab.getAttribute('data-view');
    if (!view) return;
    const url = new URL(window.location.href);
    url.searchParams.set('view', view);
    // Full navigation — easiest way to swap server-rendered structure +
    // re-init JS without a partial-update juggling act.
    window.location.href = url.toString();
  });
}
