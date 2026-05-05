import fs from 'node:fs';
import path from 'node:path';
import { getGitInfo } from './git.js';

const PROJECT_MARKERS = [
  '.git',
  'package.json',
  'pyproject.toml',
  'Cargo.toml',
  'go.mod',
  'composer.json',
  'Gemfile',
  'pubspec.yaml',
  'mix.exs',
  'build.gradle',
  'pom.xml',
  'CMakeLists.txt',
];

const SKIP_NAMES = new Set([
  'node_modules', '.venv', 'venv', 'env',
  'dist', 'build', 'target', 'out',
  '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
  '.holoctl', '.projctl', '.projhub',
  '.git', '.svn', '.hg',
  'coverage', '.coverage', '.nyc_output',
  '.next', '.nuxt', '.cache',
  '.DS_Store',
]);

function detectMarkers(dirPath) {
  const found = [];
  for (const marker of PROJECT_MARKERS) {
    if (fs.existsSync(path.join(dirPath, marker))) found.push(marker);
  }
  return found;
}

export function discoverRepos(projectRoot, opts = {}) {
  const { includeManual = [], skip = [] } = opts;
  const skipSet = new Set([...SKIP_NAMES, ...skip]);

  let entries;
  try {
    entries = fs.readdirSync(projectRoot, { withFileTypes: true });
  } catch {
    return [];
  }

  const discovered = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    if (entry.name.startsWith('.') && entry.name !== '.git') continue;
    if (skipSet.has(entry.name)) continue;

    const absPath = path.join(projectRoot, entry.name);
    const markers = detectMarkers(absPath);
    if (markers.length === 0) continue;

    discovered.push({
      name: entry.name,
      path: entry.name,
      markers,
      git: markers.includes('.git') ? getGitInfo(absPath) : null,
      source: 'auto',
    });
  }

  // Merge manual overrides (from config.project.repos[]); manual entries can
  // add subdirs that the scan missed, or override the auto-detected name.
  const byPath = new Map(discovered.map(r => [r.path, r]));
  for (const manual of includeManual) {
    const relPath = manual.path;
    const absPath = path.join(projectRoot, relPath);
    if (!fs.existsSync(absPath)) continue;

    const existing = byPath.get(relPath);
    if (existing) {
      existing.name = manual.name || existing.name;
      existing.description = manual.description;
      existing.source = 'auto+manual';
    } else {
      byPath.set(relPath, {
        name: manual.name || path.basename(relPath),
        path: relPath,
        markers: detectMarkers(absPath),
        git: getGitInfo(absPath),
        description: manual.description,
        source: 'manual',
      });
    }
  }

  return Array.from(byPath.values()).sort((a, b) => a.name.localeCompare(b.name));
}
