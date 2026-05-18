import { showToast } from './toast.js';

// ── File tree (lazy expand + copy path) ──

export function initFileTree() {
  const tree = document.getElementById('file-tree');
  if (!tree) return;

  const alias = tree.getAttribute('data-alias');

  // Lazy load children when a dir is opened
  tree.addEventListener('toggle', async (e) => {
    const details = e.target;
    if (!details.open) return;
    const childrenId = 'children-' + details.querySelector('[data-path]')?.getAttribute('data-path')?.replace(/\//g, '-');
    const lazy = document.getElementById(childrenId);
    if (!lazy || lazy.getAttribute('data-loaded') !== 'false') return;

    const subPath = lazy.getAttribute('data-path');
    lazy.style.display = '';
    lazy.innerHTML = '<div class="tree-lazy-loading">Loading...</div>';

    try {
      const res = await fetch(`/api/project/${encodeURIComponent(alias)}/files?path=${encodeURIComponent(subPath)}`);
      const { entries } = await res.json();
      lazy.innerHTML = renderTreeEntries(entries, subPath, 1);
      lazy.setAttribute('data-loaded', 'true');
      initFileTree(); // re-bind for newly inserted nodes
    } catch {
      lazy.innerHTML = '<div class="tree-lazy-loading">Failed to load</div>';
    }
  }, true);

  // Copy path on file click
  tree.addEventListener('click', (e) => {
    const fileName = e.target.closest('.tree-file-name');
    if (!fileName) return;
    const p = fileName.getAttribute('data-path');
    if (!p) return;
    navigator.clipboard?.writeText(p).catch(() => {});
    showToast(`Copied: ${p}`);
  });
}

function renderTreeEntries(entries, parentPath, depth) {
  return entries.map(e => {
    const entryPath = parentPath ? `${parentPath}/${e.name}` : e.name;
    const indent = depth * 20;
    if (e.type === 'dir') {
      const badgesHtml = (e.badges || []).map(b => `<span class="tree-badge">${b.label}</span>`).join('');
      const childId = 'children-' + entryPath.replace(/\//g, '-');
      return `<details class="tree-dir">
        <summary class="tree-row tree-dir-row" data-path="${entryPath}">
          <span class="tree-indent" style="width:${indent}px"></span>
          <span class="tree-chevron">▶</span>
          <span class="tree-icon">📁</span>
          <span class="tree-name">${e.name}</span>
          ${badgesHtml}
        </summary>
        <div class="tree-children tree-lazy" id="${childId}" data-path="${entryPath}" data-loaded="false" style="display:none"></div>
      </details>`;
    }
    return `<div class="tree-row tree-file-row" style="padding-left:${indent + 20}px">
      <span class="tree-icon">📄</span>
      <span class="tree-name tree-file-name" data-path="${entryPath}">${e.name}</span>
    </div>`;
  }).join('');
}
