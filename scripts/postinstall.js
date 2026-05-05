#!/usr/bin/env node
// Runs automatically after `npm install -g projctl`.
// Installs /projctl global slash commands for Claude Code and Cursor.
// Fails silently — never break the install.

// Skip entirely when installed as a local dependency (not with -g).
if (!process.env.npm_config_global) process.exit(0);

import { setupGlobal } from '../src/cli/commands/setup-global.js';

try {
  const results = setupGlobal(['claude', 'cursor']);
  const ok = results.filter(r => r.status === 'ok').map(r => r.label);
  const failed = results.filter(r => r.status === 'error');

  if (ok.length > 0) {
    console.log(`\n  projctl: /projctl installed for ${ok.join(', ')}\n`);
  }
  if (failed.length > 0) {
    for (const f of failed) {
      process.stderr.write(`  projctl: could not install for ${f.label}: ${f.error}\n`);
    }
    process.stderr.write('  Run `projctl setup-global` manually to retry.\n\n');
  }
  if (ok.length === 0 && failed.length === 0) {
    // missing-template — package integrity issue
    process.stderr.write('  projctl: slash command templates not found — run `projctl setup-global` after install.\n\n');
  }
} catch (err) {
  process.stderr.write(`  projctl: postinstall error: ${err.message}\n`);
  process.stderr.write('  Run `projctl setup-global` manually to install slash commands.\n\n');
}
