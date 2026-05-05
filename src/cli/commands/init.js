import fs from 'node:fs';
import path from 'node:path';
import chalk from 'chalk';
import { getDefaults, saveConfig } from '../../lib/config.js';
import { getTemplates } from '../../templates/index.js';

export function registerInitCommand(program) {
  program
    .command('init')
    .description('Initialize .holoctl/ in the current directory')
    .option('--name <name>', 'Project name')
    .option('--prefix <prefix>', 'Ticket ID prefix (e.g. MP)')
    .option('--targets <targets>', 'Compile targets (comma-separated: claude,cursor,windsurf)')
    .action(async (opts) => {
      const cwd = process.cwd();
      const holoctlDir = path.join(cwd, '.holoctl');

      if (fs.existsSync(path.join(holoctlDir, 'config.json'))) {
        console.error(chalk.yellow('.holoctl/ already exists in this directory.'));
        process.exit(1);
      }

      const dirName = path.basename(cwd);
      const name = opts.name || dirName;
      const prefix = opts.prefix || derivePrefix(name);
      const targets = opts.targets ? opts.targets.split(',').map(s => s.trim()) : ['claude'];

      const config = getDefaults();
      config.project.name = name;
      config.project.prefix = prefix;
      config.targets = targets;

      console.log(chalk.bold('\n  holoctl init\n'));
      console.log(`  Project:  ${chalk.green(name)}`);
      console.log(`  Prefix:   ${chalk.green(prefix)} (tickets: ${prefix}-001, ${prefix}-002, ...)`);
      console.log(`  Targets:  ${chalk.green(targets.join(', '))}`);
      console.log('');

      // Create directory structure
      const dirs = [
        '.holoctl',
        '.holoctl/board',
        '.holoctl/board/tickets',
        '.holoctl/agents',
        '.holoctl/commands',
        '.holoctl/context',
        '.holoctl/context/decisions',
        '.holoctl/context/documents',
      ];

      for (const dir of dirs) {
        fs.mkdirSync(path.join(cwd, dir), { recursive: true });
      }

      // Write config
      saveConfig(cwd, config);

      // Write templates
      const templates = getTemplates(config);
      for (const [relPath, content] of Object.entries(templates)) {
        const fullPath = path.join(cwd, relPath);
        fs.mkdirSync(path.dirname(fullPath), { recursive: true });
        fs.writeFileSync(fullPath, content, 'utf8');
      }

      // Create empty board index
      const indexData = {
        meta: { version: 1, updated: new Date().toISOString().slice(0, 10), nextId: 1, counts: {} },
        tickets: [],
      };
      fs.writeFileSync(
        path.join(cwd, '.holoctl', 'board', 'index.json'),
        JSON.stringify(indexData, null, '\t') + '\n',
        'utf8'
      );

      // Create empty activity log
      fs.writeFileSync(path.join(cwd, '.holoctl', 'activity.jsonl'), '', 'utf8');

      console.log(chalk.green('  ✓ .holoctl/ initialized successfully.\n'));
      console.log('  Next steps:');
      console.log(`    ${chalk.dim('$')} holoctl board add '{"title":"My first ticket","agent":"developer"}'`);
      console.log(`    ${chalk.dim('$')} holoctl serve`);
      console.log(`    ${chalk.dim('$')} holoctl compile --target ${targets[0]}`);
      console.log('');
    });
}

function derivePrefix(name) {
  const cleaned = name.replace(/[^a-zA-Z0-9]/g, '');
  if (cleaned.length <= 4) return cleaned.toUpperCase();
  // Take first letters of words, or first 3-4 chars
  const words = name.split(/[\s_-]+/).filter(Boolean);
  if (words.length >= 2) {
    return words.map(w => w[0]).join('').toUpperCase().slice(0, 4);
  }
  return cleaned.slice(0, 3).toUpperCase();
}
