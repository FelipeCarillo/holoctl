#!/usr/bin/env node
// Runs automatically after `npm install -g projctl`.
// Installs /projctl global slash commands for Claude Code and Cursor.
// Fails silently — never break the install.
import { setupGlobal } from '../src/cli/commands/setup-global.js';

try {
  const results = setupGlobal(['claude', 'cursor']);
  const ok = results.filter(r => r.status === 'ok').map(r => r.label);
  if (ok.length > 0) {
    console.log(`\n  projctl: /projctl installed for ${ok.join(', ')}\n`);
  }
} catch {
  // silent
}
