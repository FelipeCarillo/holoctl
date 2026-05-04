import { execSync } from 'node:child_process';
import fs from 'node:fs';

export function getGitInfo(absPath) {
  if (!fs.existsSync(absPath)) return { isGit: false };

  try {
    execSync('git rev-parse --git-dir', { cwd: absPath, stdio: 'pipe' });
  } catch {
    return { isGit: false };
  }

  const run = (cmd) => {
    try {
      return execSync(cmd, { cwd: absPath, stdio: 'pipe' }).toString().trim();
    } catch {
      return '';
    }
  };

  const branch = run('git rev-parse --abbrev-ref HEAD');
  const commitHash = run('git log -1 --pretty=format:%H').slice(0, 7);
  const commitMsg = run('git log -1 --pretty=format:%s');
  const commitDate = run('git log -1 --pretty=format:%cd --date=short');
  const dirty = run('git status --porcelain').length > 0;
  const remote = run('git remote get-url origin');

  return {
    isGit: true,
    branch: branch || 'HEAD',
    commitHash,
    lastCommit: commitMsg,
    commitDate,
    dirty,
    remote: remote || null,
  };
}
