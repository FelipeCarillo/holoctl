import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import chalk from 'chalk';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TEMPLATES_DIR = path.join(__dirname, '../../templates/commands');

const TARGETS = {
  claude: {
    globalDir: path.join(os.homedir(), '.claude', 'commands'),
    fileName: 'projctl.md',
    template: 'projctl-claude.md',
    label: 'Claude Code',
  },
  cursor: {
    globalDir: path.join(os.homedir(), '.cursor', 'commands'),
    fileName: 'projctl.md',
    template: 'projctl-cursor.md',
    label: 'Cursor',
  },
};

export function setupGlobal(targets, opts = {}) {
  const results = [];

  for (const targetKey of targets) {
    const t = TARGETS[targetKey];
    if (!t) {
      results.push({ target: targetKey, status: 'unknown' });
      continue;
    }

    try {
      const src = path.join(TEMPLATES_DIR, t.template);
      if (!fs.existsSync(src)) {
        results.push({ target: targetKey, label: t.label, status: 'missing-template' });
        continue;
      }

      const dest = path.join(t.globalDir, t.fileName);
      if (!opts.dryRun) {
        fs.mkdirSync(t.globalDir, { recursive: true });
        fs.copyFileSync(src, dest);
      }
      results.push({ target: targetKey, label: t.label, dest, status: 'ok' });
    } catch (err) {
      results.push({ target: targetKey, label: t.label, status: 'error', error: err.message });
    }
  }

  return results;
}

export function registerSetupGlobalCommand(program) {
  program
    .command('setup-global')
    .description('Install /projctl slash command globally for AI tools (Claude Code, Cursor)')
    .option('--targets <targets>', 'Comma-separated targets (claude,cursor)', 'claude,cursor')
    .option('--dry-run', 'Preview without writing files')
    .action((opts) => {
      const targets = opts.targets.split(',').map(s => s.trim()).filter(Boolean);
      const results = setupGlobal(targets, { dryRun: opts.dryRun });

      console.log(chalk.bold('\n  projctl setup-global\n'));
      for (const r of results) {
        if (r.status === 'ok') {
          const icon = opts.dryRun ? chalk.dim('[dry-run]') : chalk.green('✓');
          console.log(`  ${icon} ${chalk.bold(r.label)}`);
          console.log(`     ${chalk.dim(r.dest)}`);
        } else if (r.status === 'error') {
          console.log(`  ${chalk.red('✗')} ${chalk.bold(r.label || r.target)}: ${r.error}`);
        } else if (r.status === 'missing-template') {
          console.log(`  ${chalk.yellow('?')} ${chalk.bold(r.label || r.target)}: template not found`);
        } else {
          console.log(`  ${chalk.dim('?')} ${r.target}: unknown target`);
        }
      }

      const ok = results.filter(r => r.status === 'ok').length;
      if (ok > 0 && !opts.dryRun) {
        console.log(`\n  ${chalk.green(`/projctl is now available in ${ok} tool${ok !== 1 ? 's' : ''}`)}\n`);
      }
    });
}
