import { Command } from 'commander';
import { registerBoardCommand } from './commands/board.js';
import { registerInitCommand } from './commands/init.js';
import { registerWorkspaceCommand } from './commands/workspace.js';
import { registerDoctorCommand } from './commands/doctor.js';
import { registerAgentCommand } from './commands/agent.js';
import { registerCompileCommand } from './commands/compile.js';
import { registerServeCommand } from './commands/serve.js';
import { registerRepoCommand } from './commands/repo.js';
import { registerSetupGlobalCommand } from './commands/setup-global.js';

export function createCli() {
  const program = new Command();

  program
    .name('projctl')
    .description('Universal project operating system for AI coding assistants')
    .version('0.1.0');

  registerInitCommand(program);
  registerBoardCommand(program);
  registerRepoCommand(program);
  registerWorkspaceCommand(program);
  registerAgentCommand(program);
  registerCompileCommand(program);
  registerServeCommand(program);
  registerSetupGlobalCommand(program);
  registerDoctorCommand(program);

  return program;
}
