import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { createBoard } from './board.js';
import { saveConfig, loadConfig, getDefaults } from './config.js';

function freshWorkspace() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'holoctl-board-test-'));
  const config = getDefaults();
  config.project.name = 'TestProject';
  config.project.prefix = 'TST';
  saveConfig(root, config);
  fs.mkdirSync(path.join(root, '.holoctl', 'board', 'tickets'), { recursive: true });
  fs.writeFileSync(
    path.join(root, '.holoctl', 'board', 'index.json'),
    JSON.stringify({
      meta: { version: 1, updated: '2026-01-01', nextId: 1, counts: {} },
      tickets: [],
    }, null, '\t') + '\n',
    'utf8'
  );
  fs.writeFileSync(path.join(root, '.holoctl', 'activity.jsonl'), '', 'utf8');
  return { root, config: loadConfig(root) };
}

describe('createBoard', () => {
  let ws;
  beforeEach(() => { ws = freshWorkspace(); });

  it('add creates ticket with auto ID and writes md file', () => {
    const board = createBoard(ws.root, ws.config);
    const t = board.add({ title: 'First', agent: 'developer' });
    assert.equal(t.id, 'TST-001');
    assert.deepEqual(t.agent, ['developer']);
    const mdPath = path.join(ws.root, '.holoctl', 'board', t.file);
    assert.ok(fs.existsSync(mdPath));
    assert.match(fs.readFileSync(mdPath, 'utf8'), /id: TST-001/);
  });

  it('add increments id', () => {
    const board = createBoard(ws.root, ws.config);
    const a = board.add({ title: 'A' });
    const b = board.add({ title: 'B' });
    assert.equal(a.id, 'TST-001');
    assert.equal(b.id, 'TST-002');
    assert.equal(board.nextId(), 'TST-003');
  });

  it('add accepts projects array', () => {
    const board = createBoard(ws.root, ws.config);
    const t = board.add({ title: 'X', projects: ['app', 'api'] });
    assert.deepEqual(t.projects, ['app', 'api']);
    const md = fs.readFileSync(path.join(ws.root, '.holoctl', 'board', t.file), 'utf8');
    assert.match(md, /projects: app, api/);
  });

  it('add migrates legacy scope string to projects array', () => {
    const board = createBoard(ws.root, ws.config);
    const t = board.add({ title: 'Legacy', scope: 'backend' });
    assert.deepEqual(t.projects, ['backend']);
    assert.equal(t.scope, undefined);
  });

  it('ls filters by status', () => {
    const board = createBoard(ws.root, ws.config);
    board.add({ title: 'A' });
    const second = board.add({ title: 'B' });
    board.move(second.id, 'doing');
    assert.equal(board.ls({ status: 'backlog' }).length, 1);
    assert.equal(board.ls({ status: 'doing' }).length, 1);
  });

  it('ls filters by project', () => {
    const board = createBoard(ws.root, ws.config);
    board.add({ title: 'A', projects: ['app'] });
    board.add({ title: 'B', projects: ['api'] });
    board.add({ title: 'C', projects: ['app', 'api'] });
    assert.equal(board.ls({ project: 'app' }).length, 2);
    assert.equal(board.ls({ project: 'api' }).length, 2);
  });

  it('move updates status and md', () => {
    const board = createBoard(ws.root, ws.config);
    const t = board.add({ title: 'X' });
    const r = board.move(t.id, 'doing');
    assert.deepEqual(r, { id: t.id, from: 'backlog', to: 'doing' });
    const md = fs.readFileSync(path.join(ws.root, '.holoctl', 'board', t.file), 'utf8');
    assert.match(md, /status: doing/);
  });

  it('move to invalid status throws', () => {
    const board = createBoard(ws.root, ws.config);
    const t = board.add({ title: 'X' });
    assert.throws(() => board.move(t.id, 'bogus'));
  });

  it('stat counts by status', () => {
    const board = createBoard(ws.root, ws.config);
    const a = board.add({ title: 'A' });
    const b = board.add({ title: 'B' });
    board.add({ title: 'C' });
    board.move(a.id, 'doing');
    board.move(b.id, 'done');
    const s = board.stat();
    assert.equal(s.backlog, 1);
    assert.equal(s.doing, 1);
    assert.equal(s.done, 1);
    assert.equal(s.nextId, 4);
  });

  it('rebuildIndex migrates legacy scope to projects', () => {
    const legacyMd = `---
id: TST-099
title: Legacy
agent: developer
scope: backend
status: backlog
priority: p2
sprint: null
created: 2026-01-01
updated: 2026-01-01
completed: null
depends: null
tags: null
---

# Start
`;
    fs.writeFileSync(
      path.join(ws.root, '.holoctl', 'board', 'tickets', 'TST-099-legacy.md'),
      legacyMd,
      'utf8'
    );
    const board = createBoard(ws.root, ws.config);
    const result = board.rebuildIndex();
    assert.equal(result.ticketCount, 1);
    const fresh = board.get('TST-099');
    assert.deepEqual(fresh.projects, ['backend']);
  });
});
