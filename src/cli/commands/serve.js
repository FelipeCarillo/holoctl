import chalk from 'chalk';

export function registerServeCommand(program) {
  program
    .command('serve')
    .description('Start the web platform dashboard')
    .option('--port <port>', 'Port number', '4242')
    .option('--open', 'Open browser automatically')
    .action((opts) => {
      console.log(chalk.yellow('\n  projctl serve is not yet implemented.'));
      console.log(chalk.dim('  The web platform (Phase 2) will add a full dashboard with:'));
      console.log(chalk.dim('    - Multi-project overview'));
      console.log(chalk.dim('    - Live kanban board'));
      console.log(chalk.dim('    - Agent registry'));
      console.log(chalk.dim('    - Context management'));
      console.log(chalk.dim(`\n  It will run on http://localhost:${opts.port}\n`));
    });
}
