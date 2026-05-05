import fs from 'node:fs';
import path from 'node:path';
import chalk from 'chalk';
import { findProjectRoot } from '../../lib/config.js';
import { parseFrontmatter } from '../../lib/markdown.js';

export function registerAgentCommand(program) {
  const agent = program
    .command('agent')
    .description('Manage agent definitions');

  agent
    .command('list')
    .alias('ls')
    .description('List configured agents')
    .action(() => {
      const root = findProjectRoot();
      if (!root) {
        console.error(chalk.red('No .holoctl/ found. Run `holoctl init` first.'));
        process.exit(1);
      }

      const agentsDir = path.join(root, '.holoctl', 'agents');
      if (!fs.existsSync(agentsDir)) {
        console.log(chalk.dim('No agents configured.'));
        return;
      }

      const files = fs.readdirSync(agentsDir).filter(f => f.endsWith('.md'));
      for (const file of files) {
        const content = fs.readFileSync(path.join(agentsDir, file), 'utf8');
        const { data } = parseFrontmatter(content);
        const model = data.model || 'standard';
        const trigger = data.trigger || 'ticket';
        const modelColor = model === 'reasoning' ? chalk.magenta : model === 'fast' ? chalk.dim : chalk.cyan;
        console.log(
          `  ${chalk.bold((data.name || file).padEnd(16))} ${modelColor(model.padEnd(10))} ${chalk.dim(trigger.padEnd(16))} ${data.description || ''}`
        );
      }
    });

  agent
    .command('add <name>')
    .description('Create a new agent definition')
    .option('--from <template>', 'Base on an existing agent template')
    .action((name, opts) => {
      const root = findProjectRoot();
      if (!root) {
        console.error(chalk.red('No .holoctl/ found. Run `holoctl init` first.'));
        process.exit(1);
      }

      const agentsDir = path.join(root, '.holoctl', 'agents');
      const targetPath = path.join(agentsDir, `${name}.md`);

      if (fs.existsSync(targetPath)) {
        console.error(chalk.yellow(`Agent ${name} already exists.`));
        process.exit(1);
      }

      if (opts.from) {
        const sourcePath = path.join(agentsDir, `${opts.from}.md`);
        if (!fs.existsSync(sourcePath)) {
          console.error(chalk.red(`Template agent ${opts.from} not found.`));
          process.exit(1);
        }
        let content = fs.readFileSync(sourcePath, 'utf8');
        content = content.replace(/^(name:\s*).*$/m, `$1${name}`);
        fs.writeFileSync(targetPath, content, 'utf8');
      } else {
        fs.writeFileSync(targetPath, `---
name: ${name}
description: "(describe what this agent does)"
model: standard
tools: [read, search, edit, write, shell]
trigger: ticket
---

# Identity

You are the **${name}** agent. (Define identity and purpose)

# Guard Rail

(Define when this agent should refuse to work)

# Scope

(Define what this agent does and does NOT do)

# Work Order

1. (Step-by-step work process)

# Report Format

- **Done**: bullets with file:line references.
- **Definition of Done**: each Goal item marked \`[x]\` or \`[ ]\`.
- **Suggested next step**: 1 line.
`, 'utf8');
      }

      console.log(chalk.green(`Created agent: .holoctl/agents/${name}.md`));
    });
}
