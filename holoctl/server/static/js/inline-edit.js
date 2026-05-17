import { showToast } from './toast.js';
import { statusList } from './card-menu.js';

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

export function initInlineEdit() {
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
