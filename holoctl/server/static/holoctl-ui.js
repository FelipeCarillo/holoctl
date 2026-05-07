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
    // Any of the three view containers anchors SSE.
    const anchor = document.getElementById('kanban')
                || document.getElementById('list-view')
                || document.getElementById('timeline-view');
    if (!anchor) return;

    const path = window.location.pathname;
    const match = path.match(/\/project\/([^/]+)\/board(?:\/[^/]+)?$/);
    // Skip on /board/<ticket-id> detail pages (no board there).
    if (!match) return;

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
        const fragmentUrl = (window.__boardFragmentUrl && window.__boardFragmentUrl(alias))
          || `/api/project/${alias}/board-html`;
        const resp = await fetch(fragmentUrl, { cache: 'no-store' });
        if (!resp.ok) return;
        const html = (await resp.text()).trim();
        const wrapper = document.createElement('div');
        wrapper.innerHTML = html;
        const fresh = wrapper.firstElementChild;
        const current = document.getElementById('kanban')
                     || document.getElementById('list-view')
                     || document.getElementById('timeline-view');
        if (fresh && current) current.replaceWith(fresh);
        // Reapply filter / sort / group state to the freshly-swapped DOM.
        if (window.__reapplyBoardControls) window.__reapplyBoardControls();
        // Timeline needs a render pass after every DOM swap (bars are
        // positioned by JS, not server).
        if (document.getElementById('timeline-view')) initTimeline();
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
    // Both views share the .kanban-card class on individual rows/cards;
    // their containers differ (.kanban-cards vs .list-group-rows).
    document.querySelectorAll('.kanban-cards, .list-group-rows').forEach(container => {
      const cards = [...container.querySelectorAll(':scope > .kanban-card, :scope > .ticket-row')];
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

  // ── Card hover menu (⋯) ──

  // Statuses come from the server via the kanban columns themselves —
  // honors per-project config without hardcoding the default 5.
  function statusList() {
    return [...document.querySelectorAll('.kanban-col[data-status]')]
      .map(col => col.getAttribute('data-status'))
      .filter((v, i, arr) => v && arr.indexOf(v) === i);
  }

  function projectAlias() {
    const m = window.location.pathname.match(/\/project\/([^/]+)\//);
    return m ? m[1] : null;
  }

  function closeCardMenu() {
    document.querySelectorAll('.kc-menu-popover').forEach(p => p.remove());
    document.querySelectorAll('.kc-menu[aria-expanded="true"]').forEach(b =>
      b.setAttribute('aria-expanded', 'false'));
  }

  function openCardMenu(btn, card) {
    closeCardMenu();
    // Card may be a .kanban-card ancestor (cards in any view) OR the button
    // itself when the menu lives outside a card (detail-page toolbar).
    const source = card || btn;
    const id = source.getAttribute('data-id');
    const currentStatus = source.getAttribute('data-status');
    const alias = projectAlias();
    if (!id || !alias) return;
    const statuses = statusList();
    const moveItems = statuses
      .filter(s => s !== currentStatus && s !== 'cancelled')
      .map(s => `<button type="button" class="kc-menu-item" data-action="move" data-status="${s}">
        <span class="kc-menu-status-dot" data-status="${s}"></span>
        Move to ${s}
      </button>`).join('');

    const pop = document.createElement('div');
    pop.className = 'kc-menu-popover';
    pop.setAttribute('role', 'menu');
    pop.dataset.cardId = id;
    pop.innerHTML = `
      <div class="kc-menu-section">Move</div>
      ${moveItems || '<div class="kc-menu-section" style="color:var(--text-3);font-weight:500;text-transform:none;letter-spacing:0;padding:4px 10px 6px">No other status</div>'}
      <div class="kc-menu-section">Card</div>
      <button type="button" class="kc-menu-item" data-action="open">
        <span aria-hidden="true">↗</span> Open detail
      </button>
      ${currentStatus !== 'cancelled' ? `<button type="button" class="kc-menu-item kc-menu-item-danger" data-action="archive">
        <span aria-hidden="true">✕</span> Archive (cancelled)
      </button>` : ''}
    `;
    document.body.appendChild(pop);
    btn.setAttribute('aria-expanded', 'true');

    // Position below the button. Flip above if too close to viewport bottom.
    const r = btn.getBoundingClientRect();
    pop.style.top = (window.scrollY + r.bottom + 4) + 'px';
    const desiredLeft = window.scrollX + r.right - pop.offsetWidth;
    pop.style.left = Math.max(8, desiredLeft) + 'px';
    if (r.bottom + pop.offsetHeight + 8 > window.innerHeight) {
      pop.style.top = (window.scrollY + r.top - pop.offsetHeight - 4) + 'px';
    }

    pop.addEventListener('click', async (e) => {
      const item = e.target.closest('.kc-menu-item');
      if (!item) return;
      e.stopPropagation();
      const action = item.getAttribute('data-action');
      const cardLink = document.querySelector(`.kanban-card[data-id="${id}"]`);
      const href = cardLink ? cardLink.getAttribute('href') : null;
      if (action === 'open' && href) {
        closeCardMenu();
        window.location.href = href;
        return;
      }
      if (action === 'move' || action === 'archive') {
        const target = action === 'archive' ? 'cancelled' : item.getAttribute('data-status');
        if (!target) return;
        item.disabled = true;
        try {
          const resp = await fetch(`/api/project/${encodeURIComponent(alias)}/tickets/${encodeURIComponent(id)}/move`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: target }),
          });
          if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            showToast(`Move failed: ${data.detail || resp.status}`);
          } else {
            showToast(`Moved to ${target}`);
          }
        } catch (err) {
          showToast(`Move failed: ${err.message || 'network'}`);
        } finally {
          closeCardMenu();
        }
      }
    });
  }

  function initCardMenus() {
    document.addEventListener('click', (e) => {
      const trigger = e.target.closest('[data-card-menu]');
      if (trigger) {
        // Inside an <a class="kanban-card">; preventDefault stops navigation,
        // stopPropagation stops the rest of the document handler closing the menu.
        e.preventDefault();
        e.stopPropagation();
        // Card menu can be inside a .kanban-card (kanban / list / timeline)
        // or stand alone (detail-page toolbar) — pass null in the latter
        // case so openCardMenu falls back to the trigger's own data-* attrs.
        const card = trigger.closest('.kanban-card');
        const wasOpen = trigger.getAttribute('aria-expanded') === 'true';
        if (wasOpen) closeCardMenu();
        else openCardMenu(trigger, card);
        return;
      }
      // Click anywhere else closes any open menu.
      if (!e.target.closest('.kc-menu-popover')) closeCardMenu();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeCardMenu();
    });
  }

  // ── Inline "+ Add ticket" form ──

  function closeAddForms() {
    document.querySelectorAll('.kanban-col-add-form').forEach(f => f.remove());
    document.querySelectorAll('.kanban-col-add[aria-expanded="true"]').forEach(b =>
      b.setAttribute('aria-expanded', 'false'));
  }

  function openAddForm(btn) {
    closeAddForms();
    const status = btn.getAttribute('data-status');
    const col = btn.closest('.kanban-col');
    if (!col || !status) return;
    btn.setAttribute('aria-expanded', 'true');

    const form = document.createElement('form');
    form.className = 'kanban-col-add-form';
    form.dataset.status = status;
    form.innerHTML = `
      <input type="text" name="title" placeholder="Ticket title…" autocomplete="off" required>
      <div class="kanban-col-add-form-error" data-error></div>
      <div class="kanban-col-add-form-row">
        <button type="button" class="btn btn-cancel" data-cancel>Cancel</button>
        <button type="submit" class="btn btn-primary" data-submit>Add ticket</button>
      </div>
    `;
    col.appendChild(form);
    const input = form.querySelector('input[name="title"]');
    input.focus();

    form.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeAddForms();
      }
    });
    form.querySelector('[data-cancel]').addEventListener('click', closeAddForms);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const title = (input.value || '').trim();
      if (!title) return;
      const errEl = form.querySelector('[data-error]');
      const submitBtn = form.querySelector('[data-submit]');
      errEl.textContent = '';
      submitBtn.disabled = true;
      const alias = projectAlias();
      try {
        const resp = await fetch(`/api/project/${encodeURIComponent(alias)}/tickets`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, status }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          errEl.textContent = data.detail || `Error ${resp.status}`;
          submitBtn.disabled = false;
          return;
        }
        showToast(`Created ${data.id || 'ticket'}`);
        // SSE will swap the kanban DOM in shortly; close the form so it
        // doesn't get orphaned by the swap.
        closeAddForms();
      } catch (err) {
        errEl.textContent = err.message || 'Network error';
        submitBtn.disabled = false;
      }
    });
  }

  function initInlineAdd() {
    document.addEventListener('click', (e) => {
      const trigger = e.target.closest('[data-add-ticket]');
      if (trigger) {
        e.preventDefault();
        const wasOpen = trigger.getAttribute('aria-expanded') === 'true';
        if (wasOpen) closeAddForms();
        else openAddForm(trigger);
        return;
      }
      // Header-level "+ New ticket" CTA — defers to the first column's add.
      const newCta = e.target.closest('[data-new-ticket]');
      if (newCta) {
        e.preventDefault();
        const first = document.querySelector('[data-add-ticket]');
        if (first) {
          first.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          openAddForm(first);
        }
      }
    });
  }

  // ── View switcher: kanban ↔ list ──

  function currentView() {
    const panel = document.getElementById('board-controls');
    if (panel && panel.dataset.currentView) return panel.dataset.currentView;
    const url = new URL(window.location.href);
    return url.searchParams.get('view') || 'kanban';
  }

  function initViewSwitcher() {
    const switcher = document.querySelector('.view-switcher');
    if (!switcher) return;
    switcher.addEventListener('click', (e) => {
      const tab = e.target.closest('.view-tab');
      if (!tab || tab.disabled || tab.classList.contains('active')) return;
      const view = tab.getAttribute('data-view');
      if (!view) return;
      const url = new URL(window.location.href);
      url.searchParams.set('view', view);
      // Full navigation — easiest way to swap server-rendered structure +
      // re-init JS without a partial-update juggling act.
      window.location.href = url.toString();
    });
  }

  // ── List-view multi-select + bulk action bar ──

  function listRows() {
    return [...document.querySelectorAll('.list-body .ticket-row')];
  }

  function selectedRows() {
    return listRows().filter(r => r.dataset.selected === 'true');
  }

  let _lastClickedRow = null;

  function updateBulkBar() {
    const bar = document.getElementById('list-bulk-bar');
    if (!bar) return;
    const sel = selectedRows();
    if (sel.length === 0) {
      bar.hidden = true;
    } else {
      bar.hidden = false;
      const count = bar.querySelector('#lbb-count');
      if (count) count.textContent = `${sel.length} selected`;
    }
    // Sync the "select all" checkbox state with the population.
    const all = document.querySelector('[data-ticket-select-all]');
    if (all) {
      const rows = listRows();
      const visible = rows.filter(r => !r.classList.contains('bc-hidden'));
      const sels = visible.filter(r => r.dataset.selected === 'true');
      all.checked = visible.length > 0 && sels.length === visible.length;
      all.indeterminate = sels.length > 0 && sels.length < visible.length;
    }
  }

  function setRowSelected(row, selected) {
    if (!row) return;
    if (selected) row.dataset.selected = 'true';
    else delete row.dataset.selected;
    const cb = row.querySelector('[data-ticket-select]');
    if (cb) cb.checked = !!selected;
  }

  function clearSelection() {
    listRows().forEach(r => setRowSelected(r, false));
    _lastClickedRow = null;
    updateBulkBar();
  }

  function projectAliasOrThrow() {
    const a = projectAlias();
    if (!a) throw new Error('No project alias on this page');
    return a;
  }

  async function moveTicket(id, status) {
    const alias = projectAliasOrThrow();
    const resp = await fetch(`/api/project/${encodeURIComponent(alias)}/tickets/${encodeURIComponent(id)}/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || `move failed (${resp.status})`);
    }
    return resp.json();
  }

  async function patchTicket(id, field, value) {
    const alias = projectAliasOrThrow();
    const resp = await fetch(`/api/project/${encodeURIComponent(alias)}/tickets/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field, value }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || `patch failed (${resp.status})`);
    }
    return resp.json();
  }

  async function bulkMove(targetStatus) {
    const sel = selectedRows();
    if (sel.length === 0) return;
    let ok = 0, fail = 0;
    // Sequential so a single failure doesn't get drowned in noise.
    for (const row of sel) {
      const id = row.getAttribute('data-id');
      try { await moveTicket(id, targetStatus); ok += 1; }
      catch (e) { fail += 1; showToast(`Move ${id}: ${e.message}`); }
    }
    showToast(`Moved ${ok} ticket${ok === 1 ? '' : 's'}${fail ? ` (${fail} failed)` : ''}`);
    clearSelection();
  }

  function initListSelection() {
    document.addEventListener('click', (e) => {
      const cb = e.target.closest('[data-ticket-select]');
      if (cb) {
        const row = cb.closest('.ticket-row');
        if (!row) return;
        // Shift+Click → select range from last-clicked to this row.
        const wantSelected = cb.checked;
        if (e.shiftKey && _lastClickedRow) {
          const rows = listRows();
          const a = rows.indexOf(_lastClickedRow);
          const b = rows.indexOf(row);
          if (a >= 0 && b >= 0) {
            const [lo, hi] = a < b ? [a, b] : [b, a];
            for (let i = lo; i <= hi; i++) {
              if (!rows[i].classList.contains('bc-hidden')) {
                setRowSelected(rows[i], wantSelected);
              }
            }
          }
        } else {
          setRowSelected(row, wantSelected);
        }
        _lastClickedRow = row;
        updateBulkBar();
        return;
      }
      const all = e.target.closest('[data-ticket-select-all]');
      if (all) {
        const rows = listRows().filter(r => !r.classList.contains('bc-hidden'));
        rows.forEach(r => setRowSelected(r, all.checked));
        updateBulkBar();
        return;
      }
      const move = e.target.closest('[data-bulk-move]');
      if (move) {
        bulkMove(move.getAttribute('data-status'));
        return;
      }
      const archive = e.target.closest('[data-bulk-archive]');
      if (archive) {
        bulkMove('cancelled');
        return;
      }
      const clear = e.target.closest('[data-bulk-clear]');
      if (clear) {
        clearSelection();
        return;
      }
      // Group header collapses on click (avoid swallowing checkbox clicks).
      const groupHdr = e.target.closest('.list-group-header');
      if (groupHdr) {
        const group = groupHdr.closest('.list-group');
        if (!group) return;
        const collapsed = group.dataset.collapsed === 'true';
        if (collapsed) delete group.dataset.collapsed;
        else group.dataset.collapsed = 'true';
        groupHdr.setAttribute('aria-expanded', collapsed ? 'true' : 'false');
        return;
      }
    });
  }

  // ── Inline edit popover (status / priority) ──

  const PRIORITIES = ['p0', 'p1', 'p2', 'p3'];

  function closeEditPopover() {
    document.querySelectorAll('.lr-edit-popover').forEach(p => p.remove());
    document.querySelectorAll('.lr-edit[aria-expanded="true"]').forEach(b =>
      b.setAttribute('aria-expanded', 'false'));
  }

  function openEditPopover(btn) {
    closeEditPopover();
    const field = btn.getAttribute('data-edit-field');
    if (!field) return;
    // Trigger lives inside a list-view row (.ticket-row), inside a
    // detail-page row container (.detail-header-row / .dr-card), or
    // is a stand-alone toolbar button carrying its own data-id.
    const owner = btn.closest('[data-detail-row], .ticket-row, [data-id]');
    if (!owner) return;
    const id = owner.getAttribute('data-id');
    if (!id) return;
    let options;
    let current;
    if (field === 'status') {
      options = statusList();
      current = btn.getAttribute('data-status');
    } else if (field === 'priority') {
      options = PRIORITIES;
      current = btn.getAttribute('data-p');
    } else {
      return;
    }
    const pop = document.createElement('div');
    pop.className = 'lr-edit-popover';
    pop.setAttribute('role', 'menu');
    pop.innerHTML = options.map(v =>
      `<button type="button" class="lr-edit-option" data-value="${v}" ${v === current ? 'aria-current="true"' : ''}>
        ${field === 'status' ? `<span class="kc-menu-status-dot" data-status="${v}"></span>` : ''}
        ${v}
      </button>`
    ).join('');
    document.body.appendChild(pop);
    btn.setAttribute('aria-expanded', 'true');
    const r = btn.getBoundingClientRect();
    pop.style.top = (window.scrollY + r.bottom + 4) + 'px';
    pop.style.left = Math.max(8, window.scrollX + r.left) + 'px';
    if (r.bottom + pop.offsetHeight + 8 > window.innerHeight) {
      pop.style.top = (window.scrollY + r.top - pop.offsetHeight - 4) + 'px';
    }
    pop.addEventListener('click', async (e) => {
      const opt = e.target.closest('.lr-edit-option');
      if (!opt) return;
      e.stopPropagation();
      const value = opt.getAttribute('data-value');
      if (value === current) { closeEditPopover(); return; }
      opt.disabled = true;
      try {
        if (field === 'status') {
          await moveTicket(id, value); // /move handles status changes (recounts)
        } else {
          await patchTicket(id, field, value);
        }
        showToast(`${field}: ${value}`);
      } catch (err) {
        showToast(`Update failed: ${err.message}`);
      } finally {
        closeEditPopover();
      }
    });
  }

  // Free-form text edit popover (sprint / tags / agent CSV) — used by
  // the detail page's right rail. Saves via PATCH; agent CSV strings are
  // server-parsed by Board.set's _normalize_array.
  function closeTextEditPopover() {
    document.querySelectorAll('.lr-edit-text-popover').forEach(p => p.remove());
    document.querySelectorAll('[data-edit-text-field][aria-expanded="true"]').forEach(b =>
      b.setAttribute('aria-expanded', 'false'));
  }

  function openTextEditPopover(btn) {
    closeTextEditPopover();
    closeEditPopover();
    const field = btn.getAttribute('data-edit-text-field');
    const current = btn.getAttribute('data-current') || '';
    if (!field) return;
    // Detail page is the only host today, so the parent row carries the id.
    const row = btn.closest('[data-detail-row], [data-id]');
    const id = row ? row.getAttribute('data-id') : null;
    if (!id) return;

    const labelText = {
      agent:    'Agents (comma-separated)',
      sprint:   'Sprint',
      tags:     'Tags (comma-separated)',
      projects: 'Repo / projects (comma-separated)',
    }[field] || field;
    const hintText = {
      agent:    'Use names from active agents (e.g. developer, reviewer)',
      sprint:   'Free-form sprint name (e.g. sprint-1)',
      tags:     'Free-form, comma-separated',
      projects: 'Subprojects this ticket touches (e.g. backend, web)',
    }[field] || '';

    const pop = document.createElement('div');
    pop.className = 'lr-edit-text-popover';
    pop.setAttribute('role', 'dialog');
    pop.innerHTML = `
      <div class="lr-edit-text-popover-label">${labelText}</div>
      <input type="text" value="${String(current).replace(/"/g, '&quot;')}" autocomplete="off" spellcheck="false">
      ${hintText ? `<div class="lr-edit-text-popover-hint">${hintText}</div>` : ''}
      <div class="lr-edit-text-popover-error" data-error></div>
      <div class="lr-edit-text-popover-row">
        <button type="button" class="btn-sm" data-cancel>Cancel</button>
        <button type="submit" class="btn-sm btn-primary" data-save>Save</button>
      </div>
    `;
    document.body.appendChild(pop);
    btn.setAttribute('aria-expanded', 'true');
    const r = btn.getBoundingClientRect();
    pop.style.top = (window.scrollY + r.bottom + 4) + 'px';
    pop.style.left = Math.max(8, window.scrollX + r.left) + 'px';
    if (r.bottom + pop.offsetHeight + 8 > window.innerHeight) {
      pop.style.top = (window.scrollY + r.top - pop.offsetHeight - 4) + 'px';
    }
    const input = pop.querySelector('input');
    input.focus();
    input.select();

    async function save() {
      const raw = input.value.trim();
      const errEl = pop.querySelector('[data-error]');
      errEl.textContent = '';
      const saveBtn = pop.querySelector('[data-save]');
      saveBtn.disabled = true;
      // Multi-value fields get sent as a JSON array so Board.set's
      // normalizer treats them as lists (and validates agents).
      let value;
      if (field === 'agent' || field === 'tags' || field === 'projects') {
        value = raw === '' ? [] : raw.split(',').map(s => s.trim()).filter(Boolean);
      } else {
        value = raw === '' ? null : raw;
      }
      try {
        await patchTicket(id, field, value);
        showToast(`${field} updated`);
        closeTextEditPopover();
        // Trigger a quick re-render of the page: SSE will pick the change
        // up within ~2s, but a full reload feels snappier on the detail
        // page where most edits happen.
        setTimeout(() => window.location.reload(), 250);
      } catch (err) {
        errEl.textContent = err.message || 'Update failed';
        saveBtn.disabled = false;
      }
    }

    pop.querySelector('[data-save]').addEventListener('click', save);
    pop.querySelector('[data-cancel]').addEventListener('click', closeTextEditPopover);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); save(); }
      if (e.key === 'Escape') { e.preventDefault(); closeTextEditPopover(); }
    });
  }

  function initInlineEdit() {
    document.addEventListener('click', (e) => {
      const trigger = e.target.closest('.lr-edit');
      if (trigger) {
        e.preventDefault();
        e.stopPropagation();
        const wasOpen = trigger.getAttribute('aria-expanded') === 'true';
        if (wasOpen) closeEditPopover();
        else openEditPopover(trigger);
        return;
      }
      const textTrigger = e.target.closest('[data-edit-text-field]');
      if (textTrigger) {
        e.preventDefault();
        e.stopPropagation();
        const wasOpen = textTrigger.getAttribute('aria-expanded') === 'true';
        if (wasOpen) closeTextEditPopover();
        else openTextEditPopover(textTrigger);
        return;
      }
      if (!e.target.closest('.lr-edit-popover')) closeEditPopover();
      if (!e.target.closest('.lr-edit-text-popover')) closeTextEditPopover();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeEditPopover();
        closeTextEditPopover();
      }
    });
  }

  // ── Timeline (roadmap) view ──

  // Pixels per day per zoom level. Tuned for legibility:
  //   week    → ~1 week visible per ~125px (ticks every week, day labels)
  //   month   → ~1 month visible per ~150px (ticks every month)
  //   quarter → ~1 quarter visible per ~200px (ticks every quarter, broad strokes)
  const TL_ZOOM = {
    week:    { pxPerDay: 18, tickEveryDays: 7,  labelEveryDays: 7  },
    month:   { pxPerDay: 5,  tickEveryDays: 7,  labelEveryDays: 30 },
    quarter: { pxPerDay: 2,  tickEveryDays: 30, labelEveryDays: 90 },
  };
  let _tlZoom = 'month';
  let _tlOrigin = null; // Date — left edge of the timeline
  let _tlEnd = null;    // Date — right edge

  function _parseISO(s) {
    if (!s) return null;
    const d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }

  function _startOfDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  function _addDays(d, n) {
    const x = new Date(d);
    x.setDate(x.getDate() + n);
    return x;
  }

  function _daysBetween(a, b) {
    return Math.round((b - a) / (24 * 3600 * 1000));
  }

  function _fmtDay(d)   { return ('0' + d.getDate()).slice(-2); }
  function _fmtMonth(d) {
    return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()];
  }
  function _fmtQuarter(d) { return 'Q' + (Math.floor(d.getMonth() / 3) + 1) + ' ' + d.getFullYear(); }

  function _tlComputeRange() {
    const rows = [...document.querySelectorAll('#timeline .tl-row')];
    let min = null, max = null;
    rows.forEach(r => {
      const c = _parseISO(r.getAttribute('data-created'));
      if (c && (!min || c < min)) min = c;
      const done = _parseISO(r.getAttribute('data-completed'));
      const end = done || new Date();
      if (!max || end > max) max = end;
    });
    const today = new Date();
    if (!min) min = _addDays(today, -14);
    if (!max) max = today;
    // Pad a little on each side so today doesn't sit on the edge.
    min = _addDays(_startOfDay(min), -3);
    max = _addDays(_startOfDay(max), 7);
    return { min, max };
  }

  function _tlRenderAxis() {
    const axis = document.getElementById('tl-axis');
    if (!axis) return;
    axis.innerHTML = '';
    const z = TL_ZOOM[_tlZoom];
    const totalDays = _daysBetween(_tlOrigin, _tlEnd);
    const totalPx = totalDays * z.pxPerDay;
    axis.style.width = totalPx + 'px';
    // Draw ticks at z.tickEveryDays, with a label every z.labelEveryDays.
    let cur = new Date(_tlOrigin);
    while (cur <= _tlEnd) {
      const offsetDays = _daysBetween(_tlOrigin, cur);
      const left = offsetDays * z.pxPerDay;
      const isLabel = offsetDays % z.labelEveryDays === 0;
      const tick = document.createElement('div');
      tick.className = 'tl-axis-tick' + (isLabel ? ' tl-axis-tick-major' : '');
      tick.style.left = left + 'px';
      if (isLabel) {
        if (_tlZoom === 'week') {
          tick.textContent = `${_fmtMonth(cur)} ${_fmtDay(cur)}`;
        } else if (_tlZoom === 'month') {
          tick.textContent = `${_fmtMonth(cur)} ${cur.getFullYear()}`;
        } else {
          tick.textContent = _fmtQuarter(cur);
        }
      }
      axis.appendChild(tick);
      cur = _addDays(cur, z.tickEveryDays);
    }
  }

  function _tlRenderBars() {
    const z = TL_ZOOM[_tlZoom];
    const totalDays = _daysBetween(_tlOrigin, _tlEnd);
    const totalPx = totalDays * z.pxPerDay;
    const tl = document.getElementById('timeline');
    if (tl) {
      tl.style.setProperty('--tl-track-w', totalPx + 'px');
    }
    const today = _startOfDay(new Date());
    document.querySelectorAll('#timeline .tl-row').forEach(row => {
      const track = row.querySelector('[data-track]');
      if (!track) return;
      track.innerHTML = '';
      const created = _parseISO(row.getAttribute('data-created'));
      if (!created) return;
      const completedRaw = row.getAttribute('data-completed');
      const completed = completedRaw ? _parseISO(completedRaw) : null;
      const end = completed || today;
      const startDay = _daysBetween(_tlOrigin, _startOfDay(created));
      const endDay = _daysBetween(_tlOrigin, _startOfDay(end));
      const left = startDay * z.pxPerDay;
      const width = Math.max(8, (endDay - startDay) * z.pxPerDay);
      const status = row.getAttribute('data-status') || 'backlog';
      const title = row.getAttribute('data-title') || '';
      const id = row.getAttribute('data-id') || '';
      const bar = document.createElement('a');
      bar.className = 'tl-bar';
      bar.setAttribute('data-status', status);
      bar.setAttribute('data-bar', '');
      bar.style.left = left + 'px';
      bar.style.width = width + 'px';
      const alias = projectAlias();
      if (alias && id) bar.href = `/project/${encodeURIComponent(alias)}/board/${encodeURIComponent(id)}`;
      // Only show the label inside the bar if we have ~40+px to spare;
      // otherwise the tooltip on hover carries the full info.
      if (width > 40) {
        const span = document.createElement('span');
        span.className = 'tl-bar-label';
        span.textContent = `${id} · ${title}`;
        bar.appendChild(span);
      }
      bar.dataset.id = id;
      bar.dataset.title = title;
      bar.dataset.created = row.getAttribute('data-created') || '';
      bar.dataset.completed = completedRaw || '';
      track.appendChild(bar);
    });
  }

  function _tlRenderTodayLine() {
    const line = document.getElementById('tl-today-line');
    const tl = document.getElementById('timeline');
    if (!line || !tl) return;
    const z = TL_ZOOM[_tlZoom];
    const today = _startOfDay(new Date());
    if (today < _tlOrigin || today > _tlEnd) {
      line.hidden = true;
      return;
    }
    const offsetDays = _daysBetween(_tlOrigin, today);
    const px = offsetDays * z.pxPerDay;
    // Account for the sticky-left name column width.
    const nameCol = parseInt(getComputedStyle(tl).getPropertyValue('--tl-name-w')) || 240;
    line.style.left = (nameCol + px) + 'px';
    line.hidden = false;
  }

  function _tlScrollToToday() {
    const tl = document.getElementById('timeline');
    if (!tl) return;
    const z = TL_ZOOM[_tlZoom];
    const today = _startOfDay(new Date());
    const px = _daysBetween(_tlOrigin, today) * z.pxPerDay;
    const nameCol = parseInt(getComputedStyle(tl).getPropertyValue('--tl-name-w')) || 240;
    tl.scrollLeft = Math.max(0, nameCol + px - tl.clientWidth / 2);
  }

  // Hover tooltip — reads bar metadata, positions near the cursor.
  function _tlInitHover() {
    let tooltip = null;
    const tl = document.getElementById('timeline');
    if (!tl) return;
    function ensureTooltip() {
      if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.className = 'tl-bar-tooltip';
        tooltip.hidden = true;
        document.body.appendChild(tooltip);
      }
      return tooltip;
    }
    tl.addEventListener('mousemove', (e) => {
      const bar = e.target.closest('.tl-bar');
      if (!bar) {
        if (tooltip) tooltip.hidden = true;
        return;
      }
      const tt = ensureTooltip();
      const id = bar.dataset.id || '';
      const title = bar.dataset.title || '';
      const status = bar.getAttribute('data-status') || '';
      const created = bar.dataset.created || '';
      const completed = bar.dataset.completed || '';
      tt.innerHTML = `
        <div class="tl-bar-tooltip-title">${title.replace(/</g, '&lt;')}</div>
        <div class="tl-bar-tooltip-meta">
          <span>${id}</span>
          <span>${status}</span>
          <span>${created.slice(0,10)}${completed ? ' → ' + completed.slice(0,10) : ''}</span>
        </div>`;
      tt.hidden = false;
      tt.style.left = (e.pageX + 12) + 'px';
      tt.style.top = (e.pageY + 12) + 'px';
    });
    tl.addEventListener('mouseleave', () => {
      if (tooltip) tooltip.hidden = true;
    });
  }

  function _tlRenderAll() {
    const view = document.getElementById('timeline-view');
    if (!view) return;
    const range = _tlComputeRange();
    _tlOrigin = range.min;
    _tlEnd = range.max;
    _tlRenderAxis();
    _tlRenderBars();
    _tlRenderTodayLine();
  }

  function initTimeline() {
    const view = document.getElementById('timeline-view');
    if (!view) return;
    _tlRenderAll();
    // Auto-scroll to put today near the middle on first load.
    requestAnimationFrame(_tlScrollToToday);
    _tlInitHover();

    // Zoom switcher
    view.querySelectorAll('[data-tl-zoom]').forEach(btn => {
      btn.addEventListener('click', () => {
        const z = btn.getAttribute('data-tl-zoom');
        if (!z || z === _tlZoom || !TL_ZOOM[z]) return;
        _tlZoom = z;
        view.querySelectorAll('[data-tl-zoom]').forEach(b => {
          const active = b === btn;
          b.classList.toggle('active', active);
          b.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        _tlRenderAll();
      });
    });

    // Group-by select — re-fetches the timeline shell with the new axis.
    const groupSel = view.querySelector('[data-tl-group]');
    if (groupSel) {
      groupSel.addEventListener('change', async () => {
        const alias = projectAlias();
        if (!alias) return;
        try {
          const resp = await fetch(`/api/project/${encodeURIComponent(alias)}/timeline-html?group=${encodeURIComponent(groupSel.value)}`, {
            cache: 'no-store',
          });
          if (!resp.ok) { showToast(`Failed to regroup (${resp.status})`); return; }
          const html = (await resp.text()).trim();
          const wrapper = document.createElement('div');
          wrapper.innerHTML = html;
          const fresh = wrapper.firstElementChild;
          const current = document.getElementById('timeline-view');
          if (fresh && current) {
            current.replaceWith(fresh);
            initTimeline(); // re-bind on the new shell
          }
        } catch (err) { showToast(`Regroup failed: ${err.message || 'network'}`); }
      });
    }

    // Lane collapse on header click
    view.querySelectorAll('.tl-lane-header').forEach(h => {
      h.addEventListener('click', () => {
        const lane = h.closest('.tl-lane');
        if (!lane) return;
        const collapsed = lane.dataset.collapsed === 'true';
        if (collapsed) delete lane.dataset.collapsed;
        else lane.dataset.collapsed = 'true';
        h.setAttribute('aria-expanded', collapsed ? 'true' : 'false');
      });
    });

    // Jump to today
    const jump = view.querySelector('[data-tl-today]');
    if (jump) jump.addEventListener('click', _tlScrollToToday);
  }

  // Re-pos bars when the user resizes the window (sticky width var depends
  // on the date range, not viewport, but bar widths benefit from a redraw).
  let _tlResizeT = null;
  window.addEventListener('resize', () => {
    if (!document.getElementById('timeline-view')) return;
    if (_tlResizeT) clearTimeout(_tlResizeT);
    _tlResizeT = setTimeout(_tlRenderAll, 120);
  });

  // SSE: pick the right fragment endpoint per current view.
  window.__boardFragmentUrl = function (alias) {
    const view = currentView();
    if (view === 'list') return `/api/project/${encodeURIComponent(alias)}/list-html`;
    if (view === 'timeline') {
      const tlView = document.getElementById('timeline-view');
      const group = (tlView && tlView.dataset.group) || 'sprint';
      return `/api/project/${encodeURIComponent(alias)}/timeline-html?group=${encodeURIComponent(group)}`;
    }
    return `/api/project/${encodeURIComponent(alias)}/board-html`;
  };

  // ── Init ──

  // Keyboard activation for elements with role="button" — Enter/Space
  // dispatch a synthetic click. Native <button>/<a> already do this; this
  // covers the few <div role="button"> headers (group/lane collapsers)
  // that we couldn't make actual buttons due to grid layout.
  function initRoleButtonKeys() {
    document.addEventListener('keydown', (e) => {
      const el = e.target.closest('[role="button"]');
      if (!el || el.tagName === 'BUTTON' || el.tagName === 'A') return;
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        el.click();
      }
    });
  }

  initTheme();

  document.addEventListener('DOMContentLoaded', () => {
    initSSE();
    initTabs();
    initStagger();
    initFileTree();
    initBoardControls();
    initCardMenus();
    initInlineAdd();
    initViewSwitcher();
    initListSelection();
    initInlineEdit();
    initTimeline();
    initRoleButtonKeys();
  });
})();
