import { Command } from 'commander';
import { createRequire } from 'node:module';
import { registerBoardCommand } from './commands/board.js';
import { registerInitCommand } from './commands/init.js';
import { registerWorkspaceCommand } from './commands/workspace.js';
import { registerDoctorCommand } from './commands/doctor.js';
import { registerAgentCommand } from './commands/agent.js';
import { registerCompileCommand } from './commands/compile.js';
import { registerServeCommand } from './commands/serve.js';
import { registerRepoCommand } from './commands/repo.js';
import { registerSetupGlobalCommand } from './commands/setup-global.js';
import { registerSyncCommand } from './commands/sync.js';

const { version } = createRequire(import.meta.url)('../../package.json');

export function createCli() {
  const program = new Command();

  program
    .name('projctl')
    .description('Universal project operating system for AI coding assistants')
    .version(version);

  registerInitCommand(program);
  registerBoardCommand(program);
  registerRepoCommand(program);
  registerWorkspaceCommand(program);
  registerAgentCommand(program);
  registerCompileCommand(program);
  registerSyncCommand(program);
  registerServeCommand(program);
  registerSetupGlobalCommand(program);
  registerDoctorCommand(program);

  return program;
}
