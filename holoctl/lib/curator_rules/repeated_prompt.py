"""Detect repeated prompts → propose extracting a slash command / skill.

Detection strategy (item 6 of the multi-assistant plan):
  - Default: token-hash matching. Catches near-exact repeats, misses paraphrase.
    No extra dependencies.
  - Optional: `pip install holoctl[ml]` brings in fastembed (~250MB ONNX,
    avoids the 700MB torch from sentence-transformers). When available,
    prompts are matched via cosine similarity ≥ 0.85 on local embeddings.

Either mode produces the same Suggestion shape; the difference is just
recall on paraphrase.
"""
from __future__ import annotations

import re
from collections import Counter

from ..curator import CuratorContext, Suggestion, hash_pattern


THRESHOLD_REPEATS = 3
SIMILARITY_THRESHOLD = 0.85


def run(ctx: CuratorContext) -> list[Suggestion]:
    prompts: list[str] = []
    for r in ctx.journal.iter_records(kind="user_prompt"):
        payload = r.get("payload") or {}
        text = payload.get("text") or payload.get("prompt")
        if isinstance(text, str) and text.strip():
            prompts.append(text.strip())
    if not prompts:
        return []
    clusters = _cluster(prompts)
    out: list[Suggestion] = []
    for representative, count in clusters:
        if count < THRESHOLD_REPEATS:
            continue
        pid = hash_pattern("repeated_prompt", representative)
        # Use the first 6 words as a slug.
        words = re.findall(r"[a-z0-9]+", representative.lower())[:5]
        slug = "-".join(words) or "repeat"
        out.append(Suggestion(
            pattern_id=pid,
            rule="repeated_prompt",
            title=f"Curate: extract skill for repeated prompt ({count}× '{representative[:40]}…')",
            rationale=(
                f"You've issued a similar prompt {count} times. Extracting it "
                f"as a slash command / skill turns it into a one-token call "
                f"and lets you refine the spec in one place. Representative: "
                f"\"{representative}\""
            ),
            action="memory_promote",
            args={
                "name": f"prompt-{slug}",
                "body": (
                    f"# Repeated prompt: {representative[:60]}\n\n"
                    f"Detected {count} times in recent sessions. Promote to a "
                    f"durable note here, then refine into a slash command.\n\n"
                    f"## Original\n\n> {representative}\n"
                ),
                "description": f"Note about repeated prompt: {representative[:50]}",
            },
        ))
    return out


def _cluster(prompts: list[str]) -> list[tuple[str, int]]:
    """Return (representative, count) tuples, sorted by count desc.

    Tries fastembed (item 6 [ml] extra) first; falls back to token-set hash.
    """
    try:
        return _cluster_embeddings(prompts)
    except (ImportError, RuntimeError, Exception):  # noqa: BLE001
        return _cluster_hash(prompts)


def _cluster_hash(prompts: list[str]) -> list[tuple[str, int]]:
    """Bucket by sorted unique-token tuple. Catches exact + word-reorder."""
    buckets: dict[tuple[str, ...], list[str]] = {}
    for p in prompts:
        toks = tuple(sorted(set(_tokenize(p))))
        if not toks:
            continue
        buckets.setdefault(toks, []).append(p)
    out = [(v[0], len(v)) for v in buckets.values()]
    out.sort(key=lambda x: -x[1])
    return out


def _cluster_embeddings(prompts: list[str]) -> list[tuple[str, int]]:
    from fastembed import TextEmbedding  # type: ignore
    model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vectors = list(model.embed(prompts))
    # Greedy clustering: each prompt joins the first cluster whose centroid
    # has cosine >= threshold; otherwise starts a new cluster.
    clusters: list[dict] = []
    for prompt, v in zip(prompts, vectors):
        joined = False
        for c in clusters:
            if _cos(v, c["centroid"]) >= SIMILARITY_THRESHOLD:
                c["members"].append(prompt)
                c["centroid"] = _mean([c["centroid"], v])
                joined = True
                break
        if not joined:
            clusters.append({"members": [prompt], "centroid": v})
    out = [(c["members"][0], len(c["members"])) for c in clusters]
    out.sort(key=lambda x: -x[1])
    return out


def _tokenize(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) >= 3]


def _cos(a, b) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _mean(vectors):
    n = len(vectors)
    if n == 0:
        return []
    length = len(vectors[0])
    return [sum(v[i] for v in vectors) / n for i in range(length)]
