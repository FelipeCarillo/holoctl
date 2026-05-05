import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import chalk from 'chalk';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TEMPLATES_DIR = path.join(__dirname, '../../templates/commands');
const { version: PKG_VERSION } = createRequire(import.meta.url)('../../../package.json');

// Centralised platform registry — mirrors the pattern used by graphify.
// skill_dst is relative to os.homedir() unless it's an absolute path.
// version_stamp: write a .projctl_version file alongside the installed file.
const _PLATFORM_CONFIG = {
  claude: {
    template: 'projctl-claude.md',
    destDir: path.join(os.homedir(), '.claude', 'commands'),
    fileName: 'projctl.md',
    label: 'Claude Code',
  },
  cursor: {
    template: 'projctl-cursor.md',
    destDir: path.join(os.homedir(), '.cursor', 'commands'),
    fileName: 'projctl.md',
    label: 'Cursor',
  },
  windsurf: {
    template: 'projctl-windsurf.md',
    destDir: path.join(os.homedir(), '.codeium', 'windsurf', 'memories'),
    fileName: 'projctl.md',
    label: 'Windsurf',
  },
  copilot: {
    template: 'projctl-copilot.prompt.md',
    destDir: path.join(os.homedir(), '.copilot', 'prompts'),
    fileName: 'projctl.prompt.md',
    label: 'GitHub Copilot',
  },
};

function _versionFile(destDir) {
  return path.join(destDir, '.projctl_version');
}

function _checkInstalledVersion(destDir) {
  const vf = _versionFile(destDir);
  if (!fs.existsSync(vf)) return null;
  return fs.readFileSync(vf, 'utf8').trim();
}

function _writeVersionStamp(destDir) {
  fs.writeFileSync(_versionFile(destDir), PKG_VERSION, 'utf8');
}

function _refreshAllVersionStamps() {
  for (const cfg of Object.values(_PLATFORM_CONFIG)) {
    const vf = _versionFile(cfg.destDir);
    if (fs.existsSync(vf)) {
      try { fs.writeFileSync(vf, PKG_VERSION, 'utf8'); } catch { /* ignore */ }
    }
  }
}

export function checkInstalledVersions() {
  const results = [];
  for (const [key, cfg] of Object.entries(_PLATFORM_CONFIG)) {
    const dest = path.join(cfg.destDir, cfg.fileName);
    if (!fs.existsSync(dest)) continue;
    const installed = _checkInstalledVersion(cfg.destDir);
    results.push({ platform: key, label: cfg.label, dest, installed, current: PKG_VERSION });
  }
  return results;
}

export function setupGlobal(targets, opts = {}) {
  const results = [];

  for (const targetKey of targets) {
    const cfg = _PLATFORM_CONFIG[targetKey];
    if (!cfg) {
      results.push({ target: targetKey, status: 'unknown' });
      continue;
    }

    const src = path.join(TEMPLATES_DIR, cfg.template);
    if (!fs.existsSync(src)) {
      results.push({ target: targetKey, label: cfg.label, status: 'missing-template' });
      continue;
    }

    const dest = path.join(cfg.destDir, cfg.fileName);

    try {
      if (!opts.dryRun) {
        fs.mkdirSync(cfg.destDir, { recursive: true });
        fs.copyFileSync(src, dest);
        _writeVersionStamp(cfg.destDir);
      }
      results.push({ target: targetKey, label: cfg.label, dest, status: 'ok' });
    } catch (err) {
      results.push({ target: targetKey, label: cfg.label, status: 'error', error: err.message });
    }
  }

  if (!opts.dryRun && results.some(r => r.status === 'ok')) {
    _refreshAllVersionStamps();
  }

  return results;
}

export function registerSetupGlobalCommand(program) {
  const platformList = Object.keys(_PLATFORM_CONFIG).join(',');

  program
    .command('setup-global')
    .description('Install /projctl slash command globally for AI coding assistants')
    .option('--targets <targets>', `Comma-separated targets (${platformList})`, 'claude,cursor')
    .option('--dry-run', 'Preview without writing files')
    .option('--check', 'Show installed versions without installing')
    .action((opts) => {
      if (opts.check) {
        const versions = checkInstalledVersions();
        if (versions.length === 0) {
          console.log(chalk.dim('\n  /projctl is not installed in any known location.\n'));
          return;
        }
        console.log(chalk.bold('\n  projctl setup-global --check\n'));
        for (const v of versions) {
          const stale = v.installed && v.installed !== v.current;
          const badge = stale
            ? chalk.yellow(`v${v.installed} → upgrade to v${v.current}`)
            : chalk.green(`v${v.installed ?? 'unknown'} (up to date)`);
          console.log(`  ${chalk.bold(v.label.padEnd(18))} ${badge}`);
          console.log(`  ${chalk.dim(v.dest)}`);
        }
        console.log();
        return;
      }

      const targets = opts.targets.split(',').map(s => s.trim()).filter(Boolean);
      const unknown = targets.filter(t => !_PLATFORM_CONFIG[t]);
      if (unknown.length > 0) {
        console.error(chalk.red(`  Unknown target(s): ${unknown.join(', ')}`));
        console.error(chalk.dim(`  Valid targets: ${platformList}`));
        process.exit(1);
      }

      const results = setupGlobal(targets, { dryRun: opts.dryRun });

      console.log(chalk.bold('\n  projctl setup-global\n'));
      for (const r of results) {
        if (r.status === 'ok') {
          const icon = opts.dryRun ? chalk.dim('[dry-run]') : chalk.green('✓');
          console.log(`  ${icon} ${chalk.bold(r.label)}`);
          console.log(`     ${chalk.dim(r.dest)}`);
        } else if (r.status === 'error') {
          console.log(`  ${chalk.red('✗')} ${chalk.bold(r.label ?? r.target)}: ${r.error}`);
          console.error(chalk.dim(`     Tip: try running with elevated permissions or check write access to ${chalk.underline(path.dirname(r.dest ?? ''))}`));
        } else if (r.status === 'missing-template') {
          console.log(`  ${chalk.yellow('?')} ${chalk.bold(r.label ?? r.target)}: template not found — reinstall projctl`);
        } else {
          console.log(`  ${chalk.dim('?')} ${r.target}: unknown target`);
        }
      }

      const ok = results.filter(r => r.status === 'ok').length;
      if (ok > 0 && !opts.dryRun) {
        console.log(`\n  ${chalk.green(`/projctl is now available in ${ok} tool${ok !== 1 ? 's' : ''}`)}\n`);
        if (targets.includes('claude')) {
          console.log(chalk.dim('  Open Claude Code and type /projctl to get started.\n'));
        }
      }
    });
}
