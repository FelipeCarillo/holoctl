from __future__ import annotations
import re
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$")

# Characters that, when present in a bare scalar, make it ambiguous to the
# parser (or to a downstream YAML reader) and therefore force quoting on
# serialize so the value survives a round-trip.
#   - a leading char that collides with YAML flow/indicator syntax
#   - a trailing colon (would look like a key)
# We deliberately keep this conservative: most values (URLs with `https://`,
# titles with a mid-string `:`) round-trip fine unquoted because the parser
# splits on the *first* colon only.


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
        key, sep, raw_val = _split_key_value(line)
        if not sep:
            continue
        data[key] = _parse_value(raw_val.strip())

    return data, body


def _split_key_value(line: str) -> tuple[str, bool, str]:
    """Split a frontmatter line into ``(key, found, value)``.

    The key is everything up to the first colon that is *not* inside a quoted
    string. This keeps keys correct while letting values carry colons (e.g.
    ``source_url: "https://example.com/x"``). Falls back to the first bare
    colon for unquoted values like ``source_url: https://example.com`` — the
    URL's ``https:`` colon lands in the value because the key portion has no
    quotes and the split is on the first colon overall, which separates the
    key from the value.
    """
    # Find the first colon. Because keys never contain quotes or colons in this
    # schema, the first colon always terminates the key. Values may then freely
    # contain further colons (URLs, timestamps, titles).
    idx = line.find(":")
    if idx == -1:
        return line, False, ""
    return line[:idx].strip(), True, line[idx + 1 :]


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
        return [_parse_value(s.strip()) for s in _split_list_items(inner) if s.strip()]
    if (raw.startswith('"') and raw.endswith('"') and len(raw) >= 2) or (
        raw.startswith("'") and raw.endswith("'") and len(raw) >= 2
    ):
        return _unquote(raw)
    return raw


def _split_list_items(inner: str) -> list[str]:
    """Split an inline-array body on commas that are not inside quotes."""
    items: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append("".join(buf))
    return items


def _unquote(raw: str) -> str:
    q = raw[0]
    inner = raw[1:-1]
    if q == '"':
        # Honor simple backslash escapes for double-quoted scalars.
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return inner


def serialize_frontmatter(data: dict, body: str = "") -> str:
    lines = ["---"]
    for key, val in data.items():
        lines.append(f"{key}: {_serialize_value(val)}")
    lines.append("---")
    if body:
        lines.append("")
        lines.append(body)
    return "\n".join(lines)


def _needs_quoting(s: str) -> bool:
    """Whether a string scalar must be quoted to survive a parse round-trip."""
    if s == "":
        return False  # empty serializes to nothing → parses back as None; handled by None
    stripped = s.strip()
    if stripped != s:
        return True  # leading/trailing whitespace would be lost
    # A trailing colon, or a colon followed by space, makes the value look like
    # a key/mapping to the parser or a downstream YAML reader.
    if s.endswith(":") or ": " in s:
        return True
    # Leading indicator characters that have special meaning in flow context.
    # NOTE: a leading `[` is intentionally *not* forced here — see below.
    if s[0] in "{}#&*!|>'\"%@`,":
        return True
    # A value that itself looks like an inline array would be parsed as a list.
    if s.startswith("[") and s.endswith("]"):
        return True
    # NOTE: reserved scalar words (null/true/false) and bare numerics are
    # deliberately NOT quoted. The board layer uses the literal string "null"
    # as its None sentinel and expects it serialized bare as `null`; quoting
    # would round-trip it as the string "null" and break that convention.
    # Genuine None values are serialized via the `val is None` branch, not here.
    return False


def _quote(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


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
        return ", ".join(_serialize_list_item(v) for v in val)
    s = str(val)
    if _needs_quoting(s):
        return _quote(s)
    return s


def _serialize_list_item(v: Any) -> str:
    s = str(v)
    # Within a comma-joined list, an item that itself contains a comma would be
    # mis-split on parse — quote it. We keep this narrow (only commas) so the
    # board's comma-split `_normalize_array` continues to read plain items
    # (agents/tags/projects) unchanged.
    if isinstance(v, str) and "," in s:
        return _quote(s)
    return s
