/**
 * Lightweight YAML frontmatter parser/serializer.
 * No external dependencies — regex-based.
 */

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;

export function parseFrontmatter(content) {
  const match = content.match(FRONTMATTER_RE);
  if (!match) return { data: {}, body: content };

  const raw = match[1];
  const body = match[2];
  const data = {};

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const colonIdx = trimmed.indexOf(':');
    if (colonIdx === -1) continue;

    const key = trimmed.slice(0, colonIdx).trim();
    const rawVal = trimmed.slice(colonIdx + 1).trim();
    data[key] = parseValue(rawVal);
  }

  return { data, body };
}

function parseValue(raw) {
  if (raw === '' || raw === 'null') return null;
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  if (/^\d+$/.test(raw)) return parseInt(raw, 10);
  if (/^\d+\.\d+$/.test(raw)) return parseFloat(raw);

  if (raw.startsWith('[') && raw.endsWith(']')) {
    return raw
      .slice(1, -1)
      .split(',')
      .map(s => s.trim())
      .filter(Boolean)
      .map(s => parseValue(s));
  }

  if ((raw.startsWith('"') && raw.endsWith('"')) ||
      (raw.startsWith("'") && raw.endsWith("'"))) {
    return raw.slice(1, -1);
  }

  return raw;
}

export function serializeFrontmatter(data, body) {
  const lines = ['---'];
  for (const [key, val] of Object.entries(data)) {
    lines.push(`${key}: ${serializeValue(val)}`);
  }
  lines.push('---');
  if (body) lines.push('', body);
  return lines.join('\n');
}

function serializeValue(val) {
  if (val === null || val === undefined) return 'null';
  if (typeof val === 'boolean') return String(val);
  if (typeof val === 'number') return String(val);
  if (Array.isArray(val)) {
    if (val.length === 0) return 'null';
    return val.join(', ');
  }
  return String(val);
}
