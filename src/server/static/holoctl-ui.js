(function () {
  'use strict';

  // ── Theme ──

  function initTheme() {
    const saved = localStorage.getItem('holoctl-theme');
    const theme = saved || 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeIcons(theme);
  }

  function updateThemeIcons(theme) {
    document.querySelectorAll('.theme-icon-dark').forEach(el => {
      el.style.display = theme === 'dark' ? 'flex' : 'none';
    });
    document.querySelectorAll('.theme-icon-light').forEach(el => {
      el.style.display = theme === 'light' ? 'flex' : 'none';
    });
  }

  window.__toggleTheme = function () {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('holoctl-theme', next);
    updateThemeIcons(next);
  };

  // ── Toast Notifications ──

  function showToast(message) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<span class="toast-dot"></span><span>${message}</span><button class="toast-dismiss" onclick="this.parentElement.remove()">&times;</button>`;
    toast.addEventListener('click', (e) => {
      if (e.target.closest('.toast-dismiss')) return;
      window.location.reload();
    });
    container.appendChild(toast);

    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 8000);
  }

  // ── SSE Live Board Updates ──

  function initSSE() {
    const kanban = document.getElementById('kanban');
    if (!kanban) return;

    const path = window.location.pathname;
    const match = path.match(/\/project\/([^/]+)\/board/);
    if (!match) return;

    const alias = match[1];
    const source = new EventSource(`/api/project/${alias}/events`);
    let lastData = null;

    source.addEventListener('board-update', (e) => {
      if (lastData === null) {
        lastData = e.data;
        return;
      }
      if (e.data !== lastData) {
        lastData = e.data;
        showToast('Board updated — click to refresh');
      }
    });

    source.onerror = () => {
      source.close();
      setTimeout(() => initSSE(), 5000);
    };
  }

  // ── Tab Keyboard Navigation ──

  function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach((tab, i) => {
      tab.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowRight' && tabs[i + 1]) {
          tabs[i + 1].focus();
          tabs[i + 1].click();
        }
        if (e.key === 'ArrowLeft' && tabs[i - 1]) {
          tabs[i - 1].focus();
          tabs[i - 1].click();
        }
      });
    });
  }

  // ── Stagger animations ──

  function initStagger() {
    document.querySelectorAll('.project-grid > *, .kanban-column > *, .agent-grid > *, .context-list > *').forEach((el, i) => {
      el.style.animationDelay = `${i * 40}ms`;
    });
  }

  // ── File tree (lazy expand + copy path) ──

  function initFileTree() {
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

  // ── Project filter (board page) ──

  window.__filterProject = function (btn, project) {
    document.querySelectorAll('.scope-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.kanban-card').forEach(card => {
      const cardProjects = (card.getAttribute('data-projects') || '').split(',').filter(Boolean);
      const visible = project === '' || cardProjects.includes(project);
      card.style.display = visible ? '' : 'none';
    });
  };

  // ── Init ──

  initTheme();

  document.addEventListener('DOMContentLoaded', () => {
    initSSE();
    initTabs();
    initStagger();
    initFileTree();
  });
})();
