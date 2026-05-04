import chalk from 'chalk';
import fs from 'node:fs';
import path from 'node:path';
import { addToWorkspace, removeFromWorkspace, listWorkspace } from '../../lib/workspace.js';

export function registerWorkspaceCommand(program) {
  const ws = program
    .command('workspace')
    .alias('ws')
    .description('Manage registered projects across your machine');

  ws.command('add [path]')
    .description('Register a project in the workspace')
    .option('--alias <alias>', 'Short name for the project')
    .action((projectPath, opts) => {
      const resolved = path.resolve(projectPath || '.');
      if (!fs.existsSync(path.join(resolved, '.projctl', 'config.json'))) {
        console.error(chalk.red(`No .projctl/ found at ${resolved}. Run \`projctl init\` first.`));
        process.exit(1);
      }
      const alias = opts.alias || path.basename(resolved);
      addToWorkspace(resolved, alias);
      console.log(chalk.green(`Added ${alias} → ${resolved}`));
    });

  ws.command('remove <alias>')
    .description('Unregister a project')
    .action((alias) => {
      removeFromWorkspace(alias);
      console.log(chalk.green(`Removed ${alias}`));
    });

  ws.command('list')
    .alias('ls')
    .description('List all registered projects')
    .action(() => {
      const projects = listWorkspace();
      if (projects.length === 0) {
        console.log(chalk.dim('No projects registered. Run `projctl init` in a project directory.'));
        return;
      }
      for (const p of projects) {
        const exists = fs.existsSync(path.join(p.path, '.projctl', 'config.json'));
        const status = exists ? chalk.green('●') : chalk.red('●');
        console.log(`  ${status} ${chalk.bold(p.alias.padEnd(20))} ${chalk.dim(p.path)}`);
      }
    });
}
