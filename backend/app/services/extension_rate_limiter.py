"""In-memory burst rate limiter for extension captures.

Supplements the database-level daily limit check. Prevents a compromised
extension from firing dozens of captures in a single second even when
within the daily quota.

Limit: 10 captures per 60-second sliding window per user.
"""

from __future__ import annotations

import time
from collections import deque

_window: dict[str, deque[float]] = {}

BURST_LIMIT = 10
WINDOW_SECONDS = 60.0


def check_rate(user_id: str) -> bool:
    """Return True if the user is within the burst limit, False otherwise."""
    now = time.monotonic()
    timestamps = _window.get(user_id)

    if timestamps is None:
        timestamps = deque()
        _window[user_id] = timestamps

    # Evict entries older than the window
    while timestamps and (now - timestamps[0]) > WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= BURST_LIMIT:
        return False

    timestamps.append(now)
    return True
