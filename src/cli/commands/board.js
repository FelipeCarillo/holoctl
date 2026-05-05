import chalk from 'chalk';
import { findProjectRoot, loadConfig } from '../../lib/config.js';
import { createBoard } from '../../lib/board.js';

function getBoard() {
  const root = findProjectRoot();
  if (!root) {
    console.error(chalk.red('No .holoctl/ found. Run `holoctl init` first.'));
    process.exit(1);
  }
  const config = loadConfig(root);
  return { board: createBoard(root, config), config, root };
}

export function registerBoardCommand(program) {
  const board = program
    .command('board')
    .alias('b')
    .description('Manage the project board (tickets, statuses, sprints)');

  board
    .command('stat')
    .description('Show ticket counts by status')
    .action(() => {
      const { board: b } = getBoard();
      const stats = b.stat();
      console.log(JSON.stringify(stats, null, 2));
    });

  board
    .command('get <id>')
    .description('Get a single ticket by ID')
    .action((id) => {
      const { board: b } = getBoard();
      const ticket = b.get(id);
      if (!ticket) {
        console.error(chalk.red(`Ticket ${id} not found`));
        process.exit(1);
      }
      console.log(JSON.stringify(ticket, null, 2));
    });

  board
    .command('ls')
    .description('List tickets with optional filters')
    .option('--sprint <sprint>', 'Filter by sprint')
    .option('--status <status>', 'Filter by status')
    .option('--agent <agent>', 'Filter by agent')
    .option('--tag <tag>', 'Filter by tag')
    .option('--project <name>', 'Filter by project (subdir name discovered in workspace)')
    .argument('[priority]', 'Filter by priority (p0, p1, p2, p3)')
    .action((priority, opts) => {
      const { board: b } = getBoard();
      const filters = { ...opts };
      if (priority && /^p\d$/.test(priority)) filters.priority = priority;

      const tickets = b.ls(filters);
      if (tickets.length === 0) {
        console.log(chalk.dim('No tickets match the filters.'));
        return;
      }

      for (const t of tickets) {
        const dep = t.depends?.length ? chalk.dim(` [dep: ${t.depends.join(', ')}]`) : '';
        const agents = t.agent?.length ? chalk.green(t.agent.join(',')) : chalk.dim('—');
        console.log(
          `${chalk.bold(t.id)}  ${priorityColor(t.priority)}  ${statusColor(t.status)}  ${(t.sprint || '—').padEnd(12)}  ${agents.padEnd(20)}  ${t.title.slice(0, 50)}${dep}`
        );
      }
    });

  board
    .command('move <id> <status>')
    .description('Move a ticket to a new status')
    .action((id, status) => {
      const { board: b } = getBoard();
      try {
        const result = b.move(id, status);
        console.log(`${result.id}: ${result.from} → ${chalk.bold(result.to)}`);
      } catch (e) {
        console.error(chalk.red(e.message));
        process.exit(1);
      }
    });

  board
    .command('set <id> <field> [value...]')
    .description('Set a field on a ticket')
    .action((id, field, valueParts) => {
      const { board: b } = getBoard();
      const value = valueParts.join(' ');
      try {
        const result = b.set(id, field, value);
        console.log(`${result.id}.${result.field} = ${JSON.stringify(result.value)}`);
      } catch (e) {
        console.error(chalk.red(e.message));
        process.exit(1);
      }
    });

  board
    .command('add <json>')
    .description('Create a new ticket from JSON')
    .action((json) => {
      const { board: b } = getBoard();
      try {
        const patch = JSON.parse(json);
        const ticket = b.add(patch);
        console.log(chalk.green(`Created ${ticket.id}: ${ticket.title}`));
        console.log(JSON.stringify(ticket, null, 2));
      } catch (e) {
        console.error(chalk.red(e.message));
        process.exit(1);
      }
    });

  board
    .command('next-id')
    .description('Show the next available ticket ID')
    .action(() => {
      const { board: b } = getBoard();
      console.log(b.nextId());
    });

  board
    .command('rebuild-index')
    .description('Rebuild index.json from ticket .md files')
    .action(() => {
      const { board: b } = getBoard();
      const result = b.rebuildIndex();
      console.log(chalk.green(`Rebuilt index: ${result.ticketCount} tickets, nextId: ${result.nextId}`));
    });
}

function priorityColor(p) {
  const colors = { p0: chalk.red, p1: chalk.yellow, p2: chalk.blue, p3: chalk.dim };
  return (colors[p] || chalk.white)(p.padEnd(2));
}

function statusColor(s) {
  const colors = { backlog: chalk.dim, doing: chalk.cyan, review: chalk.yellow, done: chalk.green, cancelled: chalk.strikethrough };
  return (colors[s] || chalk.white)(s.padEnd(10));
}
