// ── Project filter (board page) ──
//
// Filters kanban cards by sub-project. Triggered by clicking a `.scope-btn`
// carrying `data-filter-project="<name>"` (empty string = "all"). Migrated
// from the old `window.__filterProject` global to delegated handling so a
// future CSP can drop unsafe-inline.

export function initProjectFilter() {
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-filter-project]');
    if (!btn) return;
    const project = btn.getAttribute('data-filter-project') || '';
    document.querySelectorAll('.scope-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.kanban-card').forEach(card => {
      const cardProjects = (card.getAttribute('data-projects') || '').split(',').filter(Boolean);
      const visible = project === '' || cardProjects.includes(project);
      card.style.display = visible ? '' : 'none';
    });
  });
}
