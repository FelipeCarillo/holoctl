const SVG = {
  home: '<svg viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
  agents: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4M4.22 4.22l2.83 2.83m9.9 9.9l2.83 2.83M1 12h4m14 0h4M4.22 19.78l2.83-2.83m9.9-9.9l2.83-2.83"/></svg>',
  activity: '<svg viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  folder: '<svg viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  sun: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
  moon: '<svg viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
  board: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>',
  agentTab: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4M4.22 4.22l2.83 2.83m9.9 9.9l2.83 2.83M1 12h4m14 0h4M4.22 19.78l2.83-2.83m9.9-9.9l2.83-2.83"/></svg>',
  command: '<svg viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
  context: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
};

export function layout(title, bodyContent, { sidebar, topbar } = {}) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>${esc(title)} — holoctl</title>
<script>
(function(){var t=localStorage.getItem('holoctl-theme')||'dark';document.documentElement.setAttribute('data-theme',t)})();
</script>
<link rel="stylesheet" href="/static/holoctl.css"/>
</head>
<body>
<div class="app">
  ${sidebar || ''}
  <div class="main">
    ${topbar || ''}
    ${bodyContent}
  </div>
</div>
<script src="/static/holoctl-ui.js"></script>
</body>
</html>`;
}

export function sidebarHtml(projects, currentAlias, currentTab) {
  const projectLinks = projects.map(p => {
    const active = p.alias === currentAlias ? ' active' : '';
    const shortPath = shortenPath(p.path);
    return `<div>
      <a class="nav-item${active}" href="/project/${esc(p.alias)}/board">
        <span class="nav-icon">${SVG.folder}</span>
        ${esc(p.name || p.alias)}
        ${p.ticketCount !== undefined ? `<span class="badge">${p.ticketCount}</span>` : ''}
      </a>
      <span class="project-path" title="${esc(p.path)}">${esc(shortPath)}</span>
    </div>`;
  }).join('\n');

  return `<aside class="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-brand">
        <div class="logo">P</div>
        holoctl
      </div>
      <button class="theme-toggle" onclick="window.__toggleTheme()" title="Toggle theme" aria-label="Toggle theme">
        <span class="theme-icon-dark">${SVG.sun}</span>
        <span class="theme-icon-light">${SVG.moon}</span>
      </button>
    </div>
    <nav class="sidebar-nav">
      <div class="nav-group">
        <div class="nav-group-label">Navigation</div>
        <a class="nav-item${!currentAlias && currentTab !== 'agents-global' && currentTab !== 'activity-global' ? ' active' : ''}" href="/">
          <span class="nav-icon">${SVG.home}</span> Home
        </a>
        <a class="nav-item${currentTab === 'agents-global' ? ' active' : ''}" href="/agents">
          <span class="nav-icon">${SVG.agents}</span> Agent Registry
        </a>
        <a class="nav-item${currentTab === 'activity-global' ? ' active' : ''}" href="/activity">
          <span class="nav-icon">${SVG.activity}</span> Activity
        </a>
      </div>
      <div class="nav-group">
        <div class="nav-group-label">Projects</div>
        ${projectLinks || '<div class="nav-item" style="color:var(--text-2)">No projects yet</div>'}
      </div>
    </nav>
  </aside>`;
}

export function topbarHtml(title, breadcrumbs = [], actions = '') {
  const bc = breadcrumbs.map((b, i) => {
    if (i < breadcrumbs.length - 1) {
      return `<a href="${b.href}">${esc(b.label)}</a><span class="sep">/</span>`;
    }
    return `<span>${esc(b.label)}</span>`;
  }).join(' ');

  return `<div class="topbar">
    <div class="topbar-breadcrumb">${bc}</div>
    <div class="topbar-actions">${actions}</div>
  </div>`;
}

export function tabsHtml(tabs, currentTab, baseUrl) {
  return `<div class="tabs">
    ${tabs.map(t =>
      `<a class="tab${t.id === currentTab ? ' active' : ''}" href="${baseUrl}/${t.id}">${t.icon}${t.label}</a>`
    ).join('\n')}
  </div>`;
}

export { SVG };

export function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function shortenPath(p) {
  if (!p) return '';
  const normalized = p.replace(/\\/g, '/');
  const parts = normalized.split('/');
  if (parts.length <= 3) return normalized;
  return '~/' + parts.slice(-2).join('/');
}
