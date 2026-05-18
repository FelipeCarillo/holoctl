from __future__ import annotations
import re
from datetime import datetime, tzinfo

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _parse_aware(iso: str) -> datetime | None:
    """Parse an ISO 8601 timestamp into a tz-aware `datetime`.

    Returns `None` for date-only strings, naive timestamps, or anything
    unparseable — callers fall back to regex-based extraction.
    """
    if not iso or len(iso) < 11:
        return None
    s = str(iso)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _local_tz() -> tzinfo:
    return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


def format_iso_datetime(iso: str, tz: tzinfo | None = None) -> str:
    """Pretty-print an ISO timestamp as `YYYY-MM-DD HH:MM:SS` in the given tz
    (default: system local). Strings without timezone info are displayed
    as-is (no conversion); strings without a seconds component get `:00`
    appended so the column width stays uniform."""
    if not iso:
        return ""
    dt = _parse_aware(iso)
    if dt is not None:
        local = dt.astimezone(tz or _local_tz())
        return local.strftime("%Y-%m-%d %H:%M:%S")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?", str(iso))
    if not m:
        return str(iso)[:19]
    secs = m.group(6) or "00"
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{secs}"


def format_relative_date(iso: str, tz: tzinfo | None = None) -> tuple[str, str]:
    """Return `(display, full)` — display is `Mon D` in the given tz
    (default: system local); full preserves the original ISO string."""
    if not iso:
        return ("—", "")
    dt = _parse_aware(iso)
    if dt is not None:
        local = dt.astimezone(tz or _local_tz())
        return (f"{_MONTHS[local.month - 1]} {local.day}", str(iso))
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso))
    if not m:
        return (str(iso)[:10], str(iso))
    try:
        return (f"{_MONTHS[int(m.group(2)) - 1]} {int(m.group(3))}", str(iso))
    except (ValueError, IndexError):
        return (str(iso)[:10], str(iso))
