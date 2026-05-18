"""Presenters: pure functions that turn domain dicts into template context.

Each module owns one slice of the UI (avatars, dates, card, board, list…)
and is testable in isolation. Templates consume the dicts these return;
they never reach back into `lib.board` or perform IO.
"""
