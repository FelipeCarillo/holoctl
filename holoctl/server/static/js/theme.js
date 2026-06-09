// ── Theme ──

function preferredTheme() {
  const saved = localStorage.getItem('holoctl-theme');
  if (saved) return saved;
  // No explicit override → honour the OS preference.
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

export function initTheme() {
  const theme = preferredTheme();
  document.documentElement.setAttribute('data-theme', theme);
  updateThemeIcons(theme);

  // Delegated toggle handler (replaces inline onclick="__toggleTheme()" so a
  // future CSP can drop unsafe-inline).
  document.addEventListener('click', (e) => {
    if (e.target.closest('[data-action="toggle-theme"]')) {
      toggleTheme();
    }
  });
}

function updateThemeIcons(theme) {
  document.querySelectorAll('.theme-icon-dark').forEach(el => {
    el.style.display = theme === 'dark' ? 'flex' : 'none';
  });
  document.querySelectorAll('.theme-icon-light').forEach(el => {
    el.style.display = theme === 'light' ? 'flex' : 'none';
  });
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('holoctl-theme', next);
  updateThemeIcons(next);
}
