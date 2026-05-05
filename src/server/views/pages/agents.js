import { esc } from '../layout.js';

export function agentsPage(agents, alias) {
  if (agents.length === 0) {
    return `<div class="content">
      <div class="empty-state">
        <h3>No agents defined</h3>
        <p>Run <code>holoctl agent add &lt;name&gt;</code> to create an agent.</p>
      </div>
    </div>`;
  }

  return `<div class="content">
    <div class="section-header">
      <h2 class="section-title">Agents</h2>
      <span class="section-count">${agents.length} agent${agents.length !== 1 ? 's' : ''}</span>
    </div>
    <div class="agent-grid">
      ${agents.map(a => agentCard(a, alias || a.project)).join('\n')}
    </div>
  </div>`;
}

function agentCard(a, alias) {
  const tools = (a.tools || []).map(t =>
    `<span class="tool-chip">${esc(typeof t === 'string' ? t : String(t))}</span>`
  ).join('');

  const trigger = a.trigger || 'ticket';
  const href = alias ? `/project/${esc(alias)}/agents/${esc(a.name)}` : '#';

  return `<a class="agent-card" href="${href}">
    <div class="agent-card-header">
      <span class="trigger-badge">${esc(trigger)}</span>
      <span class="agent-card-name">${esc(a.name)}</span>
      <span class="model-badge ${a.model || 'standard'}">${esc(a.model || 'standard')}</span>
    </div>
    <div class="agent-card-desc">${esc(a.description)}</div>
    <div class="agent-card-meta">${tools}</div>
  </a>`;
}
