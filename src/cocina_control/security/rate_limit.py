"""In-memory rate limiter for the login endpoint.

Limits: 5 attempts per minute per IP address.

IMPORTANT LIMITATIONS:
- State lives in process memory: a server restart resets all counters.
- Does not work correctly with multiple worker processes (each worker has its
  own counter).  For a multi-worker production deployment, replace this with
  a shared backend such as Redis.  File a new issue when that becomes necessary.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

_WINDOW = timedelta(minutes=1)
_MAX_ATTEMPTS = 5

# Mapping: IP -> list of attempt timestamps within the current window.
_attempts: dict[str, list[datetime]] = defaultdict(list)


def _clean(timestamps: list[datetime], now: datetime) -> list[datetime]:
    """Return only timestamps within the current window (lazy eviction)."""
    cutoff = now - _WINDOW
    return [ts for ts in timestamps if ts > cutoff]


def is_allowed(ip: str) -> bool:
    """Return True if *ip* may attempt a login; False if rate-limited.

    Side-effect: records the attempt if allowed.
    """
    now = datetime.now(UTC)
    _attempts[ip] = _clean(_attempts[ip], now)
    if len(_attempts[ip]) >= _MAX_ATTEMPTS:
        return False
    _attempts[ip].append(now)
    return True


def reset(ip: str) -> None:
    """Clear all recorded attempts for *ip*.  Intended for tests only."""
    _attempts.pop(ip, None)
