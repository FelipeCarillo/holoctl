import { startServer } from '../../server/index.js';

export function registerServeCommand(program) {
  program
    .command('serve')
    .description('Start the web platform dashboard')
    .option('--port <port>', 'Port number', '4242')
    .action((opts) => {
      startServer(Number(opts.port));
    });
}
