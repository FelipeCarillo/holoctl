// ── Project filter (board page) ──

window.__filterProject = function (btn, project) {
  document.querySelectorAll('.scope-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.kanban-card').forEach(card => {
    const cardProjects = (card.getAttribute('data-projects') || '').split(',').filter(Boolean);
    const visible = project === '' || cardProjects.includes(project);
    card.style.display = visible ? '' : 'none';
  });
};
