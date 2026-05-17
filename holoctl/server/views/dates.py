from __future__ import annotations
import re


def format_iso_datetime(iso: str) -> str:
    """Pretty-print an ISO timestamp as `YYYY-MM-DD HH:MM` (UTC, no seconds).

    Used in the detail page's Activity / Properties cards where the full
    ISO + microsecond is too noisy.
    """
    if not iso:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", str(iso))
    if not m:
        return str(iso)[:19]
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}"


def format_relative_date(iso: str) -> tuple[str, str]:
    """Return (display, full) — display is short, full is the original ISO.

    Used in the dense list view so the Updated column reads "May 7" / "2h ago"
    instead of dragging the full ISO string. We don't reach for full
    locale-aware relative time here; dashboards are short-lived sessions
    and the agent typically wants "today / yesterday / older".
    """
    if not iso:
        return ("—", "")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso))
    if not m:
        return (str(iso)[:10], str(iso))
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        mo = int(m.group(2)); day = int(m.group(3))
        return (f"{months[mo - 1]} {day}", str(iso))
    except (ValueError, IndexError):
        return (str(iso)[:10], str(iso))
