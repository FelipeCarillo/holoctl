import { esc } from '../layout.js';

export function agentDetailPage(agent, rawBody, backLink = '') {
  const tools = Array.isArray(agent.tools) ? agent.tools : [];
  const trigger = agent.trigger || 'ticket';
  const model = agent.model || 'standard';
  const sections = parseMarkdownSections(rawBody);

  return `<div class="content">
    ${backLink}
    <div class="detail-page">
      <div class="detail-header">
        <div class="detail-header-top">
          <span class="trigger-badge">${esc(trigger)}</span>
          <span class="model-badge ${model}">${esc(model)}</span>
        </div>
        <h1 class="detail-title">${esc(agent.name)}</h1>
        <p class="detail-desc">${esc(agent.description)}</p>
      </div>

      <div class="detail-grid">
        <div class="detail-main">
          ${sections.map(s => `
            <div class="detail-section">
              <h3 class="detail-section-title">${esc(s.title)}</h3>
              <div class="detail-section-body">${renderMarkdown(s.content)}</div>
            </div>
          `).join('')}
          ${sections.length === 0 ? '<div class="detail-section"><p class="detail-empty">No instructions defined.</p></div>' : ''}
        </div>

        <aside class="detail-sidebar">
          <div class="detail-field">
            <div class="detail-field-label">Model</div>
            <div class="detail-field-value"><span class="model-badge ${model}">${esc(model)}</span></div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">Trigger</div>
            <div class="detail-field-value"><span class="trigger-badge">${esc(trigger)}</span></div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">Tools</div>
            <div class="detail-field-value">${tools.length ? tools.map(t => `<span class="tool-chip">${esc(typeof t === 'string' ? t : String(t))}</span>`).join(' ') : '<span class="detail-empty">None</span>'}</div>
          </div>
          <div class="detail-field">
            <div class="detail-field-label">File</div>
            <div class="detail-field-value mono">${esc(agent.file || '')}</div>
          </div>
        </aside>
      </div>
    </div>
  </div>`;
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
    .replace(/^- (.+)$/gm, '<div class="md-li">$1</div>')
    .replace(/^\d+\.\s+(.+)$/gm, '<div class="md-li md-ol">$1</div>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n{2,}/g, '<br/><br/>')
    .replace(/\n/g, '<br/>') || '<p class="detail-empty">Empty</p>';
}
