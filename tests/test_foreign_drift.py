"""Task 5.5 — foreign-config drift detection (lightweight contract test).

The `holoctl-foreign-bootstrap` skill must instruct non-Claude assistants to
(a) record what they generate in `.holoctl/.foreign-compiled.json`, and
(b) on re-bootstrap, WARN before overwriting any generated file whose on-disk
hash diverges from the recorded one (treat as a hand-edit). This is prose; the
test asserts the drift-guard instructions and manifest filename are present in
the shipped skill AND in the inlined `.holoctl/foreign-bootstrap.md` body.
"""
from __future__ import annotations

from pathlib import Path

from holoctl.lib.compiler.agents import _foreign_bootstrap_body

MANIFEST_NAME = ".holoctl/.foreign-compiled.json"


def _skill_md_text() -> str:
    root = Path(__file__).resolve().parent.parent / "holoctl"
    skill = root / "templates" / "skills" / "holoctl-foreign-bootstrap" / "SKILL.md"
    return skill.read_text(encoding="utf-8")


def test_skill_text_names_the_foreign_manifest():
    text = _skill_md_text()
    assert MANIFEST_NAME in text


def test_skill_text_has_drift_guard_instructions():
    text = _skill_md_text().lower()
    # Must tell the assistant to warn before overwriting a divergent file.
    assert "warn" in text
    assert "overwrit" in text  # overwrite / overwriting
    assert "hash" in text
    assert "hand-edit" in text


def test_skill_text_describes_recording_then_comparing():
    text = _skill_md_text().lower()
    assert "sha256" in text or "sha-256" in text
    # Records on generate, compares on re-bootstrap.
    assert "re-bootstrap" in text or "re-run" in text


def test_inlined_foreign_bootstrap_body_carries_drift_guard():
    """The standalone `.holoctl/foreign-bootstrap.md` body (skill frontmatter
    stripped, hints inlined) must also carry the guard so AGENTS.md-pointed
    assistants get it without the skill packaging."""
    body = _foreign_bootstrap_body()
    assert MANIFEST_NAME in body
    low = body.lower()
    assert "warn" in low and "overwrit" in low and "hand-edit" in low
