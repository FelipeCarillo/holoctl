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

  // ── Sidebar collapse (state lives on <html data-sidebar="collapsed">,
  //    set by the inline boot script in <head> to avoid layout flash) ──

  window.__toggleSidebar = function () {
    const html = document.documentElement;
    const collapsed = html.getAttribute('data-sidebar') === 'collapsed';
    if (collapsed) {
      html.removeAttribute('data-sidebar');
      localStorage.setItem('holoctl-sidebar', 'open');
    } else {
      html.setAttribute('data-sidebar', 'collapsed');
      localStorage.setItem('holoctl-sidebar', 'collapsed');
    }
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
    const match = path.match(/\/project\/([^/]+)\/board(?:\/[^/]+)?$/);
    // Skip on /board/<ticket-id> detail pages (no kanban there).
    if (!match || !document.getElementById('kanban')) return;

    const alias = match[1];
    const source = new EventSource(`/api/project/${alias}/events`);
    let lastData = null;
    let inflight = false;

    source.addEventListener('board-update', async (e) => {
      // First event is the initial state — same as what's already on screen.
      if (lastData === null) {
        lastData = e.data;
        return;
      }
      if (e.data === lastData || inflight) return;
      lastData = e.data;
      inflight = true;
      try {
        const resp = await fetch(`/api/project/${alias}/board-html`, {
          cache: 'no-store',
        });
        if (!resp.ok) return;
        const html = (await resp.text()).trim();
        const wrapper = document.createElement('div');
        wrapper.innerHTML = html;
        const fresh = wrapper.firstElementChild;
        const current = document.getElementById('kanban');
        if (fresh && current) current.replaceWith(fresh);
        // Reapply filter / sort / group state to the freshly-swapped DOM.
        if (window.__reapplyBoardControls) window.__reapplyBoardControls();
        showToast('Board updated');
      } catch (_) {
        // Fall through; next event retries.
      } finally {
        inflight = false;
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

  // ── Board controls: filter, sort, group-by ──

  // Field-level state lives in localStorage per workspace alias so refreshing
  // or navigating away and back keeps the agent's view intact.
  function bcStorageKey() {
    const m = window.location.pathname.match(/\/project\/([^/]+)\/board/);
    return m ? `holoctl-bc:${m[1]}` : null;
  }

  const BC_DEFAULT = {
    filter: { status: '', priority: '', agent: '', sprint: '', tag: '', project: '' },
    sort: 'created',
    group: 'status',
  };

  function bcLoad() {
    const k = bcStorageKey();
    if (!k) return JSON.parse(JSON.stringify(BC_DEFAULT));
    try {
      const saved = JSON.parse(localStorage.getItem(k) || '{}');
      return {
        filter: { ...BC_DEFAULT.filter, ...(saved.filter || {}) },
        sort: saved.sort || BC_DEFAULT.sort,
        group: saved.group || BC_DEFAULT.group,
      };
    } catch (_) {
      return JSON.parse(JSON.stringify(BC_DEFAULT));
    }
  }

  function bcSave(state) {
    const k = bcStorageKey();
    if (k) localStorage.setItem(k, JSON.stringify(state));
  }

  // Read every card's data-attrs to build the option set per filter axis.
  function bcCollectOptions() {
    const opts = { status: new Set(), priority: new Set(), agent: new Set(), sprint: new Set(), tag: new Set(), project: new Set() };
    document.querySelectorAll('.kanban-card').forEach(card => {
      const get = name => card.getAttribute('data-' + name) || '';
      if (get('status')) opts.status.add(get('status'));
      if (get('p')) opts.priority.add(get('p'));
      if (get('sprint')) opts.sprint.add(get('sprint'));
      get('agent').split(',').filter(Boolean).forEach(v => opts.agent.add(v));
      get('tags').split(',').filter(Boolean).forEach(v => opts.tag.add(v));
      get('projects').split(',').filter(Boolean).forEach(v => opts.project.add(v));
    });
    const sorted = {};
    for (const [k, set] of Object.entries(opts)) sorted[k] = [...set].sort();
    return sorted;
  }

  // Populate each <select data-filter="X"> with the option set, preserving
  // the currently-selected value if it's still present.
  function bcRefreshOptions(state) {
    const opts = bcCollectOptions();
    document.querySelectorAll('[data-filter]').forEach(sel => {
      const axis = sel.getAttribute('data-filter');
      const current = state.filter[axis] || sel.value;
      // Preserve the "All" option (empty value) and rebuild the rest.
      sel.innerHTML = '<option value="">All</option>' +
        (opts[axis] || []).map(v =>
          `<option value="${v.replace(/"/g, '&quot;')}"${v === current ? ' selected' : ''}>${v}</option>`
        ).join('');
      if (opts[axis] && opts[axis].includes(current)) sel.value = current;
    });
  }

  // Show / hide cards based on the filter; cards whose data-* on every
  // active axis matches the filter survive.
  function bcApplyFilter(state) {
    const f = state.filter;
    let activeFilters = 0;
    Object.values(f).forEach(v => { if (v) activeFilters++; });
    document.querySelectorAll('.kanban-card').forEach(card => {
      const get = name => card.getAttribute('data-' + name) || '';
      const matches =
        (!f.status   || get('status') === f.status) &&
        (!f.priority || get('p') === f.priority) &&
        (!f.sprint   || get('sprint') === f.sprint) &&
        (!f.agent    || get('agent').split(',').includes(f.agent)) &&
        (!f.tag      || get('tags').split(',').includes(f.tag)) &&
        (!f.project  || get('projects').split(',').includes(f.project));
      card.classList.toggle('bc-hidden', !matches);
    });
    const countEl = document.getElementById('board-controls-count');
    if (countEl) countEl.textContent = activeFilters > 0 ? `${activeFilters} active` : '';
  }

  // Sort cards within each column. Re-orders nodes in place.
  function bcApplySort(state) {
    const cmp = bcGetComparator(state.sort);
    document.querySelectorAll('.kanban-cards').forEach(container => {
      const cards = [...container.querySelectorAll('.kanban-card')];
      cards.sort(cmp).forEach(c => container.appendChild(c));
    });
  }

  function bcGetComparator(mode) {
    const PRIO_RANK = { p0: 0, p1: 1, p2: 2, p3: 3 };
    const get = (card, name) => card.getAttribute('data-' + name) || '';
    if (mode === 'created') return (a, b) => get(a, 'created').localeCompare(get(b, 'created'));
    if (mode === 'created-desc') return (a, b) => get(b, 'created').localeCompare(get(a, 'created'));
    if (mode === 'updated-desc') return (a, b) => get(b, 'updated').localeCompare(get(a, 'updated'));
    if (mode === 'priority') return (a, b) =>
      (PRIO_RANK[get(a, 'p')] ?? 99) - (PRIO_RANK[get(b, 'p')] ?? 99);
    if (mode === 'title') return (a, b) => get(a, 'title').localeCompare(get(b, 'title'));
    if (mode === 'id') {
      const num = c => parseInt((get(c, 'id').split('-').pop() || '0'), 10) || 0;
      return (a, b) => num(a) - num(b);
    }
    return () => 0;
  }

  // Group-by changes which buckets the cards land in. Status (default) keeps
  // the server-rendered columns. Other modes rebuild the column list from
  // the unique values of the chosen attribute.
  function bcApplyGroup(state) {
    const kanban = document.getElementById('kanban');
    if (!kanban) return;
    const allCards = [...kanban.querySelectorAll('.kanban-card')];
    if (state.group === 'status') {
      // Re-distribute cards back to their original status buckets.
      kanban.querySelectorAll('.kanban-col').forEach(col => {
        const status = col.getAttribute('data-status');
        col.setAttribute('data-bucket', status);
        const cards = col.querySelector('.kanban-cards');
        // Remove all current cards from this column.
        [...cards.querySelectorAll('.kanban-card')].forEach(c => c.remove());
        const empty = cards.querySelector('.kanban-empty');
        if (empty) empty.remove();
        // Re-insert cards whose data-status matches this column.
        const owned = allCards.filter(c => c.getAttribute('data-status') === status);
        if (owned.length === 0) {
          cards.innerHTML = '<div class="kanban-empty">No tickets</div>';
        } else {
          owned.forEach(c => cards.appendChild(c));
        }
        const count = col.querySelector('.count');
        const label = col.querySelector('.col-label');
        if (count) count.textContent = owned.length;
        if (label) label.textContent = status.toUpperCase();
      });
      return;
    }
    // Custom group-by: rebuild columns from scratch.
    const axisAttr = { priority: 'p', sprint: 'sprint', agent: 'agent', tag: 'tags' }[state.group];
    if (!axisAttr) return;
    const buckets = new Map();
    allCards.forEach(card => {
      const raw = card.getAttribute('data-' + axisAttr) || '';
      const values = ['agent', 'tags'].includes(axisAttr)
        ? (raw.split(',').filter(Boolean).length ? raw.split(',').filter(Boolean) : ['(none)'])
        : [raw || '(none)'];
      values.forEach(v => {
        if (!buckets.has(v)) buckets.set(v, []);
        // Cards with multiple agents/tags appear in each bucket — clone DOM
        // so a card can show up in multiple columns. Use a wrapper marker
        // so live updates don't double-apply filters.
        buckets.get(v).push(card);
      });
    });
    // Rebuild kanban with the new buckets.
    const sortedKeys = [...buckets.keys()].sort((a, b) => {
      if (a === '(none)') return 1;
      if (b === '(none)') return -1;
      return a.localeCompare(b);
    });
    kanban.innerHTML = sortedKeys.map(k => {
      const cards = buckets.get(k);
      return `<div class="kanban-col" data-bucket="${k.replace(/"/g, '&quot;')}">
        <div class="kanban-col-header">
          <span class="col-label">${k.toUpperCase()}</span>
          <span class="count">${cards.length}</span>
        </div>
        <div class="kanban-cards"></div>
      </div>`;
    }).join('');
    // Now move cards into their buckets (clone for shared cards).
    sortedKeys.forEach(k => {
      const col = kanban.querySelector(`.kanban-col[data-bucket="${k.replace(/"/g, '&quot;')}"] .kanban-cards`);
      buckets.get(k).forEach(card => {
        // If a card belongs to multiple buckets, clone it; only the first
        // bucket gets the original (so SSE swap can find it again).
        col.appendChild(card.cloneNode(true));
      });
    });
  }

  function bcApply(state) {
    bcRefreshOptions(state);
    bcApplyGroup(state);
    bcApplySort(state);
    bcApplyFilter(state);
  }

  function initBoardControls() {
    const panel = document.getElementById('board-controls');
    if (!panel) return;

    const state = bcLoad();

    // Set the toggle's open/closed state — open if there are active filters.
    const hasActive = Object.values(state.filter).some(Boolean) ||
                      state.sort !== BC_DEFAULT.sort ||
                      state.group !== BC_DEFAULT.group;
    if (hasActive) panel.setAttribute('data-state', 'expanded');

    // Toggle button
    panel.querySelector('[data-bc-toggle]').addEventListener('click', () => {
      const expanded = panel.getAttribute('data-state') === 'expanded';
      panel.setAttribute('data-state', expanded ? 'collapsed' : 'expanded');
    });

    // Reset
    panel.querySelector('[data-bc-reset]').addEventListener('click', () => {
      const fresh = JSON.parse(JSON.stringify(BC_DEFAULT));
      bcSave(fresh);
      window.location.reload();
    });

    // Wire up filter selects
    panel.querySelectorAll('[data-filter]').forEach(sel => {
      sel.value = state.filter[sel.getAttribute('data-filter')] || '';
      sel.addEventListener('change', () => {
        state.filter[sel.getAttribute('data-filter')] = sel.value;
        bcSave(state);
        bcApplyFilter(state);
      });
    });

    // Sort
    const sortSel = panel.querySelector('[data-sort]');
    sortSel.value = state.sort;
    sortSel.addEventListener('change', () => {
      state.sort = sortSel.value;
      bcSave(state);
      bcApplySort(state);
    });

    // Group-by
    const groupSel = panel.querySelector('[data-group]');
    groupSel.value = state.group;
    groupSel.addEventListener('change', () => {
      state.group = groupSel.value;
      bcSave(state);
      bcApply(state);
    });

    bcApply(state);
  }

  // Re-apply controls after the SSE handler swaps the kanban DOM.
  window.__reapplyBoardControls = function () {
    const panel = document.getElementById('board-controls');
    if (!panel) return;
    bcApply(bcLoad());
  };

  // ── Init ──

  initTheme();

  document.addEventListener('DOMContentLoaded', () => {
    initSSE();
    initTabs();
    initStagger();
    initFileTree();
    initBoardControls();
  });
})();
