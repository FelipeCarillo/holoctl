#!/usr/bin/env node
// Discover *.test.js under src/ and run them with the built-in test runner.
// Reason this exists: `node --test src/**/*.test.js` doesn't expand the glob
// in cmd.exe / Windows git-bash, and `node --test src/` tries to load src as
// a module. So we expand the glob ourselves — works from Node 18 upward.

import { spawnSync } from 'node:child_process';
import { readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = 'src';
const SKIP = new Set(['node_modules', '.git', 'dist', 'build']);

function findTests(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    if (SKIP.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...findTests(full));
    else if (entry.endsWith('.test.js')) out.push(full);
  }
  return out;
}

const files = findTests(ROOT);
if (files.length === 0) {
  console.log(`No *.test.js found under ${ROOT}/`);
  process.exit(0);
}

const result = spawnSync(process.execPath, ['--test', ...files], {
  stdio: 'inherit',
});
process.exit(result.status ?? 1);
