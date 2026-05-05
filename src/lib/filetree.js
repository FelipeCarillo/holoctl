import fs from 'node:fs';
import path from 'node:path';

const SKIP_DIRS = new Set([
  'node_modules', 'dist', 'build', '.next', 'out', 'target',
  '__pycache__', '.venv', 'venv', '.tox', 'coverage',
  '.turbo', '.parcel-cache', '.cache',
]);

const BADGE_RULES = [
  { files: ['.git'], badge: 'git', label: 'Git' },
  { files: ['package.json'], badge: 'node', label: 'Node', detect: detectNodeFramework },
  { files: ['pyproject.toml', 'requirements.txt', 'setup.py'], badge: 'python', label: 'Python' },
  { files: ['go.mod'], badge: 'go', label: 'Go' },
  { files: ['Cargo.toml'], badge: 'rust', label: 'Rust' },
  { files: ['pubspec.yaml'], badge: 'flutter', label: 'Flutter' },
  { files: ['build.gradle', 'pom.xml', 'build.gradle.kts'], badge: 'java', label: 'Java' },
  { files: ['composer.json'], badge: 'php', label: 'PHP' },
  { files: ['Dockerfile', 'docker-compose.yml', 'docker-compose.yaml'], badge: 'docker', label: 'Docker' },
  { files: ['terraform'], badge: 'terraform', label: 'Terraform', isDir: true },
];

function detectNodeFramework(dirPath) {
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(dirPath, 'package.json'), 'utf8'));
    const deps = { ...pkg.dependencies, ...pkg.devDependencies };
    if (deps['react'] || deps['next']) return 'React';
    if (deps['vue'] || deps['nuxt']) return 'Vue';
    if (deps['svelte'] || deps['@sveltejs/kit']) return 'Svelte';
    if (deps['express'] || deps['fastify'] || deps['hono']) return 'Server';
    if (deps['react-native'] || deps['expo']) return 'React Native';
    if (deps['electron']) return 'Electron';
  } catch {}
  return 'Node';
}

function detectBadges(dirPath) {
  const entries = new Set(
    fs.existsSync(dirPath)
      ? fs.readdirSync(dirPath).map(e => e.toLowerCase())
      : []
  );
  const badges = [];

  for (const rule of BADGE_RULES) {
    const hit = rule.files.some(f => {
      if (rule.isDir) return entries.has(f.toLowerCase()) &&
        fs.statSync(path.join(dirPath, f)).isDirectory();
      return entries.has(f.toLowerCase());
    });
    if (hit) {
      const label = rule.detect ? rule.detect(dirPath) : rule.label;
      badges.push({ badge: rule.badge, label });
    }
  }

  // Detect .tf files for terraform (without terraform/ dir)
  if (!badges.find(b => b.badge === 'terraform')) {
    const hasTf = [...entries].some(e => e.endsWith('.tf'));
    if (hasTf) badges.push({ badge: 'terraform', label: 'Terraform' });
  }

  // Detect Xcode
  const hasXcode = [...entries].some(e => e.endsWith('.xcodeproj') || e.endsWith('.xcworkspace'));
  if (hasXcode) badges.push({ badge: 'ios', label: 'iOS' });

  return badges;
}

export function scanDir(absPath, opts = {}) {
  const { depth = 0, maxDepth = 1, skipHidden = false } = opts;

  if (!fs.existsSync(absPath)) return [];

  let entries;
  try {
    entries = fs.readdirSync(absPath, { withFileTypes: true });
  } catch {
    return [];
  }

  const result = [];

  for (const entry of entries) {
    if (skipHidden && entry.name.startsWith('.') && entry.name !== '.holoctl') continue;

    const entryPath = path.join(absPath, entry.name);
    const relPath = entry.name;

    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;

      const badges = detectBadges(entryPath);
      const node = {
        name: entry.name,
        type: 'dir',
        path: relPath,
        badges,
        hasChildren: true,
        children: depth < maxDepth ? scanDir(entryPath, { ...opts, depth: depth + 1 }) : null,
      };
      result.push(node);
    } else {
      result.push({
        name: entry.name,
        type: 'file',
        path: relPath,
        badges: [],
        ext: path.extname(entry.name).slice(1).toLowerCase(),
      });
    }
  }

  // Dirs first, then files, both alphabetically
  result.sort((a, b) => {
    if (a.type !== b.type) return a.type === 'dir' ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  return result;
}
