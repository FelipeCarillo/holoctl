// meta-search.js — client-side text filter for agents / commands lists.
// Filters .agent-card elements by their text content.

import { debounce } from './util.js';

/**
 * Initialise the meta search bar if [data-meta-search] is present on this page.
 * Filters .agent-card elements by their textContent.
 */
export function initMetaSearch() {
  const input = document.querySelector('[data-meta-search]');
  if (!input) return;

  const ITEM_SEL = '.agent-card';

  function applyFilter() {
    const q = input.value.trim().toLowerCase();
    document.querySelectorAll(ITEM_SEL).forEach((item) => {
      if (!q || item.textContent.toLowerCase().includes(q)) {
        item.classList.remove('meta-hidden');
      } else {
        item.classList.add('meta-hidden');
      }
    });
  }

  input.addEventListener('input', debounce(applyFilter, 100));
}
