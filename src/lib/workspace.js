import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const WORKSPACE_DIR = path.join(os.homedir(), '.projctl');
const WORKSPACE_FILE = path.join(WORKSPACE_DIR, 'workspace.json');

function load() {
  if (!fs.existsSync(WORKSPACE_FILE)) {
    return { version: 1, projects: [] };
  }
  return JSON.parse(fs.readFileSync(WORKSPACE_FILE, 'utf8'));
}

function save(data) {
  fs.mkdirSync(WORKSPACE_DIR, { recursive: true });
  fs.writeFileSync(WORKSPACE_FILE, JSON.stringify(data, null, 2) + '\n', 'utf8');
}

export function addToWorkspace(projectPath, alias) {
  const resolved = path.resolve(projectPath);
  const data = load();

  const existing = data.projects.find(p => p.path === resolved);
  if (existing) {
    existing.alias = alias || existing.alias;
    existing.lastSeen = new Date().toISOString().slice(0, 10);
  } else {
    data.projects.push({
      path: resolved,
      alias: alias || path.basename(resolved),
      added: new Date().toISOString().slice(0, 10),
      lastSeen: new Date().toISOString().slice(0, 10),
    });
  }

  save(data);
  return data;
}

export function removeFromWorkspace(aliasOrPath) {
  const data = load();
  const resolved = path.resolve(aliasOrPath);
  data.projects = data.projects.filter(
    p => p.alias !== aliasOrPath && p.path !== resolved
  );
  save(data);
  return data;
}

export function listWorkspace() {
  return load().projects;
}

export function getWorkspacePath() {
  return WORKSPACE_FILE;
}
