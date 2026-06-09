// ── Shared popover positioning ──

/**
 * Position an absolutely-positioned popover relative to a trigger button.
 * Places the popover below the trigger, flipping above when it would
 * overflow the viewport bottom. Coordinates are document-relative (they
 * account for scroll), matching `position: absolute` popovers appended to
 * <body>.
 *
 * @param {HTMLElement} pop   the popover element (already in the DOM)
 * @param {HTMLElement} btn   the trigger element
 * @param {{align?: 'left'|'right'}} [opts]  horizontal alignment edge
 */
export function positionPopover(pop, btn, opts = {}) {
  const align = opts.align || 'left';
  const r = btn.getBoundingClientRect();
  pop.style.top = (window.scrollY + r.bottom + 4) + 'px';
  const left = align === 'right'
    ? window.scrollX + r.right - pop.offsetWidth
    : window.scrollX + r.left;
  pop.style.left = Math.max(8, left) + 'px';
  // Flip above the trigger when it would overflow the viewport bottom.
  if (r.bottom + pop.offsetHeight + 8 > window.innerHeight) {
    pop.style.top = (window.scrollY + r.top - pop.offsetHeight - 4) + 'px';
  }
}
