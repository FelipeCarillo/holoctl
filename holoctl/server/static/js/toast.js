// ── Toast Notifications ──

export function showToast(message) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<span class="toast-dot"></span><span>${message}</span><button class="toast-dismiss" onclick="this.parentElement.remove()">&times;</button>`;
  toast.addEventListener('click', (e) => {
    if (e.target.closest('.toast-dismiss')) return;
    window.location.reload();
  });
  container.appendChild(toast);

  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, 8000);
}
