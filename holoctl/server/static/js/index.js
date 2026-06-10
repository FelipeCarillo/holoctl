// holoctl — module entry. Loaded as <script type="module">. Each feature
// exposes an init() wired up on DOMContentLoaded below. Interactions use
// delegated listeners + data-action attributes (no inline onclick / window
// globals) so a future CSP can drop unsafe-inline. The one remaining global,
// window.__reapplyBoardControls (board-controls.js), is consumed by the SSE
// handler after it swaps the board DOM.

import { initTheme } from './theme.js';
import { initSSE } from './sse.js';
import { initTabs } from './tabs.js';
import { initStagger } from './stagger.js';
import { initFileTree } from './filetree.js';
import { initBoardControls } from './board-controls.js';
import { initCardMenus } from './card-menu.js';
import { initInlineAdd } from './inline-add.js';
import { initViewSwitcher } from './view-switcher.js';
import { initListSelection } from './list-selection.js';
import { initInlineEdit } from './inline-edit.js';
import { initMetaSearch } from './meta-search.js';

// Keyboard activation for elements with role="button". Native <button>/<a>
// already handle Enter/Space; this covers the few <div role="button">
// headers (list-group) that we couldn't make actual buttons due to grid
// layout.
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
  initMetaSearch();
  initRoleButtonKeys();
});
