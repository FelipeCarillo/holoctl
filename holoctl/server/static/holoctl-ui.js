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

  // ── Board controls: search, filter chips, sort, group ──

  // Per-workspace state in localStorage. Bumped to v2 because the schema
  // changed (added .search, .filter shape preserved). Old v1 state is left
  // alone — agents who had it just see defaults until they touch a control.
  function bcStorageKey() {
    const m = window.location.pathname.match(/\/project\/([^/]+)\/board/);
    return m ? `holoctl-bc-v2:${m[1]}` : null;
  }

  const BC_DEFAULT = {
    search: '',
    filter: { status: '', priority: '', agent: '', sprint: '', tag: '', project: '' },
    sort: 'created',
    group: 'status',
  };

  // Axis label and value-coercion: filter axes don't 1:1 map to data-* names
  // (priority axis reads data-p; tag axis reads data-tags split by comma).
  // This table captures both for chip rendering and matching.
  const BC_AXIS = {
    status:   { label: 'Status',   attr: 'status',   multi: false },
    priority: { label: 'Priority', attr: 'p',        multi: false },
    agent:    { label: 'Agent',    attr: 'agent',    multi: true  },
    sprint:   { label: 'Sprint',   attr: 'sprint',   multi: false },
    tag:      { label: 'Tag',      attr: 'tags',     multi: true  },
    project:  { label: 'Project',  attr: 'projects', multi: true  },
  };

  function bcLoad() {
    const k = bcStorageKey();
    if (!k) return JSON.parse(JSON.stringify(BC_DEFAULT));
    try {
      const saved = JSON.parse(localStorage.getItem(k) || '{}');
      return {
        search: typeof saved.search === 'string' ? saved.search : '',
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

  // Distinct values per axis, derived from the cards currently in the DOM —
  // used by the Add-filter popover and not stored anywhere.
  function bcCollectOptions() {
    const opts = {};
    Object.keys(BC_AXIS).forEach(a => { opts[a] = new Set(); });
    document.querySelectorAll('.kanban-card').forEach(card => {
      Object.entries(BC_AXIS).forEach(([axis, info]) => {
        const raw = card.getAttribute('data-' + info.attr) || '';
        if (info.multi) {
          raw.split(',').filter(Boolean).forEach(v => opts[axis].add(v));
        } else if (raw) {
          opts[axis].add(raw);
        }
      });
    });
    const sorted = {};
    Object.entries(opts).forEach(([axis, set]) => {
      sorted[axis] = [...set].sort();
    });
    return sorted;
  }

  // Each card lives or dies on the AND of every active axis.
  function bcApplyFilter(state) {
    const f = state.filter;
    const q = (state.search || '').trim().toLowerCase();
    document.querySelectorAll('.kanban-card').forEach(card => {
      let matches = true;
      for (const [axis, info] of Object.entries(BC_AXIS)) {
        const want = f[axis];
        if (!want) continue;
        const raw = card.getAttribute('data-' + info.attr) || '';
        const ok = info.multi
          ? raw.split(',').includes(want)
          : raw === want;
        if (!ok) { matches = false; break; }
      }
      if (matches && q) {
        const haystack = (
          (card.getAttribute('data-id') || '') + ' ' +
          (card.getAttribute('data-title') || '') + ' ' +
          (card.getAttribute('data-tags') || '')
        ).toLowerCase();
        if (!haystack.includes(q)) matches = false;
      }
      card.classList.toggle('bc-hidden', !matches);
    });
  }

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
        [...cards.querySelectorAll('.kanban-card')].forEach(c => c.remove());
        const empty = cards.querySelector('.kanban-empty');
        if (empty) empty.remove();
        const owned = allCards.filter(c => c.getAttribute('data-status') === status);
        if (owned.length === 0) {
          cards.innerHTML = '<div class="kanban-empty">' +
            '<div class="kanban-empty-glyph">·</div>' +
            '<div class="kanban-empty-msg">No tickets here</div>' +
            '</div>';
        } else {
          owned.forEach(c => cards.appendChild(c));
        }
        const count = col.querySelector('.count');
        const label = col.querySelector('.col-label');
        if (count) count.textContent = owned.length;
        if (label) label.textContent = status;
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
        buckets.get(v).push(card);
      });
    });
    const sortedKeys = [...buckets.keys()].sort((a, b) => {
      if (a === '(none)') return 1;
      if (b === '(none)') return -1;
      return a.localeCompare(b);
    });
    kanban.innerHTML = sortedKeys.map(k => {
      const cards = buckets.get(k);
      return `<div class="kanban-col" data-bucket="${k.replace(/"/g, '&quot;')}">
        <div class="kanban-col-header">
          <span class="col-label">${k}</span>
          <span class="count">${cards.length}</span>
        </div>
        <div class="kanban-cards"></div>
      </div>`;
    }).join('');
    sortedKeys.forEach(k => {
      const col = kanban.querySelector(`.kanban-col[data-bucket="${k.replace(/"/g, '&quot;')}"] .kanban-cards`);
      buckets.get(k).forEach(card => {
        col.appendChild(card.cloneNode(true));
      });
    });
  }

  // Render the active-filters chip strip from state.
  function bcRenderChips(state, panel) {
    const chips = panel.querySelector('#bc-chips');
    if (!chips) return;
    const entries = Object.entries(state.filter).filter(([, v]) => v);
    chips.innerHTML = entries.map(([axis, value]) => {
      const label = (BC_AXIS[axis] && BC_AXIS[axis].label) || axis;
      const safeAxis = String(axis).replace(/"/g, '&quot;');
      const safeVal = String(value).replace(/"/g, '&quot;').replace(/</g, '&lt;');
      return `<span class="bc-chip" data-axis="${safeAxis}">
        <span class="bc-chip-axis">${label}:</span>
        <span class="bc-chip-value">${safeVal}</span>
        <button type="button" class="bc-chip-remove" data-bc-chip-remove="${safeAxis}" aria-label="Remove ${label} filter">&times;</button>
      </span>`;
    }).join('');
  }

  function bcApply(state, panel) {
    bcApplyGroup(state);
    bcApplySort(state);
    bcApplyFilter(state);
    if (panel) bcRenderChips(state, panel);
  }

  // Add-filter popover: 2-step (axis → value), positioned under #bc-add-filter.
  function bcOpenPopover(panel, btn) {
    const pop = panel.querySelector('#bc-popover');
    if (!pop) return;
    pop.querySelector('[data-step="axis"]').hidden = false;
    pop.querySelector('[data-step="value"]').hidden = true;
    pop.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    // Position under the trigger inside the controls strip.
    const r = btn.getBoundingClientRect();
    const cr = panel.getBoundingClientRect();
    pop.style.left = (r.left - cr.left) + 'px';
    pop.style.top = (r.bottom - cr.top + 6) + 'px';
  }

  function bcClosePopover(panel) {
    const pop = panel.querySelector('#bc-popover');
    const btn = panel.querySelector('#bc-add-filter');
    if (!pop) return;
    pop.hidden = true;
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function bcShowAxisValues(panel, axis) {
    const pop = panel.querySelector('#bc-popover');
    if (!pop) return;
    const opts = bcCollectOptions()[axis] || [];
    const label = (BC_AXIS[axis] && BC_AXIS[axis].label) || axis;
    pop.querySelector('#bc-popover-axis-label').textContent = label;
    const list = pop.querySelector('#bc-popover-values');
    if (opts.length === 0) {
      list.innerHTML = '<div class="bc-popover-value-empty">No values available</div>';
    } else {
      list.innerHTML = opts.map(v =>
        `<button type="button" class="bc-popover-value" data-value="${String(v).replace(/"/g, '&quot;')}">${String(v).replace(/</g, '&lt;')}</button>`
      ).join('');
    }
    pop.querySelector('[data-step="axis"]').hidden = true;
    pop.querySelector('[data-step="value"]').hidden = false;
    pop.setAttribute('data-axis', axis);
  }

  function debounce(fn, wait) {
    let t = null;
    return function (...args) {
      if (t) clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  function initBoardControls() {
    const panel = document.getElementById('board-controls');
    if (!panel) return;

    const state = bcLoad();

    // Search
    const search = panel.querySelector('#bc-search');
    if (search) {
      search.value = state.search || '';
      const onSearch = debounce(() => {
        state.search = search.value;
        bcSave(state);
        bcApplyFilter(state);
      }, 120);
      search.addEventListener('input', onSearch);
    }

    // Sort
    const sortSel = panel.querySelector('[data-sort]');
    if (sortSel) {
      sortSel.value = state.sort;
      sortSel.addEventListener('change', () => {
        state.sort = sortSel.value;
        bcSave(state);
        bcApplySort(state);
      });
    }

    // Group
    const groupSel = panel.querySelector('[data-group]');
    if (groupSel) {
      groupSel.value = state.group;
      groupSel.addEventListener('change', () => {
        state.group = groupSel.value;
        bcSave(state);
        bcApply(state, panel);
      });
    }

    // Reset
    const reset = panel.querySelector('#bc-reset');
    if (reset) {
      reset.addEventListener('click', () => {
        const fresh = JSON.parse(JSON.stringify(BC_DEFAULT));
        bcSave(fresh);
        window.location.reload();
      });
    }

    // Add-filter popover
    const addBtn = panel.querySelector('#bc-add-filter');
    if (addBtn) {
      addBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const pop = panel.querySelector('#bc-popover');
        if (pop && !pop.hidden) bcClosePopover(panel);
        else bcOpenPopover(panel, addBtn);
      });
    }
    panel.addEventListener('click', (e) => {
      const axisBtn = e.target.closest('.bc-popover-axis');
      if (axisBtn) {
        bcShowAxisValues(panel, axisBtn.getAttribute('data-axis'));
        return;
      }
      const valBtn = e.target.closest('.bc-popover-value');
      if (valBtn) {
        const pop = panel.querySelector('#bc-popover');
        const axis = pop.getAttribute('data-axis');
        const value = valBtn.getAttribute('data-value');
        if (axis && value) {
          state.filter[axis] = value;
          bcSave(state);
          bcApply(state, panel);
        }
        bcClosePopover(panel);
        return;
      }
      const back = e.target.closest('#bc-popover-back');
      if (back) {
        const pop = panel.querySelector('#bc-popover');
        pop.querySelector('[data-step="axis"]').hidden = false;
        pop.querySelector('[data-step="value"]').hidden = true;
        return;
      }
      const remove = e.target.closest('[data-bc-chip-remove]');
      if (remove) {
        const axis = remove.getAttribute('data-bc-chip-remove');
        if (axis) {
          state.filter[axis] = '';
          bcSave(state);
          bcApply(state, panel);
        }
        return;
      }
    });

    // Click-away closes the popover
    document.addEventListener('click', (e) => {
      const pop = panel.querySelector('#bc-popover');
      if (!pop || pop.hidden) return;
      if (!pop.contains(e.target) && !e.target.closest('#bc-add-filter')) {
        bcClosePopover(panel);
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') bcClosePopover(panel);
    });

    bcApply(state, panel);
  }

  // Re-apply controls after the SSE handler swaps the kanban DOM.
  window.__reapplyBoardControls = function () {
    const panel = document.getElementById('board-controls');
    if (!panel) return;
    bcApply(bcLoad(), panel);
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
