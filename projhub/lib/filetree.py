from __future__ import annotations
import json
from pathlib import Path

_SKIP_DIRS = {
    "node_modules", "dist", "build", ".next", "out", "target",
    "__pycache__", ".venv", "venv", ".tox", "coverage",
    ".turbo", ".parcel-cache", ".cache",
}

_BADGE_RULES = [
    {"files": [".git"], "badge": "git", "label": "Git"},
    {"files": ["package.json"], "badge": "node", "label": "Node", "detect": "_detect_node"},
    {"files": ["pyproject.toml", "requirements.txt", "setup.py"], "badge": "python", "label": "Python"},
    {"files": ["go.mod"], "badge": "go", "label": "Go"},
    {"files": ["Cargo.toml"], "badge": "rust", "label": "Rust"},
    {"files": ["pubspec.yaml"], "badge": "flutter", "label": "Flutter"},
    {"files": ["build.gradle", "pom.xml", "build.gradle.kts"], "badge": "java", "label": "Java"},
    {"files": ["composer.json"], "badge": "php", "label": "PHP"},
    {"files": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"], "badge": "docker", "label": "Docker"},
]


def _detect_node(dir_path: Path) -> str:
    try:
        pkg = json.loads((dir_path / "package.json").read_text(encoding="utf-8"))
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "react" in deps or "next" in deps:
            return "React"
        if "vue" in deps or "nuxt" in deps:
            return "Vue"
        if "svelte" in deps or "@sveltejs/kit" in deps:
            return "Svelte"
        if "express" in deps or "fastify" in deps or "hono" in deps:
            return "Server"
        if "react-native" in deps or "expo" in deps:
            return "React Native"
        if "electron" in deps:
            return "Electron"
    except Exception:
        pass
    return "Node"


def _detect_badges(dir_path: Path) -> list[dict]:
    try:
        entries = {e.name.lower() for e in dir_path.iterdir()}
    except Exception:
        entries = set()

    badges = []
    for rule in _BADGE_RULES:
        hit = any(f.lower() in entries for f in rule["files"])
        if hit:
            label = _detect_node(dir_path) if rule.get("detect") == "_detect_node" else rule["label"]
            badges.append({"badge": rule["badge"], "label": label})

    # Terraform .tf files
    if not any(b["badge"] == "terraform" for b in badges):
        if any(e.endswith(".tf") for e in entries):
            badges.append({"badge": "terraform", "label": "Terraform"})

    # Xcode
    if any(e.endswith(".xcodeproj") or e.endswith(".xcworkspace") for e in entries):
        badges.append({"badge": "ios", "label": "iOS"})

    return badges


def scan_dir(abs_path: Path, depth: int = 0, max_depth: int = 1, skip_hidden: bool = False) -> list[dict]:
    if not abs_path.exists():
        return []

    try:
        entries = list(abs_path.iterdir())
    except Exception:
        return []

    result = []
    for entry in entries:
        if skip_hidden and entry.name.startswith(".") and entry.name != ".projhub":
            continue

        if entry.is_dir():
            if entry.name in _SKIP_DIRS:
                continue
            badges = _detect_badges(entry)
            children = scan_dir(entry, depth + 1, max_depth, skip_hidden) if depth < max_depth else None
            result.append({
                "name": entry.name,
                "type": "dir",
                "path": entry.name,
                "badges": badges,
                "hasChildren": True,
                "children": children,
            })
        else:
            result.append({
                "name": entry.name,
                "type": "file",
                "path": entry.name,
                "badges": [],
                "ext": entry.suffix.lstrip(".").lower(),
            })

    result.sort(key=lambda x: (0 if x["type"] == "dir" else 1, x["name"].lower()))
    return result
