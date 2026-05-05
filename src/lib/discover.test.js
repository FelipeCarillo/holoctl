import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { discoverRepos } from './discover.js';

function tmpDir(prefix = 'holoctl-test-') {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function makeMarker(dir, name) {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, name), '', 'utf8');
}

describe('discoverRepos', () => {
  it('returns empty list for empty workspace', () => {
    const root = tmpDir();
    assert.deepEqual(discoverRepos(root), []);
  });

  it('detects subdir with .git', () => {
    const root = tmpDir();
    fs.mkdirSync(path.join(root, 'app', '.git'), { recursive: true });
    const repos = discoverRepos(root);
    assert.equal(repos.length, 1);
    assert.equal(repos[0].name, 'app');
    assert.ok(repos[0].markers.includes('.git'));
  });

  it('detects subdir with package.json', () => {
    const root = tmpDir();
    makeMarker(path.join(root, 'frontend'), 'package.json');
    const repos = discoverRepos(root);
    assert.equal(repos.length, 1);
    assert.equal(repos[0].name, 'frontend');
  });

  it('ignores subdir without any marker', () => {
    const root = tmpDir();
    fs.mkdirSync(path.join(root, 'infra'));
    fs.writeFileSync(path.join(root, 'infra', 'main.tf'), '', 'utf8');
    assert.deepEqual(discoverRepos(root), []);
  });

  it('skips well-known dirs even with markers', () => {
    const root = tmpDir();
    for (const skipped of ['node_modules', '__pycache__', '.venv', 'dist']) {
      makeMarker(path.join(root, skipped), 'package.json');
    }
    makeMarker(path.join(root, 'good'), 'package.json');
    const repos = discoverRepos(root);
    assert.deepEqual(repos.map(r => r.name), ['good']);
  });

  it('skips hidden dirs other than .git', () => {
    const root = tmpDir();
    makeMarker(path.join(root, '.idea'), 'package.json');
    makeMarker(path.join(root, 'app'), 'package.json');
    const repos = discoverRepos(root);
    assert.deepEqual(repos.map(r => r.name), ['app']);
  });

  it('does not list root-level files as repos', () => {
    const root = tmpDir();
    fs.writeFileSync(path.join(root, 'package.json'), '{}', 'utf8');
    assert.deepEqual(discoverRepos(root), []);
  });

  it('sorts repos by name', () => {
    const root = tmpDir();
    for (const name of ['zebra', 'alpha', 'mike']) {
      makeMarker(path.join(root, name), 'package.json');
    }
    const names = discoverRepos(root).map(r => r.name);
    assert.deepEqual(names, ['alpha', 'mike', 'zebra']);
  });

  it('manual override renames a discovered repo', () => {
    const root = tmpDir();
    makeMarker(path.join(root, 'app'), 'package.json');
    const repos = discoverRepos(root, {
      includeManual: [{ name: 'frontend-app', path: 'app', description: 'UI' }],
    });
    assert.equal(repos.length, 1);
    assert.equal(repos[0].name, 'frontend-app');
    assert.equal(repos[0].source, 'auto+manual');
  });

  it('manual entry can add subdir without markers', () => {
    const root = tmpDir();
    fs.mkdirSync(path.join(root, 'infra'));
    const repos = discoverRepos(root, {
      includeManual: [{ name: 'infra', path: 'infra', description: 'TF' }],
    });
    assert.equal(repos.length, 1);
    assert.equal(repos[0].source, 'manual');
  });

  it('manual entry pointing to non-existent path is ignored', () => {
    const root = tmpDir();
    const repos = discoverRepos(root, {
      includeManual: [{ name: 'ghost', path: 'ghost', description: '' }],
    });
    assert.deepEqual(repos, []);
  });

  it('non-existent root returns empty list (does not throw)', () => {
    assert.deepEqual(discoverRepos('/this/does/not/exist/abc123xyz'), []);
  });
});
