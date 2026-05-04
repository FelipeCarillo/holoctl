import { esc } from '../layout.js';

export function commandDetailPage(cmd, rawBody, backLink = '') {
  const sections = parseMarkdownSections(rawBody);

  return `<div class="content">
    ${backLink}
    <div class="detail-page">
      <div class="detail-header">
        <h1 class="detail-title">/${esc(cmd.name)} ${cmd.arguments ? `<span class="detail-args">${esc(cmd.arguments)}</span>` : ''}</h1>
        <p class="detail-desc">${esc(cmd.description)}</p>
      </div>

      <div class="detail-main" style="max-width:720px">
        ${sections.map(s => `
          <div class="detail-section">
            <h3 class="detail-section-title">${esc(s.title)}</h3>
            <div class="detail-section-body">${renderMarkdown(s.content)}</div>
          </div>
        `).join('')}
        ${sections.length === 0 ? '<div class="detail-section"><p class="detail-empty">No instructions defined.</p></div>' : ''}
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
  let inCode = false;
  return esc(text.trim())
    .replace(/^- (.+)$/gm, '<div class="md-li">$1</div>')
    .replace(/^\d+\.\s+(.+)$/gm, '<div class="md-li md-ol">$1</div>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n{2,}/g, '<br/><br/>')
    .replace(/\n/g, '<br/>') || '<p class="detail-empty">Empty</p>';
}
