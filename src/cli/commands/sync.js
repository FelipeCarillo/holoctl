import fs from 'node:fs';
import path from 'node:path';
import chalk from 'chalk';
import { findProjectRoot, loadConfig } from '../../lib/config.js';
import { getTemplates } from '../../templates/index.js';

// Files owned by the template engine — safe to overwrite on sync.
// User-owned files (context docs, tickets, instructions.md, agents) are NOT touched.
const SYNC_TARGETS = new Set([
  '.holoctl/commands/status.md',
  '.holoctl/commands/ticket.md',
  '.holoctl/commands/board.md',
  '.holoctl/commands/sprint.md',
  '.holoctl/commands/decision.md',
  '.holoctl/commands/close.md',
  '.holoctl/board/WORKFLOW.md',
  '.holoctl/board/tickets/_template.md',
]);

export function registerSyncCommand(program) {
  program
    .command('sync')
    .description('Update template-managed files in .holoctl/ after a holoctl upgrade')
    .option('--agents', 'Also regenerate agent templates (overwrites customizations)')
    .option('--dry-run', 'Preview changes without writing files')
    .action((opts) => {
      const root = findProjectRoot();
      if (!root) {
        console.error(chalk.red('No .holoctl/ found. Run `holoctl init` first.'));
        process.exit(1);
      }

      const config = loadConfig(root);
      const templates = getTemplates(config);

      const targets = new Set(SYNC_TARGETS);
      if (opts.agents) {
        for (const key of Object.keys(templates)) {
          if (key.startsWith('.holoctl/agents/')) targets.add(key);
        }
      }

      console.log(chalk.bold('\n  holoctl sync\n'));

      const updated = [];
      const added = [];

      for (const [relPath, content] of Object.entries(templates)) {
        if (!targets.has(relPath)) continue;

        const fullPath = path.join(root, relPath);
        const exists = fs.existsSync(fullPath);
        const changed = exists ? fs.readFileSync(fullPath, 'utf8') !== content : true;

        if (!changed) continue;

        if (!opts.dryRun) {
          fs.mkdirSync(path.dirname(fullPath), { recursive: true });
          fs.writeFileSync(fullPath, content, 'utf8');
        }

        if (exists) {
          updated.push(relPath);
        } else {
          added.push(relPath);
        }
      }

      if (added.length === 0 && updated.length === 0) {
        console.log(chalk.dim('  Already up to date. Nothing to sync.\n'));
        return;
      }

      const prefix = opts.dryRun ? chalk.dim('[dry-run] ') : '';

      for (const f of added) {
        console.log(`  ${prefix}${chalk.green('+')} ${f}`);
      }
      for (const f of updated) {
        console.log(`  ${prefix}${chalk.cyan('~')} ${f}`);
      }

      console.log('');
      if (!opts.dryRun) {
        console.log(chalk.green(`  ✓ Synced ${added.length + updated.length} file(s).\n`));
        console.log(`  Run ${chalk.dim('holoctl compile')} to push changes to your AI tool.\n`);
      } else {
        console.log(chalk.dim(`  ${added.length + updated.length} file(s) would be updated.\n`));
      }
    });
}
