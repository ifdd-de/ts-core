"""Times of samples: ISO 8601 with an offset outside, milliseconds inside.

VictoriaMetrics keeps timestamps as milliseconds since 1970-01-01 UTC. The
API takes and returns ISO 8601 strings. A time without an offset is refused,
because it would mean whatever time zone the client happens to run in; a
time finer than a millisecond is refused, because it would be cut silently.
Answers are in UTC with exactly three decimals.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class TimeError(ValueError):
    """A time the API does not accept (HTTP 422)."""


def parse_time(value: str) -> int:
    """Milliseconds since the epoch of an ISO 8601 time with offset.

    Args:
        value: E.g. ``2026-10-22T09:15:00+02:00`` or ``2026-10-22T07:15:00.250Z``.

    Returns:
        The time in milliseconds since 1970-01-01T00:00:00Z.

    Raises:
        TimeError: Not ISO 8601, no offset, finer than a millisecond, or
            before 1970.
    """
    if not isinstance(value, str):
        raise TimeError("a time must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise TimeError(f"{value!r} is not an ISO 8601 time") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TimeError(f"{value!r} has no offset (add Z or e.g. +02:00)")
    if parsed.microsecond % 1000:
        raise TimeError(f"{value!r} is finer than a millisecond")
    delta = parsed - EPOCH
    if delta < timedelta(0):
        raise TimeError(f"{value!r} is before 1970-01-01T00:00:00Z")
    return delta // timedelta(milliseconds=1)


def format_time(milliseconds: int) -> str:
    """ISO 8601 in UTC with milliseconds, e.g. ``2026-10-22T07:15:00.250+00:00``."""
    return (EPOCH + timedelta(milliseconds=milliseconds)).isoformat(timespec="milliseconds")


def vm_time(milliseconds: int) -> str:
    """A time parameter for VictoriaMetrics: seconds with exactly three decimals."""
    return f"{milliseconds // 1000}.{milliseconds % 1000:03d}"
