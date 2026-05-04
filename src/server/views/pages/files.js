import { esc } from '../layout.js';

const BADGE_COLORS = {
  git: 'var(--orange)',
  node: 'var(--green)',
  python: 'var(--blue)',
  go: 'var(--cyan)',
  rust: 'var(--orange)',
  flutter: 'var(--blue)',
  java: 'var(--red)',
  php: 'var(--purple, #a78bfa)',
  docker: 'var(--blue)',
  terraform: 'var(--purple, #a78bfa)',
  ios: 'var(--text-2)',
};

const FILE_ICONS = {
  js: '📄', ts: '📄', jsx: '📄', tsx: '📄',
  py: '🐍', go: '📄', rs: '📄',
  md: '📝', json: '📋', yaml: '📋', yml: '📋',
  toml: '📋', env: '🔒', gitignore: '🙈',
  css: '🎨', html: '🌐', svg: '🖼',
  sh: '⚙️', dockerfile: '🐳',
};

export function filesPage(alias, entries) {
  return `<div class="content">
    <div class="section-header">
      <h2 class="section-title">Files</h2>
      <span class="section-count" style="font-size:11px;color:var(--text-3)">project root</span>
    </div>
    <div class="file-tree" id="file-tree" data-alias="${esc(alias)}">
      ${renderEntries(entries, '', 0)}
    </div>
  </div>`;
}

function renderEntries(entries, parentPath, depth) {
  return entries.map(e => renderEntry(e, parentPath, depth)).join('\n');
}

function renderEntry(e, parentPath, depth) {
  const indent = depth * 20;
  const entryPath = parentPath ? `${parentPath}/${e.name}` : e.name;

  if (e.type === 'dir') {
    const badges = renderBadges(e.badges);
    const childrenHtml = e.children
      ? `<div class="tree-children" id="children-${esc(entryPath.replace(/\//g, '-'))}">${renderEntries(e.children, entryPath, depth + 1)}</div>`
      : `<div class="tree-children tree-lazy" id="children-${esc(entryPath.replace(/\//g, '-'))}" data-path="${esc(entryPath)}" data-loaded="false" style="display:none"></div>`;

    const expanded = depth < 1 ? 'open' : '';
    return `<details class="tree-dir" ${expanded} style="--indent:${indent}px">
      <summary class="tree-row tree-dir-row" data-path="${esc(entryPath)}">
        <span class="tree-indent" style="width:${indent}px"></span>
        <span class="tree-chevron">▶</span>
        <span class="tree-icon">📁</span>
        <span class="tree-name">${esc(e.name)}</span>
        ${badges}
      </summary>
      ${childrenHtml}
    </details>`;
  }

  const icon = FILE_ICONS[e.ext] || '📄';
  return `<div class="tree-row tree-file-row" style="padding-left:${indent + 20}px" title="${esc(entryPath)}">
    <span class="tree-icon">${icon}</span>
    <span class="tree-name tree-file-name" data-path="${esc(entryPath)}">${esc(e.name)}</span>
  </div>`;
}

function renderBadges(badges) {
  if (!badges || badges.length === 0) return '';
  return badges.map(b => {
    const color = BADGE_COLORS[b.badge] || 'var(--text-2)';
    return `<span class="tree-badge" style="color:${color}">${esc(b.label)}</span>`;
  }).join('');
}
