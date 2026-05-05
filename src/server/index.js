import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Hono } from 'hono';
import { serveStatic } from '@hono/node-server/serve-static';
import { serve } from '@hono/node-server';
import { streamSSE } from 'hono/streaming';

import { findProjectRoot, loadConfig } from '../lib/config.js';
import { createBoard } from '../lib/board.js';
import { parseFrontmatter } from '../lib/markdown.js';
import { discoverRepos } from '../lib/discover.js';

// Replaces the old global-registry-based listWorkspace(): workspace is now the
// single dir containing .holoctl/ discovered upwards from cwd.
function listWorkspaceCompat() {
  const root = findProjectRoot();
  if (!root) return [];
  return [{ path: root, alias: path.basename(root), added: '', lastSeen: '' }];
}
import { layout, sidebarHtml, topbarHtml, tabsHtml, esc } from './views/layout.js';
import { homePage } from './views/pages/home.js';
import { boardPage } from './views/pages/board.js';
import { agentsPage } from './views/pages/agents.js';
import { contextPage } from './views/pages/context.js';
import { commandsPage } from './views/pages/commands.js';
import { ticketDetailPage } from './views/pages/ticket-detail.js';
import { agentDetailPage } from './views/pages/agent-detail.js';
import { commandDetailPage } from './views/pages/command-detail.js';
import { contextDetailPage } from './views/pages/context-detail.js';
import { reposPage } from './views/pages/repos.js';
import { filesPage } from './views/pages/files.js';
import { scanDir } from '../lib/filetree.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function createServer(opts = {}) {
  const app = new Hono();

  // Static files
  app.use('/static/*', async (c, next) => {
    const filePath = path.join(__dirname, 'static', c.req.path.replace('/static/', ''));
    if (fs.existsSync(filePath)) {
      const ext = path.extname(filePath);
      const mimeTypes = {
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.png': 'image/png',
        '.svg': 'image/svg+xml',
      };
      const content = fs.readFileSync(filePath);
      c.header('Content-Type', mimeTypes[ext] || 'application/octet-stream');
      return c.body(content);
    }
    return next();
  });

  // ── Helpers ──

  function getProjects() {
    const workspace = listWorkspaceCompat();
    return workspace.map(p => {
      try {
        const config = loadConfig(p.path);
        const board = createBoard(p.path, config);
        const stats = board.stat();
        const agentsDir = path.join(p.path, '.holoctl', 'agents');
        const agents = fs.existsSync(agentsDir)
          ? fs.readdirSync(agentsDir).filter(f => f.endsWith('.md')).map(f => f.replace('.md', ''))
          : [];
        const allTickets = board.ls();
        const discovered = discoverRepos(p.path, { includeManual: config.project.repos || [] });
        const enrichedRepos = discovered.map(r => {
          const ticketCount = allTickets.filter(t => (t.projects || []).includes(r.name)).length;
          return { ...r, ticketCount };
        });

        return {
          ...p,
          name: config.project.name,
          prefix: config.project.prefix,
          description: config.project.description,
          counts: stats,
          ticketCount: Object.entries(stats).filter(([k]) => k !== 'nextId').reduce((a, [, v]) => a + v, 0),
          agents,
          targets: config.targets,
          repos: enrichedRepos,
          config,
          valid: true,
        };
      } catch {
        return { ...p, valid: false, counts: {}, ticketCount: 0, agents: [], targets: [] };
      }
    }).filter(p => p.valid);
  }

  function getProject(alias) {
    const projects = getProjects();
    return projects.find(p => p.alias === alias);
  }

  function readAgents(projectPath) {
    const agentsDir = path.join(projectPath, '.holoctl', 'agents');
    if (!fs.existsSync(agentsDir)) return [];
    return fs.readdirSync(agentsDir)
      .filter(f => f.endsWith('.md'))
      .map(f => {
        const content = fs.readFileSync(path.join(agentsDir, f), 'utf8');
        const { data } = parseFrontmatter(content);
        return { ...data, file: f };
      });
  }

  function readCommands(projectPath) {
    const dir = path.join(projectPath, '.holoctl', 'commands');
    if (!fs.existsSync(dir)) return [];
    return fs.readdirSync(dir)
      .filter(f => f.endsWith('.md'))
      .map(f => {
        const content = fs.readFileSync(path.join(dir, f), 'utf8');
        const { data } = parseFrontmatter(content);
        return { ...data, file: f };
      });
  }

  function readContextDocs(projectPath) {
    const dir = path.join(projectPath, '.holoctl', 'context');
    if (!fs.existsSync(dir)) return [];
    const items = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        items.push({ name: entry.name + '/', isDir: true, description: `${entry.name} folder` });
      } else if (entry.name.endsWith('.md')) {
        const content = fs.readFileSync(path.join(dir, entry.name), 'utf8');
        const firstLine = content.split('\n').find(l => l.startsWith('# '));
        items.push({ name: entry.name, isDir: false, description: firstLine?.replace('# ', '') || '' });
      }
    }
    return items;
  }

  function renderPage(title, content, { projects, currentAlias, currentTab, breadcrumbs, tabs, tabBase, actions } = {}) {
    const allProjects = projects || getProjects();
    const sidebar = sidebarHtml(allProjects, currentAlias, currentTab);
    const topbar = topbarHtml(title, breadcrumbs || [], actions || '');
    const tabsBar = tabs ? tabsHtml(tabs, currentTab, tabBase) : '';
    return layout(title, tabsBar + content, { sidebar, topbar });
  }

  // ── Routes ──

  const PROJECT_TABS = [
    { id: 'board', icon: '<svg class="icon-sm" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg> ', label: 'Board' },
    { id: 'repos', icon: '<svg class="icon-sm" viewBox="0 0 24 24"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg> ', label: 'Repos' },
    { id: 'files', icon: '<svg class="icon-sm" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg> ', label: 'Files' },
    { id: 'agents', icon: '<svg class="icon-sm" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4M4.22 4.22l2.83 2.83m9.9 9.9l2.83 2.83M1 12h4m14 0h4M4.22 19.78l2.83-2.83m9.9-9.9l2.83-2.83"/></svg> ', label: 'Agents' },
    { id: 'commands', icon: '<svg class="icon-sm" viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg> ', label: 'Commands' },
    { id: 'context', icon: '<svg class="icon-sm" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> ', label: 'Context' },
  ];

  // Home
  app.get('/', (c) => {
    const projects = getProjects();
    const html = renderPage('Home', homePage(projects), {
      projects,
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: 'Home' }],
    });
    return c.html(html);
  });

  // Project board
  app.get('/project/:alias/board', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const board = createBoard(project.path, project.config);
    const tickets = board.ls();
    const html = renderPage(project.name, boardPage(project, tickets, project.config), {
      currentAlias: project.alias,
      currentTab: 'board',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Board' }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Project agents
  app.get('/project/:alias/agents', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const agents = readAgents(project.path);
    const html = renderPage(project.name, agentsPage(agents, project.alias), {
      currentAlias: project.alias,
      currentTab: 'agents',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Agents' }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Project commands
  app.get('/project/:alias/commands', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const commands = readCommands(project.path);
    const html = renderPage(project.name, commandsPage(commands, project.alias), {
      currentAlias: project.alias,
      currentTab: 'commands',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Commands' }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Project context
  app.get('/project/:alias/context', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const docs = readContextDocs(project.path);
    const html = renderPage(project.name, contextPage(docs, project.alias), {
      currentAlias: project.alias,
      currentTab: 'context',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Context' }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Ticket detail
  app.get('/project/:alias/board/:ticketId', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const ticketId = c.req.param('ticketId');
    const board = createBoard(project.path, project.config);
    const ticket = board.get(ticketId);
    if (!ticket) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Ticket not found</h3></div></div>'), 404);

    const ticketFile = path.join(project.path, '.holoctl', 'board', ticket.file);
    const rawContent = fs.existsSync(ticketFile) ? fs.readFileSync(ticketFile, 'utf8') : '';
    const { body } = parseFrontmatter(rawContent);

    const backLink = `<a class="back-link" href="/project/${project.alias}/board"><svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>Back to Board</a>`;
    const html = renderPage(`${ticketId} — ${project.name}`, ticketDetailPage(ticket, body, backLink), {
      currentAlias: project.alias,
      currentTab: 'board',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Board', href: `/project/${project.alias}/board` }, { label: ticketId }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Agent detail
  app.get('/project/:alias/agents/:name', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const agentName = c.req.param('name');
    const agentFile = path.join(project.path, '.holoctl', 'agents', agentName + '.md');
    if (!fs.existsSync(agentFile)) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Agent not found</h3></div></div>'), 404);

    const rawContent = fs.readFileSync(agentFile, 'utf8');
    const { data, body } = parseFrontmatter(rawContent);

    const backLink = `<a class="back-link" href="/project/${project.alias}/agents"><svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>Back to Agents</a>`;
    const html = renderPage(`${agentName} — ${project.name}`, agentDetailPage({ ...data, file: agentName + '.md' }, body, backLink), {
      currentAlias: project.alias,
      currentTab: 'agents',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Agents', href: `/project/${project.alias}/agents` }, { label: agentName }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Command detail
  app.get('/project/:alias/commands/:name', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const cmdName = c.req.param('name');
    const cmdFile = path.join(project.path, '.holoctl', 'commands', cmdName + '.md');
    if (!fs.existsSync(cmdFile)) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Command not found</h3></div></div>'), 404);

    const rawContent = fs.readFileSync(cmdFile, 'utf8');
    const { data, body } = parseFrontmatter(rawContent);

    const backLink = `<a class="back-link" href="/project/${project.alias}/commands"><svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>Back to Commands</a>`;
    const html = renderPage(`/${cmdName} — ${project.name}`, commandDetailPage(data, body, backLink), {
      currentAlias: project.alias,
      currentTab: 'commands',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Commands', href: `/project/${project.alias}/commands` }, { label: '/' + cmdName }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Context doc detail
  app.get('/project/:alias/context/:name', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const docName = c.req.param('name');
    const docFile = path.join(project.path, '.holoctl', 'context', docName);
    if (!fs.existsSync(docFile)) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Document not found</h3></div></div>'), 404);

    const rawContent = fs.readFileSync(docFile, 'utf8');

    const backLink = `<a class="back-link" href="/project/${project.alias}/context"><svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>Back to Context</a>`;
    const html = renderPage(`${docName} — ${project.name}`, contextDetailPage(docName, rawContent, backLink), {
      currentAlias: project.alias,
      currentTab: 'context',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Context', href: `/project/${project.alias}/context` }, { label: docName }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Project files
  app.get('/project/:alias/files', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const entries = scanDir(project.path, { maxDepth: 1 });
    const html = renderPage(project.name, filesPage(project.alias, entries), {
      currentAlias: project.alias,
      currentTab: 'files',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Files' }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Files API (lazy expand)
  app.get('/api/project/:alias/files', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.json({ error: 'Not found' }, 404);

    const subPath = c.req.query('path') || '';
    const safe = subPath.replace(/\.\./g, '').replace(/^[/\\]+/, '');
    const absPath = safe ? path.join(project.path, safe) : project.path;

    if (!absPath.startsWith(project.path)) return c.json({ error: 'Forbidden' }, 403);

    const entries = scanDir(absPath, { maxDepth: 1 });
    return c.json({ entries });
  });

  // Project repos
  app.get('/project/:alias/repos', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.html(renderPage('Not Found', '<div class="content"><div class="empty-state"><h3>Project not found</h3></div></div>'), 404);

    const html = renderPage(project.name, reposPage(project.repos || [], project.alias), {
      currentAlias: project.alias,
      currentTab: 'repos',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: project.name, href: `/project/${project.alias}/board` }, { label: 'Repos' }],
      tabs: PROJECT_TABS,
      tabBase: `/project/${project.alias}`,
    });
    return c.html(html);
  });

  // Project redirect
  app.get('/project/:alias', (c) => {
    return c.redirect(`/project/${c.req.param('alias')}/board`);
  });

  // Global agent registry
  app.get('/agents', (c) => {
    const projects = getProjects();
    const allAgents = [];
    for (const p of projects) {
      const agents = readAgents(p.path);
      for (const a of agents) {
        allAgents.push({ ...a, project: p.alias });
      }
    }
    const html = renderPage('Agent Registry', agentsPage(allAgents), {
      currentTab: 'agents-global',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: 'Agent Registry' }],
    });
    return c.html(html);
  });

  // Activity (placeholder)
  app.get('/activity', (c) => {
    const html = renderPage('Activity', `<div class="content">
      <div class="empty-state">
        <h3>Activity Timeline</h3>
        <p>Cross-project activity feed coming soon.</p>
      </div>
    </div>`, {
      currentTab: 'activity-global',
      breadcrumbs: [{ label: 'holoctl', href: '/' }, { label: 'Activity' }],
    });
    return c.html(html);
  });

  // ── API ──

  app.get('/api/projects', (c) => {
    return c.json({ projects: getProjects() });
  });

  app.get('/api/project/:alias/board', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.json({ error: 'Not found' }, 404);
    const board = createBoard(project.path, project.config);
    const indexPath = path.join(project.path, '.holoctl', 'board', 'index.json');
    const data = fs.existsSync(indexPath) ? JSON.parse(fs.readFileSync(indexPath, 'utf8')) : { meta: {}, tickets: [] };
    return c.json(data);
  });

  // SSE for live updates
  app.get('/api/project/:alias/events', (c) => {
    const project = getProject(c.req.param('alias'));
    if (!project) return c.json({ error: 'Not found' }, 404);

    return streamSSE(c, async (stream) => {
      const indexPath = path.join(project.path, '.holoctl', 'board', 'index.json');

      const sendUpdate = () => {
        try {
          const data = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
          stream.writeSSE({ data: JSON.stringify(data), event: 'board-update' });
        } catch {}
      };

      sendUpdate();

      if (fs.existsSync(indexPath)) {
        const watcher = fs.watch(indexPath, () => sendUpdate());
        stream.onAbort(() => watcher.close());

        // Keep alive
        while (true) {
          await stream.sleep(30000);
        }
      }
    });
  });

  return app;
}

export function startServer(port = 4242) {
  const app = createServer();

  serve({ fetch: app.fetch, port }, (info) => {
    console.log(`\n  holoctl dashboard  →  http://localhost:${info.port}\n`);
  });
}
