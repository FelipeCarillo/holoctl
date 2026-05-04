import { esc } from '../layout.js';

export function homePage(projects) {
  if (projects.length === 0) {
    return `<div class="content">
      <div class="empty-state">
        <h3>No projects yet</h3>
        <p>Run <code>projctl init</code> in any project directory to get started.</p>
      </div>
    </div>`;
  }

  return `<div class="content">
    <div class="section-header">
      <h2 class="section-title">Projects</h2>
      <span class="section-count">${projects.length} project${projects.length !== 1 ? 's' : ''} registered</span>
    </div>
    <div class="project-grid">
      ${projects.map(projectCard).join('\n')}
    </div>
  </div>`;
}

function projectCard(p) {
  const counts = p.counts || {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const doing = counts.doing || 0;
  const done = counts.done || 0;
  const backlog = counts.backlog || 0;
  const review = counts.review || 0;
  const repoCount = (p.repos || []).length;
  const shortPath = shortenPath(p.path);

  return `<a class="project-card" href="/project/${esc(p.alias)}/board">
    <div class="project-card-header">
      <div class="project-card-icon">${esc(p.prefix?.[0] || p.alias[0]?.toUpperCase() || 'P')}</div>
      <div style="flex:1;min-width:0">
        <div class="project-card-name">${esc(p.name || p.alias)}</div>
        <div class="project-card-prefix">${esc(p.prefix || p.alias.toUpperCase())} · ${total} ticket${total !== 1 ? 's' : ''}${repoCount > 0 ? ` · ${repoCount} repo${repoCount !== 1 ? 's' : ''}` : ''}</div>
        <div class="project-card-path" title="${esc(p.path)}">${esc(shortPath)}</div>
      </div>
    </div>
    <div class="progress-bar">
      ${done ? `<div class="progress-segment done" style="width:${total ? (done/total*100) : 0}%"></div>` : ''}
      ${review ? `<div class="progress-segment review" style="width:${total ? (review/total*100) : 0}%"></div>` : ''}
      ${doing ? `<div class="progress-segment doing" style="width:${total ? (doing/total*100) : 0}%"></div>` : ''}
      ${backlog ? `<div class="progress-segment backlog" style="width:${total ? (backlog/total*100) : 0}%"></div>` : ''}
    </div>
    <div class="project-card-stats">
      <div class="stat-mini"><span class="stat-dot backlog"></span>${backlog} backlog</div>
      <div class="stat-mini"><span class="stat-dot doing"></span>${doing} doing</div>
      <div class="stat-mini"><span class="stat-dot review"></span>${review} review</div>
      <div class="stat-mini"><span class="stat-dot done"></span>${done} done</div>
    </div>
    <div class="project-card-meta">
      ${(p.agents || []).slice(0, 3).map(a => `<span class="chip chip-agent">${esc(a)}</span>`).join('')}
      ${(p.targets || []).map(t => `<span class="chip chip-target">${esc(t)}</span>`).join('')}
    </div>
  </a>`;
}

function shortenPath(p) {
  if (!p) return '';
  const normalized = p.replace(/\\/g, '/');
  const parts = normalized.split('/');
  if (parts.length <= 3) return normalized;
  return '~/' + parts.slice(-2).join('/');
}
