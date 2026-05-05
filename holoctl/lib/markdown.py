from __future__ import annotations
import re
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    raw, body = match.group(1), match.group(2)
    data: dict = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        idx = line.find(":")
        if idx == -1:
            continue
        key = line[:idx].strip()
        raw_val = line[idx + 1:].strip()
        data[key] = _parse_value(raw_val)

    return data, body


def _parse_value(raw: str) -> Any:
    if raw in ("", "null"):
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    if re.fullmatch(r"\d+\.\d+", raw):
        return float(raw)
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1]
        return [_parse_value(s.strip()) for s in inner.split(",") if s.strip()]
    if (raw.startswith('"') and raw.endswith('"')) or \
       (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    return raw


def serialize_frontmatter(data: dict, body: str = "") -> str:
    lines = ["---"]
    for key, val in data.items():
        lines.append(f"{key}: {_serialize_value(val)}")
    lines.append("---")
    if body:
        lines.append("")
        lines.append(body)
    return "\n".join(lines)


def _serialize_value(val: Any) -> str:
    if val is None:
        return "null"
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        if not val:
            return "null"
        return ", ".join(str(v) for v in val)
    return str(val)
