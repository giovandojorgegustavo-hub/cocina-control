"""Time window helpers for business rules that depend on calendar day.

Argentina does not observe daylight saving time, so UTC-3 is a fixed offset
year-round.  Using a fixed tzinfo avoids any ambiguity that would arise from
a named IANA timezone with historical DST transitions.
"""

from datetime import datetime, timedelta, timezone

# Argentina Standard Time: UTC-3, fixed offset (no DST).
ARGENTINA_TZ = timezone(timedelta(hours=-3))


def is_same_calendar_day_argentina(a: datetime, b: datetime) -> bool:
    """Return True if *a* and *b* fall on the same calendar day in UTC-3.

    Both arguments are expected to be timezone-aware datetimes; if they are
    naive they are treated as UTC (standard library behaviour for astimezone).

    Edge cases:
    - 23:59 UTC-3 and 00:00 UTC-3 the next day → False (different days).
    - 00:01 UTC and 23:59 UTC-3 of the previous day → same day in UTC-3 iff
      they map to the same date in UTC-3.

    >>> from datetime import timezone, timedelta
    >>> tz = timezone(timedelta(hours=-3))
    >>> d1 = datetime(2026, 7, 9, 23, 59, tzinfo=tz)   # 23:59 Argentina
    >>> d2 = datetime(2026, 7, 10, 0, 0, tzinfo=tz)    # 00:00 Argentina next day
    >>> is_same_calendar_day_argentina(d1, d2)
    False
    >>> d3 = datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc)  # 00:00 Argentina
    >>> is_same_calendar_day_argentina(d1, d3)
    True
    """
    date_a = a.astimezone(ARGENTINA_TZ).date()
    date_b = b.astimezone(ARGENTINA_TZ).date()
    return date_a == date_b
