// ── Tab Keyboard Navigation ──

export function initTabs() {
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach((tab, i) => {
    tab.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight' && tabs[i + 1]) {
        tabs[i + 1].focus();
        tabs[i + 1].click();
      }
      if (e.key === 'ArrowLeft' && tabs[i - 1]) {
        tabs[i - 1].focus();
        tabs[i - 1].click();
      }
    });
  });
}
