import { showToast } from './toast.js';
import { projectAlias } from './api.js';

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

export function initInlineAdd() {
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
