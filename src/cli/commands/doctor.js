import fs from 'node:fs';
import path from 'node:path';
import chalk from 'chalk';
import { findProjectRoot, loadConfig } from '../../lib/config.js';

export function registerDoctorCommand(program) {
  program
    .command('doctor')
    .description('Check project health')
    .action(() => {
      const root = findProjectRoot();
      if (!root) {
        console.error(chalk.red('No .holoctl/ found. Run `holoctl init` first.'));
        process.exit(1);
      }

      console.log(chalk.bold('\n  holoctl doctor\n'));
      let issues = 0;

      // Check config
      try {
        const config = loadConfig(root);
        check('Config', '.holoctl/config.json is valid', true);
      } catch (e) {
        check('Config', `.holoctl/config.json: ${e.message}`, false);
        issues++;
      }

      // Check board
      const indexPath = path.join(root, '.holoctl', 'board', 'index.json');
      if (fs.existsSync(indexPath)) {
        try {
          const data = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
          const ticketCount = data.tickets?.length || 0;
          check('Board', `index.json valid (${ticketCount} tickets)`, true);
        } catch (e) {
          check('Board', `index.json parse error: ${e.message}`, false);
          issues++;
        }
      } else {
        check('Board', 'index.json exists', false);
        issues++;
      }

      // Check agents
      const agentsDir = path.join(root, '.holoctl', 'agents');
      if (fs.existsSync(agentsDir)) {
        const agents = fs.readdirSync(agentsDir).filter(f => f.endsWith('.md'));
        check('Agents', `${agents.length} agent(s) defined`, agents.length > 0);
        if (agents.length === 0) issues++;
      } else {
        check('Agents', 'agents/ directory exists', false);
        issues++;
      }

      // Check commands
      const commandsDir = path.join(root, '.holoctl', 'commands');
      if (fs.existsSync(commandsDir)) {
        const commands = fs.readdirSync(commandsDir).filter(f => f.endsWith('.md'));
        check('Commands', `${commands.length} command(s) defined`, commands.length > 0);
        if (commands.length === 0) issues++;
      } else {
        check('Commands', 'commands/ directory exists', false);
        issues++;
      }

      // Check instructions
      const instructionsPath = path.join(root, '.holoctl', 'instructions.md');
      check('Instructions', 'instructions.md exists', fs.existsSync(instructionsPath));
      if (!fs.existsSync(instructionsPath)) issues++;

      // Check context
      const contextDir = path.join(root, '.holoctl', 'context');
      check('Context', 'context/ directory exists', fs.existsSync(contextDir));
      if (!fs.existsSync(contextDir)) issues++;

      console.log('');
      if (issues === 0) {
        console.log(chalk.green('  All checks passed. Project is healthy.\n'));
      } else {
        console.log(chalk.yellow(`  ${issues} issue(s) found.\n`));
      }
    });
}

function check(category, message, ok) {
  const icon = ok ? chalk.green('✓') : chalk.red('✗');
  console.log(`  ${icon} ${chalk.dim(category.padEnd(14))} ${message}`);
}
