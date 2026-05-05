import { esc } from '../layout.js';

export function reposPage(repos, alias) {
  if (repos.length === 0) {
    return `<div class="content">
      <div class="empty-state">
        <h3>No repos registered</h3>
        <p>Add sub-directories to this project with:</p>
        <code>holoctl repo add ./my-repo --name my-repo</code>
      </div>
    </div>`;
  }

  return `<div class="content">
    <div class="section-header">
      <h2 class="section-title">Repos</h2>
      <span class="section-count">${repos.length} repo${repos.length !== 1 ? 's' : ''}</span>
    </div>
    <div class="project-grid">
      ${repos.map(r => repoCard(r, alias)).join('\n')}
    </div>
  </div>`;
}

function repoCard(r, alias) {
  const git = r.git || {};
  const branchBadge = git.isGit
    ? `<span class="chip chip-agent">${esc(git.branch || 'HEAD')}${git.dirty ? ' *' : ''}</span>`
    : `<span class="chip" style="color:var(--text-2)">no git</span>`;

  const commitLine = git.isGit && git.commitHash
    ? `<div class="project-card-path" title="${esc(git.lastCommit)}">
        <span style="font-family:monospace;color:var(--text-2)">${esc(git.commitHash)}</span>
        ${esc((git.lastCommit || '').slice(0, 48))}
        <span style="color:var(--text-3)">${esc(git.commitDate || '')}</span>
       </div>`
    : `<div class="project-card-path" style="color:var(--text-3)">no commits</div>`;

  const remoteLink = git.remote
    ? `<a class="chip chip-target" href="${esc(normalizeRemote(git.remote))}" target="_blank" rel="noopener" style="text-decoration:none">${esc(remoteLabel(git.remote))}</a>`
    : '';

  const ticketBadge = r.ticketCount != null
    ? `<span class="badge" style="margin-left:auto">${r.ticketCount} ticket${r.ticketCount !== 1 ? 's' : ''}</span>`
    : '';

  const dirtyIndicator = git.dirty
    ? `<span style="color:var(--yellow);font-size:11px;font-weight:600">● uncommitted changes</span>`
    : '';

  return `<div class="project-card" style="cursor:default">
    <div class="project-card-header">
      <div class="project-card-icon">${esc((r.name[0] || 'R').toUpperCase())}</div>
      <div style="flex:1;min-width:0">
        <div class="project-card-name">${esc(r.name)}</div>
        <div class="project-card-prefix">${esc(r.path || '')} ${ticketBadge}</div>
        ${commitLine}
      </div>
    </div>
    <div class="project-card-meta" style="margin-top:8px;gap:6px;align-items:center">
      ${branchBadge}
      ${remoteLink}
      ${dirtyIndicator}
    </div>
    ${r.description ? `<div style="font-size:12px;color:var(--text-2);margin-top:8px">${esc(r.description)}</div>` : ''}
  </div>`;
}

function normalizeRemote(remote) {
  if (!remote) return '#';
  if (remote.startsWith('http')) return remote;
  // git@github.com:user/repo.git → https://github.com/user/repo
  const m = remote.match(/git@([^:]+):(.+?)(?:\.git)?$/);
  if (m) return `https://${m[1]}/${m[2]}`;
  return remote;
}

function remoteLabel(remote) {
  if (!remote) return '';
  const m = remote.match(/github\.com[:/](.+?)(?:\.git)?$/);
  if (m) return m[1];
  return remote.replace(/^https?:\/\//, '').replace(/\.git$/, '').slice(0, 30);
}
