import fs from 'node:fs';
import path from 'node:path';

// Markers checked when locating a project root. `.holoctl` is canonical;
// `.projctl` and `.projhub` are accepted for backwards compatibility with
// pre-rename installs and are auto-renamed to `.holoctl` on the next save.
const PROJECT_DIR_MARKERS = ['.holoctl', '.projctl', '.projhub'];

function existingMarker(root) {
  for (const marker of PROJECT_DIR_MARKERS) {
    if (fs.existsSync(path.join(root, marker, 'config.json'))) return marker;
  }
  return null;
}

const DEFAULTS = {
  version: 1,
  project: {
    name: 'MyProject',
    prefix: 'PRJ',
    description: '',
    objective: '',
    repos: [],
  },
  board: {
    statuses: ['backlog', 'doing', 'review', 'done', 'cancelled'],
    priorities: ['p0', 'p1', 'p2', 'p3'],
    idPadding: 3,
    customFields: {},
  },
  agents: {
    defaultModel: 'standard',
    requireTicket: true,
  },
  commands: {
    boardCli: 'npx holoctl board',
  },
  targets: ['claude'],
  server: {
    port: 4242,
    theme: 'dark',
  },
};

export function findProjectRoot(from = process.cwd()) {
  let dir = path.resolve(from);
  while (true) {
    if (existingMarker(dir)) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function migrateLegacyMarker(projectRoot) {
  const canonical = path.join(projectRoot, '.holoctl');
  const legacy = existingMarker(projectRoot);
  if (legacy && legacy !== '.holoctl' && !fs.existsSync(canonical)) {
    fs.renameSync(path.join(projectRoot, legacy), canonical);
  }
}

export function loadConfig(projectRoot) {
  // Migrate legacy `.projctl/` or `.projhub/` BEFORE reading so downstream
  // consumers (board, server) that hardcode `.holoctl/` don't get confused.
  migrateLegacyMarker(projectRoot);
  const marker = existingMarker(projectRoot);
  if (!marker) throw new Error(`No .holoctl/config.json found at ${projectRoot}`);
  const configPath = path.join(projectRoot, marker, 'config.json');
  const raw = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  return deepMerge(structuredClone(DEFAULTS), raw);
}

export function saveConfig(projectRoot, config) {
  migrateLegacyMarker(projectRoot);
  const canonical = path.join(projectRoot, '.holoctl');
  fs.mkdirSync(canonical, { recursive: true });
  fs.writeFileSync(path.join(canonical, 'config.json'), JSON.stringify(config, null, 2) + '\n', 'utf8');
}

export function getDefaults() {
  return structuredClone(DEFAULTS);
}

function deepMerge(target, source) {
  for (const key of Object.keys(source)) {
    if (
      source[key] &&
      typeof source[key] === 'object' &&
      !Array.isArray(source[key]) &&
      target[key] &&
      typeof target[key] === 'object' &&
      !Array.isArray(target[key])
    ) {
      deepMerge(target[key], source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}
