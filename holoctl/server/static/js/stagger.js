// ── Stagger animations ──

export function initStagger() {
  document.querySelectorAll('.project-grid > *, .kanban-column > *, .agent-grid > *, .context-list > *').forEach((el, i) => {
    el.style.animationDelay = `${i * 40}ms`;
  });
}
