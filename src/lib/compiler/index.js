import { compileClaude } from './claude.js';
import { compileCursor } from './cursor.js';
import { compileWindsurf } from './windsurf.js';
import { compileCopilot } from './copilot.js';
import { compileGeneric } from './generic.js';

const COMPILERS = {
  claude: compileClaude,
  cursor: compileCursor,
  windsurf: compileWindsurf,
  copilot: compileCopilot,
  generic: compileGeneric,
};

export async function compileProject(projectRoot, config, target, opts = {}) {
  const compiler = COMPILERS[target];
  if (!compiler) {
    throw new Error(`Unknown compile target: ${target}. Available: ${Object.keys(COMPILERS).join(', ')}`);
  }
  return compiler(projectRoot, config, opts);
}
