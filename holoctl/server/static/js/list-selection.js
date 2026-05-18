import { showToast } from './toast.js';

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

export function initListSelection() {
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
