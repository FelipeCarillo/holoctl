"""Tests for v0.17 expanded agent_suggest heuristics — dba/devops/security/docs signals."""
from __future__ import annotations
from pathlib import Path

from holoctl.cli.agent import (
    _detect_dba_signals,
    _detect_devops_signals,
    _detect_security_signals,
    _detect_docs_signals,
    _detect_suggestions,
)


def test_dba_signals_detect_sql_files(tmp_path: Path):
    (tmp_path / "schema.sql").write_text("CREATE TABLE users (id INT);", encoding="utf-8")
    (tmp_path / "seed.sql").write_text("INSERT INTO users VALUES (1);", encoding="utf-8")
    (tmp_path / "queries.sql").write_text("SELECT * FROM users;", encoding="utf-8")
    reasons = _detect_dba_signals(tmp_path)
    assert any("*.sql" in r for r in reasons)


def test_dba_signals_detect_migrations_dir(tmp_path: Path):
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "0001_init.sql").write_text("--", encoding="utf-8")
    reasons = _detect_dba_signals(tmp_path)
    assert any("migrations" in r for r in reasons)


def test_dba_signals_detect_prisma(tmp_path: Path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text("// schema", encoding="utf-8")
    reasons = _detect_dba_signals(tmp_path)
    assert any("prisma" in r for r in reasons)


def test_dba_signals_skip_node_modules(tmp_path: Path):
    """SQL files inside node_modules don't count."""
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    for i in range(5):
        (tmp_path / "node_modules" / "pkg" / f"{i}.sql").write_text("--", encoding="utf-8")
    reasons = _detect_dba_signals(tmp_path)
    assert not reasons


def test_devops_signals_detect_workflows(tmp_path: Path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci", encoding="utf-8")
    reasons = _detect_devops_signals(tmp_path)
    assert any("Actions" in r for r in reasons)


def test_devops_signals_detect_dockerfile(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.13", encoding="utf-8")
    reasons = _detect_devops_signals(tmp_path)
    assert any("Dockerfile" in r for r in reasons)


def test_devops_signals_detect_terraform(tmp_path: Path):
    (tmp_path / "terraform").mkdir()
    (tmp_path / "terraform" / "main.tf").write_text("resource", encoding="utf-8")
    reasons = _detect_devops_signals(tmp_path)
    assert any("Terraform" in r for r in reasons)


def test_devops_signals_detect_k8s(tmp_path: Path):
    (tmp_path / "k8s").mkdir()
    reasons = _detect_devops_signals(tmp_path)
    assert any("k8s" in r for r in reasons)


def test_security_signals_detect_security_md(tmp_path: Path):
    (tmp_path / "SECURITY.md").write_text("# Security", encoding="utf-8")
    reasons = _detect_security_signals(tmp_path)
    assert any("SECURITY.md" in r for r in reasons)


def test_security_signals_detect_audit_configs(tmp_path: Path):
    (tmp_path / ".snyk").write_text("ignore: {}", encoding="utf-8")
    reasons = _detect_security_signals(tmp_path)
    assert any(".snyk" in r for r in reasons)


def test_docs_signals_detect_docs_dir_large(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(12):
        (docs / f"page{i}.md").write_text("# x", encoding="utf-8")
    reasons = _detect_docs_signals(tmp_path)
    assert any(">10" in r for r in reasons)


def test_docs_signals_detect_active_changelog(tmp_path: Path):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n" + ("entry " * 500), encoding="utf-8")
    reasons = _detect_docs_signals(tmp_path)
    assert any("CHANGELOG" in r for r in reasons)


def test_full_suggest_includes_new_personas(tmp_path: Path):
    """End-to-end: a project with mixed signals gets multiple persona suggestions."""
    # Code package + tests.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    # Migrations + SQL.
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001.sql").write_text("--", encoding="utf-8")
    (tmp_path / "schema.sql").write_text("--", encoding="utf-8")
    (tmp_path / "queries.sql").write_text("--", encoding="utf-8")
    (tmp_path / "more.sql").write_text("--", encoding="utf-8")
    # Workflows.
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci", encoding="utf-8")
    # SECURITY.md.
    (tmp_path / "SECURITY.md").write_text("# Security", encoding="utf-8")
    # Docs.
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(11):
        (docs / f"p{i}.md").write_text("# x", encoding="utf-8")

    suggestions = _detect_suggestions(tmp_path)
    names = {s["name"] for s in suggestions}
    assert {"developer", "reviewer", "dba", "devops", "security-auditor", "tech-writer"}.issubset(names)
