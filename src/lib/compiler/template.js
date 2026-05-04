/**
 * Simple template resolver: replaces {{variable}} with config values.
 * Supports dot notation: {{project.name}}, {{commands.boardCli}}
 */
export function resolveTemplate(template, config) {
  return template.replace(/\{\{([^}]+)\}\}/g, (match, key) => {
    const trimmed = key.trim();
    const value = getNestedValue(config, trimmed);
    if (value === undefined) return match;
    return String(value);
  });
}

function getNestedValue(obj, key) {
  const parts = key.split('.');
  let current = obj;
  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    current = current[part];
  }
  return current;
}
