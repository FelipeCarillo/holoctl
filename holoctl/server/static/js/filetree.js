import { showToast } from './toast.js';

// ── File tree (lazy expand + copy path) ──
//
// Supports two usage modes:
//
//  1. Generic file tree (container id="file-tree"):
//     Fetches from data-tree-endpoint?path=<subpath>.
//     Files are copy-to-clipboard (legacy behaviour).
//
//  2. Context tree (container id="context-tree"):
//     Fetches from data-tree-endpoint?path=<subpath>.
//     Files render as <a href="data-file-href-base + path">.
//
// Configuration via data-attributes on the container element:
//   data-alias            — project alias (used by legacy endpoint)
//   data-tree-endpoint    — API base URL for tree listing
//   data-file-href-base   — (optional) URL prefix for file links;
//                           when present, file nodes render as <a> links
//                           rather than copy-to-clipboard spans.

/** Escape a string for safe insertion into HTML text/attribute content. */
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function initFileTree() {
  for (const tree of document.querySelectorAll('#file-tree, #context-tree')) {
    _attachTree(tree);
  }
}

function _attachTree(tree) {
  const alias = tree.getAttribute('data-alias');
  const treeEndpoint = tree.getAttribute('data-tree-endpoint')
    || `/api/project/${encodeURIComponent(alias)}/files`;
  const fileHrefBase = tree.getAttribute('data-file-href-base') || null;

  // Lazy load children when a dir is opened
  tree.addEventListener('toggle', async (e) => {
    const details = e.target;
    if (!details.open) return;
    // Find the lazy children div nested inside this <details>.
    const lazy = details.querySelector('.tree-lazy[data-loaded="false"]');
    if (!lazy) return;

    const subPath = lazy.getAttribute('data-path');
    // Read the depth stored on the lazy container so nested levels indent
    // correctly; default to 0 if missing (first-level expansion).
    const parentDepth = parseInt(lazy.getAttribute('data-depth') || '0', 10);
    lazy.style.display = '';
    lazy.innerHTML = '<div class="tree-lazy-loading">Loading…</div>';

    try {
      const url = `${treeEndpoint}?path=${encodeURIComponent(subPath)}`;
      const res = await fetch(url);
      if (!res.ok) {
        lazy.innerHTML = '<div class="tree-lazy-loading">Failed to load</div>';
        return;
      }
      const { entries } = await res.json();
      lazy.innerHTML = renderTreeEntries(entries, subPath, parentDepth + 1, fileHrefBase);
      lazy.setAttribute('data-loaded', 'true');
    } catch {
      lazy.innerHTML = '<div class="tree-lazy-loading">Failed to load</div>';
    }
  }, true);

  // Copy path on file click (legacy: only when no fileHrefBase)
  if (!fileHrefBase) {
    tree.addEventListener('click', (e) => {
      const fileName = e.target.closest('.tree-file-name');
      if (!fileName) return;
      const p = fileName.getAttribute('data-path');
      if (!p) return;
      navigator.clipboard?.writeText(p).catch(() => {});
      showToast(`Copied: ${p}`);
    });
  }
}

function renderTreeEntries(entries, parentPath, depth, fileHrefBase) {
  return entries.map(e => {
    const entryPath = parentPath ? `${parentPath}/${e.name}` : e.name;
    const indent = depth * 20;
    if (e.type === 'dir') {
      const badgesHtml = (e.badges || []).map(b => `<span class="tree-badge">${esc(b.label)}</span>`).join('');
      const childId = 'children-' + entryPath.replace(/\//g, '-');
      return `<details class="tree-dir">
        <summary class="tree-row tree-dir-row" data-path="${esc(entryPath)}">
          <span class="tree-indent" style="width:${indent}px"></span>
          <span class="tree-chevron">&#x25B6;</span>
          <span class="tree-icon">&#x1F4C1;</span>
          <span class="tree-name">${esc(e.name)}</span>
          ${badgesHtml}
        </summary>
        <div class="tree-children tree-lazy" id="${childId}" data-path="${esc(entryPath)}" data-depth="${depth}" data-loaded="false" style="display:none"></div>
      </details>`;
    }
    if (fileHrefBase) {
      const href = fileHrefBase + entryPath.split('/').map(encodeURIComponent).join('/');
      return `<div class="tree-row tree-file-row" style="padding-left:${indent + 20}px">
        <span class="tree-icon">&#x1F4C4;</span>
        <a href="${esc(href)}" class="tree-name tree-context-link">${esc(e.name)}</a>
      </div>`;
    }
    return `<div class="tree-row tree-file-row" style="padding-left:${indent + 20}px">
      <span class="tree-icon">&#x1F4C4;</span>
      <span class="tree-name tree-file-name" data-path="${esc(entryPath)}">${esc(e.name)}</span>
    </div>`;
  }).join('');
}
