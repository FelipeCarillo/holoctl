// ── Theme ──

export function initTheme() {
  const saved = localStorage.getItem('holoctl-theme');
  const theme = saved || 'dark';
  document.documentElement.setAttribute('data-theme', theme);
  updateThemeIcons(theme);
}

function updateThemeIcons(theme) {
  document.querySelectorAll('.theme-icon-dark').forEach(el => {
    el.style.display = theme === 'dark' ? 'flex' : 'none';
  });
  document.querySelectorAll('.theme-icon-light').forEach(el => {
    el.style.display = theme === 'light' ? 'flex' : 'none';
  });
}

window.__toggleTheme = function () {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('holoctl-theme', next);
  updateThemeIcons(next);
};
