import { esc } from '../layout.js';

export function boardPage(project, tickets, config) {
  const statuses = config.board.statuses;
  const shortPath = (project.path || '').replace(/\\/g, '/');
  const alias = project.alias;
  const repos = project.repos || [];

  const statusLabels = {
    backlog: 'Backlog',
    doing: 'In Progress',
    review: 'Review',
    done: 'Done',
    cancelled: 'Cancelled',
  };

  const columns = statuses.map(status => {
    const colTickets = tickets.filter(t => t.status === status);

    return `<div class="kanban-col" data-status="${status}">
      <div class="kanban-col-header">
        <span class="col-label">${statusLabels[status] || status}</span>
        <span class="count">${colTickets.length}</span>
      </div>
      <div class="kanban-cards">
        ${colTickets.length === 0
          ? '<div class="kanban-empty">No tickets</div>'
          : colTickets.map(t => ticketCard(t, alias)).join('\n')}
      </div>
    </div>`;
  });

  const scopeFilter = repos.length > 0
    ? `<div class="scope-filter" id="scope-filter">
        <button class="scope-btn active" data-scope="" onclick="window.__filterScope(this,'')">All</button>
        ${repos.map(r => `<button class="scope-btn" data-scope="${esc(r.name)}" onclick="window.__filterScope(this,'${esc(r.name)}')">${esc(r.name)}</button>`).join('')}
      </div>`
    : '';

  return `<div class="content">
    <div class="board-header">
      <div class="live-indicator"><span class="pulse"></span>Live</div>
      <div class="board-path" title="${esc(shortPath)}">${esc(shortPath)}</div>
      <span class="board-count">${tickets.length} ticket${tickets.length !== 1 ? 's' : ''}</span>
    </div>
    ${scopeFilter}
    <div class="kanban" id="kanban">
      ${columns.join('\n')}
    </div>
  </div>`;
}

function ticketCard(t, alias) {
  const agents = (t.agent || []).map(a => `<span class="chip chip-agent">${esc(a)}</span>`).join('');
  const tags = (t.tags || []).map(tag => `<span class="tool-chip">#${esc(tag)}</span>`).join('');
  const sprint = t.sprint ? `<span class="chip chip-sprint">${esc(t.sprint)}</span>` : '';
  const deps = (t.depends || []).length
    ? `<span class="tool-chip" style="color:var(--red)">dep: ${esc(t.depends.join(', '))}</span>`
    : '';
  const date = t.completed || t.updated || t.created;

  return `<a class="kanban-card" data-p="${t.priority || 'p2'}" data-id="${esc(t.id)}" data-scope="${esc(t.scope || '')}" href="/project/${esc(alias)}/board/${esc(t.id)}">
    <div class="kanban-card-top">
      <span class="kanban-card-id">${esc(t.id)}</span>
      <span class="kanban-card-title">${esc(t.title)}</span>
      <span class="p-badge ${t.priority || 'p2'}">${t.priority || 'p2'}</span>
    </div>
    <div class="kanban-card-meta">${agents}${sprint}${tags}${deps}</div>
    <div class="kanban-card-dates">
      <span>${date || ''}</span>
      <span>${esc(t.scope || '')}</span>
    </div>
  </a>`;
}
