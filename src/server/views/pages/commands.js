import { esc } from '../layout.js';

const cmdIcon = `<svg class="icon-sm" viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`;

export function commandsPage(commands, alias) {
  if (commands.length === 0) {
    return `<div class="content">
      <div class="empty-state">
        <h3>No commands defined</h3>
        <p>Run <code>projctl cmd add &lt;name&gt;</code> to create a command.</p>
      </div>
    </div>`;
  }

  return `<div class="content">
    <div class="section-header">
      <h2 class="section-title">Commands</h2>
      <span class="section-count">${commands.length} command${commands.length !== 1 ? 's' : ''}</span>
    </div>
    <div class="context-list">
      ${commands.map(cmd => commandItem(cmd, alias)).join('\n')}
    </div>
  </div>`;
}

function commandItem(cmd, alias) {
  const href = alias ? `/project/${esc(alias)}/commands/${esc(cmd.name)}` : '#';

  return `<a class="context-item" href="${href}">
    <div class="context-item-icon command">${cmdIcon}</div>
    <div style="flex:1">
      <div class="context-item-name">/${esc(cmd.name)} ${cmd.arguments ? `<span style="color:var(--text-muted)">${esc(cmd.arguments)}</span>` : ''}</div>
      <div class="context-item-desc">${esc(cmd.description)}</div>
    </div>
  </a>`;
}
