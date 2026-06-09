import { showToast } from './toast.js';
import { statusList } from './card-menu.js';
import { esc } from './dom.js';
import { moveTicket, patchTicket } from './api.js';
import { positionPopover } from './popover.js';

// ── Inline edit popover (status / priority) ──

const PRIORITIES = ['p0', 'p1', 'p2', 'p3'];

// Trigger that opened the current popover — focus returns here on close.
let _editTrigger = null;
let _textTrigger = null;

// Reflect a saved status/priority on its trigger button in-place. Value pills
// (list rows, detail properties) render the bare value as their text; static
// labels like the toolbar "Move ▾" carry a "▾" glyph and must be left alone.
function applyButtonValue(btn, newValue) {
  const text = btn.textContent.trim();
  if (text.includes('▾')) return;
  btn.textContent = newValue;
}

function closeEditPopover() {
  document.querySelectorAll('.lr-edit-popover').forEach(p => p.remove());
  document.querySelectorAll('.lr-edit[aria-expanded="true"]').forEach(b =>
    b.setAttribute('aria-expanded', 'false'));
  if (_editTrigger) {
    const t = _editTrigger;
    _editTrigger = null;
    if (document.contains(t)) t.focus();
  }
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
    `<button type="button" class="lr-edit-option" data-value="${esc(v)}" ${v === current ? 'aria-current="true"' : ''}>
      ${field === 'status' ? `<span class="kc-menu-status-dot" data-status="${esc(v)}"></span>` : ''}
      ${esc(v)}
    </button>`
  ).join('');
  document.body.appendChild(pop);
  btn.setAttribute('aria-expanded', 'true');
  _editTrigger = btn;
  positionPopover(pop, btn);

  // Focus the first option; ArrowUp/ArrowDown rove between options.
  const optionEls = [...pop.querySelectorAll('.lr-edit-option')];
  if (optionEls.length) optionEls[0].focus();
  pop.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const focusables = [...pop.querySelectorAll('.lr-edit-option')];
    if (!focusables.length) return;
    const idx = focusables.indexOf(document.activeElement);
    const next = e.key === 'ArrowDown'
      ? (idx + 1) % focusables.length
      : (idx - 1 + focusables.length) % focusables.length;
    focusables[next].focus();
  });

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
        btn.setAttribute('data-status', value);
      } else {
        await patchTicket(id, field, value);
        btn.setAttribute('data-p', value);
      }
      // Reflect the new value on the trigger in-place (SSE refreshes the
      // board fully within ~2s; no forced reload needed).
      applyButtonValue(btn, value);
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
  if (_textTrigger) {
    const t = _textTrigger;
    _textTrigger = null;
    if (document.contains(t)) t.focus();
  }
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
    <div class="lr-edit-text-popover-label">${esc(labelText)}</div>
    <input type="text" value="${esc(current)}" autocomplete="off" spellcheck="false">
    ${hintText ? `<div class="lr-edit-text-popover-hint">${esc(hintText)}</div>` : ''}
    <div class="lr-edit-text-popover-error" data-error></div>
    <div class="lr-edit-text-popover-row">
      <button type="button" class="btn-sm" data-cancel>Cancel</button>
      <button type="submit" class="btn-sm btn-primary" data-save>Save</button>
    </div>
  `;
  document.body.appendChild(pop);
  btn.setAttribute('aria-expanded', 'true');
  _textTrigger = btn;
  positionPopover(pop, btn);
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
      // Update the trigger in-place rather than forcing a reload. The detail
      // page isn't covered by board SSE, so reflect the new value directly on
      // the trigger: keep `data-current` (for the next popover open) in sync
      // and rewrite the visible text. Rich formatting (avatar stacks, chips)
      // is rebuilt server-side on the next full page load.
      const display = Array.isArray(value) ? value.join(', ') : (value === null || value === undefined ? '' : String(value));
      btn.setAttribute('data-current', display);
      btn.replaceChildren(); // clear existing rich content safely
      if (display) {
        const span = document.createElement('span');
        span.className = 'dr-prop-text';
        span.textContent = field === 'sprint' ? `#${display}` : display;
        btn.appendChild(span);
      } else {
        const span = document.createElement('span');
        span.className = 'dr-prop-empty';
        span.textContent = '—';
        btn.appendChild(span);
      }
      showToast(`${field} updated`);
      closeTextEditPopover();
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
