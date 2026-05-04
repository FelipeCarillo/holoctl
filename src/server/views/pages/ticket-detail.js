import { esc } from '../layout.js';

export function ticketDetailPage(ticket, rawBody, backLink = '') {
  const priority = ticket.priority || 'p2';
  const status = ticket.status || 'backlog';
  const agents = Array.isArray(ticket.agent) ? ticket.agent : (ticket.agent ? [ticket.agent] : []);
  const tags = Array.isArray(ticket.tags) ? ticket.tags : [];
  const depends = Array.isArray(ticket.depends) ? ticket.depends : [];

  const statusLabels = {
    backlog: 'Backlog',
    doing: 'In Progress',
    review: 'Review',
    done: 'Done',
    cancelled: 'Cancelled',
  };

  const statusColors = {
    backlog: 'muted',
    doing: 'blue',
    review: 'yellow',
    done: 'green',
    cancelled: 'red',
  };

  const sections = parseMarkdownSections(rawBody);

  return `<div class="content">
    ${backLink}
    <div class="detail-page">
      <div class="detail-header">
        <div class="detail-header-top">
          <span class="detail-id">${esc(ticket.id)}</span>
          <span class="p-badge ${priority}">${priority}</span>
          <span class="status-badge ${statusColors[status] || 'muted'}">${esc(statusLabels[status] || status)}</span>
        </div>
        <h1 class="detail-title">${esc(ticket.title)}</h1>
      </div>

      <div class="detail-grid">
        <div class="detail-main">
          ${sections.map(s => `
            <div class="detail-section">
              <h3 class="detail-section-title">${esc(s.title)}</h3>
              <div class="detail-section-body">${renderMarkdown(s.content)}</div>
            </div>
          `).join('')}
          ${sections.length === 0 ? '<div class="detail-section"><p class="detail-empty">No content yet.</p></div>' : ''}
        </div>

        <aside class="detail-sidebar">
          <div class="detail-field">
            <div class="detail-field-label">Status</div>
            <div class="detail-field-value"><span class="status-badge ${statusColors[status] || 'muted'}">${esc(statusLabels[status] || status)}</span></div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">Priority</div>
            <div class="detail-field-value"><span class="p-badge ${priority}">${priority}</span></div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">Agent</div>
            <div class="detail-field-value">${agents.length ? agents.map(a => `<span class="chip chip-agent">${esc(a)}</span>`).join(' ') : '<span class="detail-empty">None</span>'}</div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">Scope</div>
            <div class="detail-field-value"><code>${esc(ticket.scope || '—')}</code></div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">Sprint</div>
            <div class="detail-field-value">${ticket.sprint ? `<span class="chip chip-sprint">${esc(ticket.sprint)}</span>` : '<span class="detail-empty">None</span>'}</div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">Tags</div>
            <div class="detail-field-value">${tags.length ? tags.map(t => `<span class="tool-chip">#${esc(t)}</span>`).join(' ') : '<span class="detail-empty">None</span>'}</div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">Dependencies</div>
            <div class="detail-field-value">${depends.length ? depends.map(d => `<code>${esc(d)}</code>`).join(', ') : '<span class="detail-empty">None</span>'}</div>
          </div>
          <hr class="detail-divider"/>
          <div class="detail-field">
            <div class="detail-field-label">Created</div>
            <div class="detail-field-value mono">${formatDateTime(ticket.created)}</div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">Updated</div>
            <div class="detail-field-value mono">${formatDateTime(ticket.updated)}</div>
          </div>
          ${ticket.completed ? `
          <div class="detail-field">
            <div class="detail-field-label">Completed</div>
            <div class="detail-field-value mono">${formatDateTime(ticket.completed)}</div>
          </div>` : ''}
        </aside>
      </div>
    </div>
  </div>`;
}

function formatDateTime(val) {
  if (!val) return '—';
  const d = new Date(val);
  if (isNaN(d.getTime())) return esc(String(val));
  const date = d.toLocaleDateString('en-CA');
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return `${date} <span style="color:var(--text-2)">${time}</span>`;
}

function parseMarkdownSections(body) {
  if (!body || !body.trim()) return [];
  const lines = body.split('\n');
  const sections = [];
  let current = null;

  for (const line of lines) {
    const match = line.match(/^#+\s+(.+)/);
    if (match) {
      if (current) sections.push(current);
      current = { title: match[1], content: '' };
    } else if (current) {
      current.content += line + '\n';
    }
  }
  if (current) sections.push(current);
  return sections;
}

function renderMarkdown(text) {
  return esc(text.trim())
    .replace(/^- \[x\] (.+)$/gm, '<div class="check done"><span class="check-box">&#10003;</span> $1</div>')
    .replace(/^- \[ \] (.+)$/gm, '<div class="check"><span class="check-box"></span> $1</div>')
    .replace(/^- (.+)$/gm, '<div class="md-li">$1</div>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n{2,}/g, '<br/><br/>')
    .replace(/\n/g, '<br/>') || '<p class="detail-empty">Empty</p>';
}
