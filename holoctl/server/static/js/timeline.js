import { showToast } from './toast.js';
import { currentView } from './view-switcher.js';

// ── Timeline (roadmap) view ──

// Pixels per day per zoom level. Tuned for legibility:
//   day     → 1 day visible per ~64px (every day labelled)
//   week    → ~1 week visible per ~125px (ticks every week, day labels)
//   month   → ~1 month visible per ~150px (ticks every month)
//   quarter → ~1 quarter visible per ~200px (ticks every quarter, broad strokes)
const TL_ZOOM = {
  day:     { pxPerDay: 64, tickEveryDays: 1,  labelEveryDays: 1  },
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
      if (_tlZoom === 'day') {
        // Day mode: stack day-of-week over MMM DD so each tick reads
        // unambiguously without crowding (Mon / 07 May).
        const dow = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][cur.getDay()];
        tick.innerHTML = `<span class="tl-axis-tick-dow">${dow}</span><br>${_fmtDay(cur)} ${_fmtMonth(cur)}`;
      } else if (_tlZoom === 'week') {
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

export function initTimeline() {
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
