import { esc } from '../layout.js';

const icons = {
  doc: `<svg class="icon-sm" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`,
  folder: `<svg class="icon-sm" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
  objective: `<svg class="icon-sm" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
  architecture: `<svg class="icon-sm" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>`,
  conventions: `<svg class="icon-sm" viewBox="0 0 24 24"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>`,
};

export function contextPage(docs, alias) {
  if (docs.length === 0) {
    return `<div class="content">
      <div class="empty-state">
        <h3>No context documents</h3>
        <p>Add files to <code>.projctl/context/</code> to define project context.</p>
      </div>
    </div>`;
  }

  return `<div class="content">
    <div class="section-header">
      <h2 class="section-title">Project Context</h2>
      <span class="section-count">${docs.length} item${docs.length !== 1 ? 's' : ''}</span>
    </div>
    <div class="context-list">
      ${docs.map(doc => contextItem(doc, alias)).join('\n')}
    </div>
  </div>`;
}

function contextItem(doc, alias) {
  const iconMap = {
    'objective.md': 'objective',
    'architecture.md': 'architecture',
    'conventions.md': 'conventions',
  };
  const iconType = iconMap[doc.name] || (doc.isDir ? 'folder' : 'doc');
  const iconSvg = icons[iconType] || icons.doc;

  const isClickable = !doc.isDir && alias;
  const tag = isClickable ? 'a' : 'div';
  const href = isClickable ? ` href="/project/${esc(alias)}/context/${esc(doc.name)}"` : '';

  return `<${tag} class="context-item"${href}>
    <div class="context-item-icon ${iconType}">${iconSvg}</div>
    <div>
      <div class="context-item-name">${esc(doc.name)}</div>
      ${doc.description ? `<div class="context-item-desc">${esc(doc.description)}</div>` : ''}
    </div>
  </${tag}>`;
}
