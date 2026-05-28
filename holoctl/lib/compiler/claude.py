from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from ..markdown import parse_frontmatter
from . import hooks_emit, mcp_emit, memory_emit
from .manifest import CompileLedger
from .template import load_bootstrap, resolve_template

_MODEL_MAP = {"fast": "haiku", "standard": "sonnet", "reasoning": "opus"}
_TOOL_MAP = {
    "read": "Read",
    "search": "Grep, Glob",
    "edit": "Edit",
    "write": "Write",
    "shell": "Bash",
    "browser": "WebSearch, WebFetch",
}


def compile_claude(
    project_root: Path,
    config: dict,
    dry_run: bool = False,
    ledger: CompileLedger | None = None,
) -> dict:
    """Compile ``.holoctl/`` into Claude Code's native config under ``.claude/``.

    Generated files are emitted **clean** (no header) and tracked via the
    ``ledger`` (``.holoctl/.compiled.json``). When called without a ledger
    (e.g. tests, the drift scratch compile), a self-contained one is created
    and finalized here so the call still produces a manifest + prunes orphans.
    """
    owns_ledger = ledger is None
    if ledger is None:
        from ._safe_write import force as _force
        ledger = CompileLedger.for_target(
            project_root, "claude", dry_run=dry_run, force=_force()
        )

    files: list[str] = []
    # CLAUDE.md's bespoke preserve notes land directly in the ledger's skip
    # list, so the ledger is the single source of truth for "what we left alone".
    skipped: list[dict] = ledger.skipped

    agents_dir = project_root / ".holoctl" / "agents"
    claude_agents_dir = project_root / ".claude" / "agents"

    if agents_dir.exists():
        if not dry_run:
            claude_agents_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(agents_dir.glob("*.md")):
            data_fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
            # Build Claude-native frontmatter. Filters out holoctl-private metadata
            # (`when_to_suggest`, `trigger`, `tools`-as-categories) which the
            # curator reads from the source files but Claude Code does not need.
            fm_lines = [
                "---",
                f"name: {data_fm.get('name', f.stem)}",
                f"description: {data_fm.get('description', '')}",
                f"tools: {_map_tools(data_fm.get('tools'))}",
                f"model: {_MODEL_MAP.get(data_fm.get('model', 'standard'), data_fm.get('model', 'sonnet'))}",
            ]
            # `paths:` is Claude Code-native auto-trigger for subagents.
            paths_val = data_fm.get("paths")
            if paths_val:
                if isinstance(paths_val, list):
                    fm_lines.append("paths:")
                    for p in paths_val:
                        fm_lines.append(f"  - {p}")
                else:
                    # Comma-separated string fallback.
                    fm_lines.append("paths:")
                    for p in str(paths_val).split(","):
                        p = p.strip()
                        if p:
                            fm_lines.append(f"  - {p}")
            fm_lines.append("---")
            frontmatter = "\n".join(fm_lines)
            resolved_body = resolve_template(body, config)
            output = frontmatter + "\n" + resolved_body
            out_path = f".claude/agents/{f.name}"
            if ledger.write(out_path, output, source=f".holoctl/agents/{f.name}", target="claude"):
                files.append(out_path)

    commands_dir = project_root / ".holoctl" / "commands"
    claude_commands_dir = project_root / ".claude" / "commands"

    if commands_dir.exists():
        if not dry_run:
            claude_commands_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(commands_dir.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            output = resolve_template(content, config)
            out_path = f".claude/commands/{f.name}"
            if ledger.write(out_path, output, source=f".holoctl/commands/{f.name}", target="claude"):
                files.append(out_path)

    instructions_path = project_root / ".holoctl" / "instructions.md"
    if instructions_path.exists():
        content = instructions_path.read_text(encoding="utf-8")
        rendered = resolve_template(content, config)
        # Append a memory pointer block when .holoctl/memory/ exists. Coexists
        # with Claude's native auto-memory (item 11 of the multi-assistant plan).
        if (project_root / ".holoctl" / "memory").exists():
            rendered = rendered.rstrip() + memory_emit.claude_memory_reference_block()
        output = rendered
        out_path = "CLAUDE.md"
        claude_md_path = project_root / out_path
        # M11: CLAUDE.md gets defensive treatment — if genuinely hand-edited
        # (not owned, not legacy), preserve via rename to CLAUDE.local.md instead
        # of skip-or-overwrite. Ownership is decided by the ledger/manifest.
        if not dry_run:
            wrote = _materialize_claude_md(
                claude_md_path, output, out_path, ledger, skipped=skipped
            )
            if wrote:
                files.append(out_path)
        else:
            # Dry-run: record in the ledger so it's tracked, write nothing.
            ledger.record_text(out_path, output, source=".holoctl/instructions.md", target="claude")
            files.append(out_path)

    # Path-scoped rules → .claude/rules/<name>.md (with `paths:` frontmatter)
    rules_src = project_root / ".holoctl" / "rules"
    if rules_src.exists():
        rules_out = project_root / ".claude" / "rules"
        if not dry_run:
            rules_out.mkdir(parents=True, exist_ok=True)
        for f in sorted(rules_src.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            output = resolve_template(content, config)
            out_path = f".claude/rules/{f.name}"
            if ledger.write(out_path, output, source=f".holoctl/rules/{f.name}", target="claude"):
                files.append(out_path)

    # Built-in skills shipped with the holoctl package — reactive skills that
    # the agent auto-triggers via `description:` matching. These live in
    # `holoctl/templates/skills/` and are emitted on every compile.
    files.extend(_emit_builtin_skills(project_root, config, ledger, dry_run=dry_run))

    # Custom skills (with progressive disclosure) → .claude/skills/<name>/
    skills_src = project_root / ".holoctl" / "skills"
    if skills_src.exists():
        for skill_dir in sorted(p for p in skills_src.iterdir() if p.is_dir()):
            name = skill_dir.name
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            out_dir = project_root / ".claude" / "skills" / name
            if not dry_run:
                out_dir.mkdir(parents=True, exist_ok=True)
            content = skill_md.read_text(encoding="utf-8")
            out_path = f".claude/skills/{name}/SKILL.md"
            if ledger.write(
                out_path, resolve_template(content, config),
                source=f".holoctl/skills/{name}", target="claude",
            ):
                files.append(out_path)
            # Sync support files (references/, scripts/, templates/) per-file
            # through the ledger so they are manifest-tracked and orphans are
            # pruned automatically. No rmtree: user-added files under
            # .claude/skills/<name>/ that holoctl never generated are preserved
            # (foreign, not in manifest) and never silently deleted.
            for support in ("references", "scripts", "templates"):
                support_src = skill_dir / support
                if support_src.exists():
                    for sf in sorted(support_src.rglob("*")):
                        if not sf.is_file():
                            continue
                        rel_within = sf.relative_to(skill_dir)
                        rel_out = f".claude/skills/{name}/{rel_within.as_posix()}"
                        if ledger.write_bytes(
                            rel_out, sf,
                            source=f".holoctl/skills/{name}",
                            target="claude",
                        ):
                            files.append(rel_out)

    # Output styles → .claude/output_styles/<name>.md (Claude Code-specific)
    styles_src = project_root / ".holoctl" / "output_styles"
    if styles_src.exists():
        styles_out = project_root / ".claude" / "output_styles"
        if not dry_run:
            styles_out.mkdir(parents=True, exist_ok=True)
        for f in sorted(styles_src.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            out_path = f".claude/output_styles/{f.name}"
            if ledger.write(
                out_path, resolve_template(content, config),
                source=f".holoctl/output_styles/{f.name}", target="claude",
            ):
                files.append(out_path)

    # Memory topics → .claude/skills/holoctl-memory-*/SKILL.md
    files.extend(memory_emit.emit_claude(project_root, ledger, dry_run=dry_run))

    # Hooks (journal/curator) + write-tool permissions → .claude/settings.json
    files.extend(hooks_emit.emit_claude(project_root, dry_run=dry_run))

    # MCP server config → .claude/settings.json:mcpServers.holoctl
    files.extend(mcp_emit.emit_claude(project_root, dry_run=dry_run))

    bootstrap = load_bootstrap("holoctl-claude.md")
    if bootstrap:
        out_path = ".claude/commands/holoctl.md"
        if not dry_run:
            claude_commands_dir.mkdir(parents=True, exist_ok=True)
            (project_root / out_path).write_text(bootstrap, encoding="utf-8")
        files.append(out_path)

    upgrade_bootstrap = load_bootstrap("hctl-upgrade-claude.md")
    if upgrade_bootstrap:
        out_path = ".claude/commands/hctl-upgrade.md"
        if not dry_run:
            claude_commands_dir.mkdir(parents=True, exist_ok=True)
            (project_root / out_path).write_text(upgrade_bootstrap, encoding="utf-8")
        files.append(out_path)

    # When this function owns the ledger (no orchestrator passed one), finalize
    # here so a direct call still prunes orphans + writes the manifest.
    if owns_ledger:
        from ... import __version__ as _ver
        ledger.prune_orphans()
        ledger.finalize(holoctl_version=_ver)

    # `skipped` IS `ledger.skipped` (same list), so it now holds both CLAUDE.md
    # preserve notes and the ledger's foreign/hand-edited + orphan skip notes.
    result: dict[str, object] = {"files": files}
    if skipped:
        result["skipped"] = skipped
    return result


def _map_tools(tools) -> str:
    if not tools:
        return "Read, Grep, Glob, Edit, Write, Bash"
    arr = tools if isinstance(tools, list) else [t.strip() for t in str(tools).split(",")]
    return ", ".join(str(_TOOL_MAP.get(t, t)) for t in arr)


def _materialize_claude_md(
    claude_md_path: Path,
    generated_content: str,
    rel: str,
    ledger: CompileLedger,
    *,
    skipped: list[dict],
) -> bool:
    """Write CLAUDE.md, preserving any hand-edited content via rename.

    Ownership is decided by the manifest (via the ledger), not the header:
      - File doesn't exist → write new + record in the manifest.
      - File is holoctl-owned-unmodified OR carries the legacy header (adoption)
        → safe to overwrite + record.
      - File is genuinely hand-edited (not owned, not legacy):
          - `--force` → backup to `.claude/.cache/CLAUDE.backup-<ts>.md`,
            overwrite, record, append skip note.
          - otherwise → rename to `CLAUDE.local.md` to preserve, write new,
            record, append skip note.

    Always records the generated content in the manifest so the next compile
    recognizes CLAUDE.md as owned (the file we materialize IS ours regardless
    of which branch we took).
    """
    def _record() -> None:
        ledger.record_text(rel, generated_content, source=".holoctl/instructions.md", target="claude")

    if not claude_md_path.exists():
        claude_md_path.parent.mkdir(parents=True, exist_ok=True)
        claude_md_path.write_text(generated_content, encoding="utf-8")
        _record()
        return True

    if ledger.is_owned_text(rel) or ledger.is_legacy(rel):
        # Ours (tracked or legacy-headered) — safe to regenerate.
        claude_md_path.write_text(generated_content, encoding="utf-8")
        _record()
        return True

    existing = claude_md_path.read_text(encoding="utf-8")

    # Genuinely hand-edited (foreign / drifted).
    if ledger.force:
        backup_dir = claude_md_path.parent / ".claude" / ".cache"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"CLAUDE.backup-{ts}.md"
        backup_path.write_text(existing, encoding="utf-8")
        claude_md_path.write_text(generated_content, encoding="utf-8")
        _record()
        skipped.append({
            "path": str(claude_md_path),
            "reason": f"hand-edited; backed up to {backup_path.relative_to(claude_md_path.parent)} before overwrite (--force)",
        })
        return True

    # Default: preserve via rename.
    local_path = claude_md_path.with_name("CLAUDE.local.md")
    if local_path.exists():
        # Don't clobber an existing CLAUDE.local.md either.
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        local_path = claude_md_path.with_name(f"CLAUDE.local.{ts}.md")
    claude_md_path.rename(local_path)
    claude_md_path.write_text(generated_content, encoding="utf-8")
    _record()
    skipped.append({
        "path": str(claude_md_path),
        "reason": (
            f"hand-edited CLAUDE.md preserved as {local_path.name}; "
            f"move its content into .holoctl/instructions.md or pass --force to overwrite"
        ),
    })
    return True


def _emit_builtin_skills(
    project_root: Path,
    config: dict,
    ledger: CompileLedger,
    dry_run: bool = False,
) -> list[str]:
    """Copy built-in reactive skills from the holoctl package into `.claude/skills/`.

    Each subdir of `holoctl/templates/skills/` becomes a skill. Templates are
    resolved against `config` so `{{project.name}}` etc. work. The SKILL.md goes
    through the ledger (manifest-tracked, headerless). Support files
    (`references/`, `scripts/`, `templates/`) are synced per-file through the
    ledger (manifest-tracked, hand-edit-guarded, pruned on removal).

    Override contract
    -----------------
    If `.holoctl/skills/<name>/SKILL.md` exists for a given built-in name, that
    built-in is **skipped** here entirely — the custom-skills loop (which runs
    immediately after this function) will emit the user's version to the same
    `.claude/skills/<name>/SKILL.md` path. This gives users an explicit, safe
    override mechanism: drop a `SKILL.md` in `.holoctl/skills/<name>/` and the
    built-in is shadowed without any fragile write-order dependency.
    """
    files: list[str] = []
    try:
        from importlib.resources import files as _ires_files
        skills_root = _ires_files("holoctl") / "templates" / "skills"
    except (ModuleNotFoundError, AttributeError):
        skills_root = (
            Path(__file__).resolve().parent.parent.parent / "templates" / "skills"
        )
    # `importlib.resources` returns a Traversable; convert to Path when possible.
    skills_root_path = Path(str(skills_root))
    if not skills_root_path.exists():
        return []

    out_skills_dir = project_root / ".claude" / "skills"
    # Pre-compute the set of built-in names that have a custom override so we
    # can skip them in a single fast check per skill dir.
    custom_skills_src = project_root / ".holoctl" / "skills"

    for skill_dir in sorted(p for p in skills_root_path.iterdir() if p.is_dir()):
        name = skill_dir.name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        # Override check: if the user has placed a SKILL.md in
        # .holoctl/skills/<name>/, skip emitting the built-in. The custom-skills
        # loop (directly below in compile_claude) will emit the user's version.
        if (custom_skills_src / name / "SKILL.md").exists():
            continue

        out_dir = out_skills_dir / name
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
        content = skill_md.read_text(encoding="utf-8")
        out_skill_path = f".claude/skills/{name}/SKILL.md"
        if ledger.write(
            out_skill_path, resolve_template(content, config),
            source="builtin", target="claude",
        ):
            files.append(out_skill_path)
        # Sync support files per-file through the ledger. Orphaned support files
        # (removed from the built-in source) are pruned automatically by
        # prune_orphans() at the end of the compile. User-added files under
        # .claude/skills/<name>/ that holoctl never generated are never pruned.
        for support in ("references", "scripts", "templates"):
            support_src = skill_dir / support
            if support_src.exists():
                for sf in sorted(support_src.rglob("*")):
                    if not sf.is_file():
                        continue
                    rel_within = sf.relative_to(skill_dir)
                    rel_out = f".claude/skills/{name}/{rel_within.as_posix()}"
                    if ledger.write_bytes(
                        rel_out, sf,
                        source="builtin",
                        target="claude",
                    ):
                        files.append(rel_out)
    return files
