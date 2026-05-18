// holoctl — module entry. Loaded as <script type="module">; imports run
// before any DOM is parsed, so module-level side-effects (window.__xxx
// assignments in theme/project-filter/board-controls) wire the global
// handlers that templates still call via `onclick="__foo()"`.

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

// Side-effect imports — these modules only export window-scoped handlers
// consumed via onclick attributes, no init() to call.
import './project-filter.js';

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
  initRoleButtonKeys();
});
