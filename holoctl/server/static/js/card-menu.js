import { showToast } from './toast.js';
import { esc } from './dom.js';
import { projectAlias, moveTicket } from './api.js';
import { positionPopover } from './popover.js';

// ── Card hover menu (⋯) ──

// Statuses come from the server. On the kanban view we mine the column
// elements (which carry `data-status`); everywhere else (list, timeline,
// detail page) the server stamps a CSV onto the closest enclosing
// wrapper via `data-statuses`. Without this fallback, the detail-page
// toolbar Move ▾ + ⋯ menus would render an empty popover (no kanban
// cols on that page → empty list → invisible UI → "button does
// nothing").
export function statusList() {
  const wrap = document.querySelector('[data-statuses]');
  if (wrap) {
    const csv = wrap.getAttribute('data-statuses') || '';
    const fromAttr = csv.split(',').map(s => s.trim()).filter(Boolean);
    if (fromAttr.length) return fromAttr;
  }
  return [...document.querySelectorAll('.kanban-col[data-status]')]
    .map(col => col.getAttribute('data-status'))
    .filter((v, i, arr) => v && arr.indexOf(v) === i);
}

// Trigger that opened the current menu — focus returns here on close.
let _menuTrigger = null;

function closeCardMenu() {
  document.querySelectorAll('.kc-menu-popover').forEach(p => p.remove());
  document.querySelectorAll('.kc-menu[aria-expanded="true"], [data-card-menu][aria-expanded="true"]').forEach(b =>
    b.setAttribute('aria-expanded', 'false'));
  if (_menuTrigger) {
    const t = _menuTrigger;
    _menuTrigger = null;
    if (document.contains(t)) t.focus();
  }
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
    .map(s => `<button type="button" class="kc-menu-item" data-action="move" data-status="${esc(s)}">
      <span class="kc-menu-status-dot" data-status="${esc(s)}"></span>
      Move to ${esc(s)}
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
  _menuTrigger = btn;

  // Position below the button, right-aligned; flip above near viewport bottom.
  positionPopover(pop, btn, { align: 'right' });

  // Focus the first menu item on open.
  const items = [...pop.querySelectorAll('.kc-menu-item')];
  if (items.length) items[0].focus();

  // ArrowUp/ArrowDown roving focus between items.
  pop.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const focusables = [...pop.querySelectorAll('.kc-menu-item')];
    if (!focusables.length) return;
    const idx = focusables.indexOf(document.activeElement);
    const next = e.key === 'ArrowDown'
      ? (idx + 1) % focusables.length
      : (idx - 1 + focusables.length) % focusables.length;
    focusables[next].focus();
  });

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
        await moveTicket(id, target);
        showToast(`Moved to ${target}`);
      } catch (err) {
        showToast(`Move failed: ${err.message || 'network'}`);
      } finally {
        closeCardMenu();
      }
    }
  });
}

export function initCardMenus() {
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
