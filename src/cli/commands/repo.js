import chalk from 'chalk';
import fs from 'node:fs';
import path from 'node:path';
import { findProjectRoot, loadConfig, saveConfig } from '../../lib/config.js';
import { getGitInfo } from '../../lib/git.js';

function getProjectContext() {
  const root = findProjectRoot();
  if (!root) {
    console.error(chalk.red('No .holoctl/ found. Run `holoctl init` first.'));
    process.exit(1);
  }
  const config = loadConfig(root);
  return { root, config };
}

export function registerRepoCommand(program) {
  const repo = program
    .command('repo')
    .alias('r')
    .description('Manage repos (sub-directories) within a project root');

  repo
    .command('add <repoPath>')
    .description('Register a sub-directory/repo in this project')
    .option('--name <name>', 'Short name for the repo (defaults to directory name)')
    .option('--description <desc>', 'Brief description', '')
    .action((repoPath, opts) => {
      const { root, config } = getProjectContext();

      const abs = path.resolve(repoPath);
      if (!fs.existsSync(abs)) {
        console.error(chalk.red(`Path does not exist: ${abs}`));
        process.exit(1);
      }

      const name = opts.name || path.basename(abs);
      const rel = path.relative(root, abs).replace(/\\/g, '/');

      if (config.project.repos.find(r => r.name === name)) {
        console.error(chalk.yellow(`Repo "${name}" already registered.`));
        process.exit(1);
      }

      config.project.repos.push({ name, path: rel, description: opts.description });
      saveConfig(root, config);

      const git = getGitInfo(abs);
      const branch = git.isGit ? chalk.cyan(git.branch) : chalk.dim('not a git repo');
      console.log(chalk.green(`Added repo "${name}"`) + `  ${chalk.dim(rel)}  ${branch}`);
    });

  repo
    .command('remove <name>')
    .description('Unregister a repo from this project')
    .action((name) => {
      const { root, config } = getProjectContext();
      const before = config.project.repos.length;
      config.project.repos = config.project.repos.filter(r => r.name !== name);
      if (config.project.repos.length === before) {
        console.error(chalk.red(`Repo "${name}" not found.`));
        process.exit(1);
      }
      saveConfig(root, config);
      console.log(chalk.green(`Removed repo "${name}"`));
    });

  repo
    .command('list')
    .alias('ls')
    .description('List registered repos')
    .action(() => {
      const { root, config } = getProjectContext();
      const repos = config.project.repos;
      if (repos.length === 0) {
        console.log(chalk.dim('No repos registered. Run `holoctl repo add <path>`.'));
        return;
      }
      for (const r of repos) {
        const abs = path.join(root, r.path);
        const git = getGitInfo(abs);
        const exists = fs.existsSync(abs);
        const status = exists ? chalk.green('●') : chalk.red('●');
        const branch = git.isGit
          ? chalk.cyan(`[${git.branch}]`) + (git.dirty ? chalk.yellow(' *') : '')
          : chalk.dim('[no git]');
        const commit = git.commitHash ? chalk.dim(` ${git.commitHash} ${git.lastCommit.slice(0, 40)}`) : '';
        console.log(`  ${status} ${chalk.bold(r.name.padEnd(20))} ${branch}${commit}`);
        console.log(`     ${chalk.dim(r.path)}`);
      }
    });

  repo
    .command('info <name>')
    .description('Show git info for a repo')
    .action((name) => {
      const { root, config } = getProjectContext();
      const entry = config.project.repos.find(r => r.name === name);
      if (!entry) {
        console.error(chalk.red(`Repo "${name}" not found.`));
        process.exit(1);
      }
      const abs = path.join(root, entry.path);
      const git = getGitInfo(abs);
      console.log(chalk.bold(`\n  ${name}\n`));
      console.log(`  Path:    ${chalk.dim(abs)}`);
      if (!git.isGit) {
        console.log(`  Git:     ${chalk.dim('not a git repository')}\n`);
        return;
      }
      console.log(`  Branch:  ${chalk.cyan(git.branch)}${git.dirty ? chalk.yellow('  (dirty)') : ''}`);
      console.log(`  Commit:  ${chalk.dim(git.commitHash)} ${git.lastCommit}`);
      console.log(`  Date:    ${chalk.dim(git.commitDate)}`);
      if (git.remote) console.log(`  Remote:  ${chalk.dim(git.remote)}`);
      console.log('');
    });
}
