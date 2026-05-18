"""Built-in curator rules.

Each rule is a callable ``(CuratorContext) -> list[Suggestion]``. A rule
should be cheap (∼ms per call) and side-effect-free — emitting a
Suggestion is just appending to a list, never writing to disk.
"""
from __future__ import annotations

from typing import Callable

from . import (
    library_persona_match,
    repeated_glob_edits,
    repeated_prompt,
    unused_topic,
)


def builtin_rules() -> list[Callable]:
    return [
        repeated_glob_edits.run,
        repeated_prompt.run,
        unused_topic.run,
        library_persona_match.run,
    ]
