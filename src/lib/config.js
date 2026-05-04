import fs from 'node:fs';
import path from 'node:path';

const CONFIG_FILE = '.projctl/config.json';

const DEFAULTS = {
  version: 1,
  project: {
    name: 'MyProject',
    prefix: 'PRJ',
    description: '',
    objective: '',
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
    boardCli: 'npx projctl board',
  },
  targets: ['claude'],
  server: {
    port: 4242,
  },
};

export function findProjectRoot(from = process.cwd()) {
  let dir = path.resolve(from);
  while (true) {
    if (fs.existsSync(path.join(dir, '.projctl', 'config.json'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

export function loadConfig(projectRoot) {
  const configPath = path.join(projectRoot, CONFIG_FILE);
  if (!fs.existsSync(configPath)) {
    throw new Error(`No .projctl/config.json found at ${projectRoot}`);
  }
  const raw = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  return deepMerge(structuredClone(DEFAULTS), raw);
}

export function saveConfig(projectRoot, config) {
  const configPath = path.join(projectRoot, CONFIG_FILE);
  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n', 'utf8');
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
