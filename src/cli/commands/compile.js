import chalk from 'chalk';
import { findProjectRoot, loadConfig } from '../../lib/config.js';
import { compileProject } from '../../lib/compiler/index.js';

export function registerCompileCommand(program) {
  program
    .command('compile')
    .description('Compile .projctl/ to tool-specific files')
    .option('--target <target>', 'Specific target (claude, cursor, windsurf, copilot, devin, aider, generic)')
    .option('--dry-run', 'Preview without writing files')
    .action(async (opts) => {
      const root = findProjectRoot();
      if (!root) {
        console.error(chalk.red('No .projctl/ found. Run `projctl init` first.'));
        process.exit(1);
      }

      const config = loadConfig(root);
      const targets = opts.target ? [opts.target] : config.targets;

      for (const target of targets) {
        try {
          const result = await compileProject(root, config, target, { dryRun: opts.dryRun });
          if (opts.dryRun) {
            console.log(chalk.dim(`[dry-run] ${target}:`));
            for (const file of result.files) {
              console.log(`  ${chalk.dim('would write')} ${file}`);
            }
          } else {
            console.log(chalk.green(`✓ ${target}`), chalk.dim(`(${result.files.length} files)`));
            for (const file of result.files) {
              console.log(`  ${chalk.dim('→')} ${file}`);
            }
          }
        } catch (e) {
          console.error(chalk.red(`✗ ${target}: ${e.message}`));
        }
      }
    });
}
