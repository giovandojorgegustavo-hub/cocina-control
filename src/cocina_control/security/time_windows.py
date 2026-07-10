"""Time window helpers for business rules that depend on calendar day.

The business timezone is configured via COCINA_BUSINESS_TIMEZONE (default
America/Lima, UTC-5, no DST).  All calendar-day comparisons use the configured
timezone so that day boundaries match the wall clock the kitchen operates on.

ZoneInfo handles DST transitions correctly for any IANA timezone — if the
business ever moves to a DST-observing location the code remains correct.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from cocina_control.config import get_settings


def is_same_calendar_day_local(a: datetime, b: datetime) -> bool:
    """Return True if *a* and *b* fall on the same calendar day in the business timezone.

    The business timezone is configured via COCINA_BUSINESS_TIMEZONE
    (default America/Lima).

    Both arguments are expected to be timezone-aware datetimes; if they are
    naive they are treated as UTC (standard library behaviour for astimezone).

    Edge cases:
    - 23:59 local and 00:00 local the next day → False (different days).
    - 00:01 UTC and 23:59 local of the previous day → same day in local iff
      they map to the same date in the business timezone.

    Example (Lima UTC-5):
      d1 = datetime(2026, 7, 9, 23, 59, tzinfo=ZoneInfo("America/Lima"))  # 23:59 Lima July 9
      d2 = datetime(2026, 7, 10, 0, 0, tzinfo=ZoneInfo("America/Lima"))   # 00:00 Lima July 10
      is_same_calendar_day_local(d1, d2)  # → False

      d3 = datetime(2026, 7, 10, 4, 0, tzinfo=timezone.utc)  # 23:00 Lima July 9
      is_same_calendar_day_local(d1, d3)  # → True
    """
    tz = ZoneInfo(get_settings().business_timezone)
    return a.astimezone(tz).date() == b.astimezone(tz).date()
