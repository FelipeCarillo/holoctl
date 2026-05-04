import { compileClaude } from './claude.js';
import { compileGeneric } from './generic.js';

const COMPILERS = {
  claude: compileClaude,
  generic: compileGeneric,
};

export async function compileProject(projectRoot, config, target, opts = {}) {
  const compiler = COMPILERS[target];
  if (!compiler) {
    throw new Error(`Unknown compile target: ${target}. Available: ${Object.keys(COMPILERS).join(', ')}`);
  }
  return compiler(projectRoot, config, opts);
}
