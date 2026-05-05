import fs from 'node:fs';
import path from 'node:path';
import { parseFrontmatter, serializeFrontmatter } from './markdown.js';

export function createBoard(projectRoot, config) {
  const boardDir = path.join(projectRoot, '.holoctl', 'board');
  const indexPath = path.join(boardDir, 'index.json');
  const ticketsDir = path.join(boardDir, 'tickets');
  const today = new Date().toISOString().slice(0, 10);

  function load() {
    if (!fs.existsSync(indexPath)) {
      return {
        meta: { version: 1, updated: today, nextId: 1, counts: {} },
        tickets: [],
      };
    }
    return JSON.parse(fs.readFileSync(indexPath, 'utf8'));
  }

  function save(data) {
    fs.mkdirSync(boardDir, { recursive: true });
    fs.writeFileSync(indexPath, JSON.stringify(data, null, '\t') + '\n', 'utf8');
  }

  function recount(tickets) {
    const counts = {};
    for (const s of config.board.statuses) counts[s] = 0;
    for (const t of tickets) counts[t.status] = (counts[t.status] || 0) + 1;
    return counts;
  }

  function generateId(num) {
    const padded = String(num).padStart(config.board.idPadding, '0');
    return `${config.project.prefix}-${padded}`;
  }

  function slugify(title) {
    return title
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .slice(0, 40);
  }

  function patchTicketMd(filePath, patches) {
    const fullPath = path.join(boardDir, filePath);
    if (!fs.existsSync(fullPath)) return;
    let content = fs.readFileSync(fullPath, 'utf8');
    for (const [key, val] of Object.entries(patches)) {
      const strVal = val === null ? 'null' : String(val);
      content = content.replace(
        new RegExp(`^(${key}:\\s*)(.*)$`, 'm'),
        `$1${strVal}`
      );
    }
    fs.writeFileSync(fullPath, content, 'utf8');
  }

  return {
    stat() {
      const data = load();
      return { ...data.meta.counts, nextId: data.meta.nextId };
    },

    get(id) {
      const data = load();
      return data.tickets.find(t => t.id === id) || null;
    },

    ls(filters = {}) {
      const data = load();
      let tickets = data.tickets;

      if (filters.sprint) tickets = tickets.filter(t => t.sprint === filters.sprint);
      if (filters.status) tickets = tickets.filter(t => t.status === filters.status);
      if (filters.agent) tickets = tickets.filter(t => (t.agent || []).includes(filters.agent));
      if (filters.tag) tickets = tickets.filter(t => (t.tags || []).includes(filters.tag));
      if (filters.priority) tickets = tickets.filter(t => t.priority === filters.priority);
      if (filters.project) tickets = tickets.filter(t => (t.projects || []).includes(filters.project));

      return tickets;
    },

    move(id, newStatus) {
      if (!config.board.statuses.includes(newStatus)) {
        throw new Error(`Invalid status: ${newStatus}. Valid: ${config.board.statuses.join('|')}`);
      }

      const data = load();
      const ticket = data.tickets.find(t => t.id === id);
      if (!ticket) throw new Error(`Ticket ${id} not found`);

      const oldStatus = ticket.status;
      ticket.status = newStatus;
      ticket.updated = today;
      if (newStatus === 'done') ticket.completed = today;

      data.meta.counts = recount(data.tickets);
      data.meta.updated = today;
      save(data);

      const mdPatches = { status: newStatus, updated: today };
      if (newStatus === 'done') mdPatches.completed = today;
      if (ticket.file) patchTicketMd(ticket.file, mdPatches);

      return { id, from: oldStatus, to: newStatus };
    },

    set(id, field, value) {
      const data = load();
      const ticket = data.tickets.find(t => t.id === id);
      if (!ticket) throw new Error(`Ticket ${id} not found`);

      const parsed = value === 'null' ? null
        : value === 'true' ? true
        : value === 'false' ? false
        : /^\[/.test(value) ? JSON.parse(value)
        : value;

      ticket[field] = parsed;
      ticket.updated = today;
      data.meta.updated = today;
      save(data);

      if (ticket.file) patchTicketMd(ticket.file, { [field]: value, updated: today });

      return { id, field, value: parsed };
    },

    add(patch) {
      const data = load();
      const nextNum = data.meta.nextId;
      const id = generateId(nextNum);
      const slug = slugify(patch.title || '');

      // Accept new `projects` (array) or legacy `scope` (string).
      let projects = patch.projects;
      if (projects == null && patch.scope) projects = [patch.scope];

      const ticket = {
        id,
        title: patch.title || '',
        agent: patch.agent || [],
        projects: projects || [],
        status: patch.status || 'backlog',
        priority: patch.priority || 'p2',
        sprint: patch.sprint || null,
        created: today,
        updated: today,
        completed: null,
        depends: patch.depends || [],
        tags: patch.tags || [],
        file: `tickets/${id}-${slug}.md`,
        ...patch,
        id,
        created: today,
        updated: today,
        // Re-apply after spread so legacy `scope` in patch doesn't shadow projects.
        projects: normalizeArray(projects),
      };
      delete ticket.scope;

      if (typeof ticket.agent === 'string') ticket.agent = [ticket.agent];
      if (typeof ticket.tags === 'string') ticket.tags = ticket.tags.split(',').map(s => s.trim());
      if (typeof ticket.depends === 'string') ticket.depends = ticket.depends.split(',').map(s => s.trim()).filter(Boolean);

      data.tickets.push(ticket);
      data.meta.nextId = nextNum + 1;
      data.meta.counts = recount(data.tickets);
      data.meta.updated = today;
      save(data);

      createTicketMd(ticket);
      logActivity(projectRoot, { type: 'ticket.created', ticket: id, actor: 'cli' });

      return ticket;
    },

    nextId() {
      const data = load();
      return generateId(data.meta.nextId);
    },

    rebuildIndex() {
      fs.mkdirSync(ticketsDir, { recursive: true });
      const files = fs.readdirSync(ticketsDir).filter(f => f.endsWith('.md') && !f.startsWith('_'));
      const tickets = [];

      for (const file of files) {
        const content = fs.readFileSync(path.join(ticketsDir, file), 'utf8');
        const { data } = parseFrontmatter(content);
        if (!data.id) continue;

        // Migration: legacy `scope: "X"` → `projects: ["X"]`.
        let projectsFm = data.projects;
        if (projectsFm == null && data.scope) projectsFm = data.scope;

        tickets.push({
          id: data.id,
          title: data.title || '',
          agent: normalizeArray(data.agent),
          projects: normalizeArray(projectsFm),
          status: data.status || 'backlog',
          priority: data.priority || 'p2',
          sprint: data.sprint || null,
          created: data.created || today,
          updated: data.updated || today,
          completed: data.completed || null,
          depends: normalizeArray(data.depends),
          tags: normalizeArray(data.tags),
          file: `tickets/${file}`,
        });
      }

      tickets.sort((a, b) => {
        const numA = parseInt(a.id.split('-').pop(), 10);
        const numB = parseInt(b.id.split('-').pop(), 10);
        return numA - numB;
      });

      const maxNum = tickets.reduce((max, t) => {
        const n = parseInt(t.id.split('-').pop(), 10);
        return n > max ? n : max;
      }, 0);

      const data = {
        meta: {
          version: 1,
          updated: today,
          nextId: maxNum + 1,
          counts: recount(tickets),
        },
        tickets,
      };
      save(data);
      return { ticketCount: tickets.length, nextId: data.meta.nextId };
    },
  };

  function createTicketMd(ticket) {
    const mdPath = path.join(boardDir, ticket.file);
    fs.mkdirSync(path.dirname(mdPath), { recursive: true });

    const templatePath = path.join(ticketsDir, '_template.md');
    let body = '';
    if (fs.existsSync(templatePath)) {
      const { body: tmplBody } = parseFrontmatter(fs.readFileSync(templatePath, 'utf8'));
      body = tmplBody;
    } else {
      body = `\n# Start\n\n(Current state before starting)\n\n# Goal — Definition of Done\n\n- [ ] (criteria)\n\n# Context\n\n(Why this ticket exists)\n\n# Out of scope\n\n(What NOT to do)\n\n# Execution notes\n\n(Agent fills during work)\n`;
    }

    const projects = ticket.projects || [];
    const frontmatter = {
      id: ticket.id,
      title: ticket.title,
      agent: ticket.agent.join(', ') || 'null',
      projects: projects.length ? projects.join(', ') : 'null',
      status: ticket.status,
      priority: ticket.priority,
      sprint: ticket.sprint,
      created: ticket.created,
      updated: ticket.updated,
      completed: ticket.completed,
      depends: ticket.depends.length ? ticket.depends.join(', ') : 'null',
      tags: ticket.tags.length ? ticket.tags.join(', ') : 'null',
    };

    const content = serializeFrontmatter(frontmatter, body);
    fs.writeFileSync(mdPath, content, 'utf8');
  }
}

function normalizeArray(val) {
  if (!val || val === 'null') return [];
  if (Array.isArray(val)) return val;
  return String(val).split(',').map(s => s.trim()).filter(Boolean);
}

function logActivity(projectRoot, event) {
  const logPath = path.join(projectRoot, '.holoctl', 'activity.jsonl');
  const entry = { ts: new Date().toISOString(), ...event };
  fs.appendFileSync(logPath, JSON.stringify(entry) + '\n', 'utf8');
}
