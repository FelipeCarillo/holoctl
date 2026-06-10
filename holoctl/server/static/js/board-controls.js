// ── Board controls: search, filter chips, sort, group ──

import { esc } from './dom.js';
import { debounce } from './util.js';

// Per-workspace state in localStorage. Bumped to v2 because the schema
// changed (added .search, .filter shape preserved). Old v1 state is left
// alone — agents who had it just see defaults until they touch a control.
function bcStorageKey() {
  const m = window.location.pathname.match(/\/project\/([^/]+)\/board/);
  return m ? `holoctl-bc-v2:${m[1]}` : null;
}

const BC_DEFAULT = {
  search: '',
  filter: { status: '', priority: '', agent: '', sprint: '', tag: '', project: '', kind: '', source: '' },
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
  kind:     { label: 'Kind',     attr: 'kind',     multi: false },
  source:   { label: 'Source',   attr: 'source',   multi: false },
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
  } catch {
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

// Axis name → data-* attribute used by the card markup.
const BC_GROUP_ATTR = { priority: 'p', sprint: 'sprint', agent: 'agent', tag: 'tags', project: 'projects', kind: 'kind' };
// Axes where a comma-separated list means "ticket belongs to multiple buckets".
const BC_GROUP_MULTI = new Set(['agent', 'tags', 'projects']);

function bcBucketKeys(card, axisAttr) {
  const raw = card.getAttribute('data-' + axisAttr) || '';
  if (BC_GROUP_MULTI.has(axisAttr)) {
    const parts = raw.split(',').filter(Boolean);
    return parts.length ? parts : ['(none)'];
  }
  return [raw || '(none)'];
}

function bcSortBucketKeys(keys) {
  return [...keys].sort((a, b) => {
    if (a === '(none)') return 1;
    if (b === '(none)') return -1;
    return a.localeCompare(b);
  });
}

function bcApplyGroup(state) {
  const kanban = document.getElementById('kanban');
  if (kanban) return bcApplyGroupKanban(state, kanban);
  const listView = document.getElementById('list-view');
  if (listView) return bcApplyGroupList(state, listView);
  // tree: group select is hidden by the server template; nothing to do.
}

function bcApplyGroupKanban(state, kanban) {
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
  const axisAttr = BC_GROUP_ATTR[state.group];
  if (!axisAttr) return;
  const buckets = new Map();
  allCards.forEach(card => {
    bcBucketKeys(card, axisAttr).forEach(v => {
      if (!buckets.has(v)) buckets.set(v, []);
      buckets.get(v).push(card);
    });
  });
  const sortedKeys = bcSortBucketKeys(buckets.keys());
  kanban.innerHTML = sortedKeys.map(k => {
    const cards = buckets.get(k);
    return `<div class="kanban-col" data-bucket="${esc(k)}">
      <div class="kanban-col-header">
        <span class="col-label">${esc(k)}</span>
        <span class="count">${cards.length}</span>
      </div>
      <div class="kanban-cards"></div>
    </div>`;
  }).join('');
  // Append cards by column index (positional) rather than re-querying by an
  // escaped attribute selector — the DOM attribute value is the *unescaped*
  // key, so a selector built from esc(k) would miss keys containing markup.
  const cols = kanban.querySelectorAll('.kanban-col .kanban-cards');
  sortedKeys.forEach((k, i) => {
    const target = cols[i];
    if (!target) return;
    buckets.get(k).forEach(card => target.appendChild(card.cloneNode(true)));
  });
}

// List view: dissolve the server-rendered .list-group buckets (one per status)
// and rebuild them by the chosen axis. `state.group === 'status'` puts things
// back where they started — read from each row's data-status, not from the
// existing group containers (those may already have been reorganized).
function bcApplyGroupList(state, listView) {
  const body = listView.querySelector('#list-body') || listView.querySelector('.list-body');
  if (!body) return;
  const allRows = [...listView.querySelectorAll('.ticket-row')];
  let axis, axisAttr, sortKeys;
  if (state.group === 'status') {
    axis = 'status';
    axisAttr = 'status';
    // Keep the original status order from the server-rendered groups so
    // backlog → doing → review → done → cancelled stays predictable.
    const originalOrder = [...listView.querySelectorAll('.list-group')]
      .map(g => g.getAttribute('data-bucket'));
    sortKeys = (keys) => {
      const set = new Set(keys);
      const inOrder = originalOrder.filter(k => set.has(k));
      const extras = [...keys].filter(k => !originalOrder.includes(k)).sort();
      return [...inOrder, ...extras];
    };
  } else {
    axisAttr = BC_GROUP_ATTR[state.group];
    if (!axisAttr) return;
    axis = state.group;
    sortKeys = bcSortBucketKeys;
  }
  const buckets = new Map();
  allRows.forEach(row => {
    const keys = (axis === 'status')
      ? [row.getAttribute('data-status') || '(none)']
      : bcBucketKeys(row, axisAttr);
    keys.forEach(v => {
      if (!buckets.has(v)) buckets.set(v, []);
      buckets.get(v).push(row);
    });
  });
  const orderedKeys = sortKeys([...buckets.keys()]);
  body.innerHTML = orderedKeys.map(k => {
    const safe = esc(k);
    return `<div class="list-group" data-bucket="${safe}">
      <div class="list-group-header" data-status="${safe}" role="button" tabindex="0" aria-expanded="true" aria-label="Toggle ${safe} group">
        <span class="lg-toggle" aria-hidden="true">▾</span>
        <span class="lg-label">${safe}</span>
        <span class="lg-count">${buckets.get(k).length}</span>
      </div>
      <div class="list-group-rows"></div>
    </div>`;
  }).join('');
  // Positional append (see bcApplyGroupKanban) — avoids escaped-selector mismatch.
  const groupRows = body.querySelectorAll('.list-group .list-group-rows');
  orderedKeys.forEach((k, i) => {
    const rowsEl = groupRows[i];
    if (!rowsEl) return;
    buckets.get(k).forEach(row => rowsEl.appendChild(row.cloneNode(true)));
  });
}

// Render the active-filters chip strip from state.
function bcRenderChips(state, panel) {
  const chips = panel.querySelector('#bc-chips');
  if (!chips) return;
  const entries = Object.entries(state.filter).filter(([, v]) => v);
  chips.innerHTML = entries.map(([axis, value]) => {
    const label = (BC_AXIS[axis] && BC_AXIS[axis].label) || axis;
    const safeAxis = esc(axis);
    const safeVal = esc(value);
    const safeLabel = esc(label);
    return `<span class="bc-chip" data-axis="${safeAxis}">
      <span class="bc-chip-axis">${safeLabel}:</span>
      <span class="bc-chip-value">${safeVal}</span>
      <button type="button" class="bc-chip-remove" data-bc-chip-remove="${safeAxis}" aria-label="Remove ${safeLabel} filter">&times;</button>
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
      `<button type="button" class="bc-popover-value" data-value="${esc(v)}">${esc(v)}</button>`
    ).join('');
  }
  pop.querySelector('[data-step="axis"]').hidden = true;
  pop.querySelector('[data-step="value"]').hidden = false;
  pop.setAttribute('data-axis', axis);
}

export function initBoardControls() {
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
