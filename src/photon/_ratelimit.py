"""Client-side pacing, to stay within the API's request rate.

Photon accepts up to :data:`~photon.constants.RATE_LIMIT_PER_SEC` requests a
second and queues the excess server-side rather than rejecting it, so going over
costs latency, not errors. Pacing at the source keeps a burst — a batch of
submissions, say — from piling up in that queue.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .constants import RATE_LIMIT_PER_SEC

__all__ = ["RateLimiter"]


class RateLimiter:
    """Spaces calls at least ``1 / rate`` seconds apart.

    Call :meth:`acquire` before each request. It is thread-safe: each caller
    reserves the next free slot under a lock, then sleeps outside it, so
    concurrent workers share one rate instead of each getting their own.

    There is no burst allowance: an idle limiter lets one call through at once,
    not ten. That is the simplest schedule that can never exceed the limit in
    any one-second window.

    Args:
        rate: Calls allowed per second.
        sleep: Override for :func:`time.sleep`, for tests.
        clock: Override for :func:`time.monotonic`, for tests. Must be monotonic.

    Raises:
        ValueError: ``rate`` is not positive.
    """

    def __init__(
        self,
        rate: float = RATE_LIMIT_PER_SEC,
        *,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        # "not > 0" also rejects NaN.
        if not rate > 0:
            raise ValueError("rate must be greater than zero.")
        self.rate = rate
        self._interval = 1.0 / rate
        self._sleep = time.sleep if sleep is None else sleep
        self._clock = time.monotonic if clock is None else clock
        self._lock = threading.Lock()
        self._next_slot: float | None = None

    def acquire(self) -> float:
        """Wait until the next call is allowed.

        Returns:
            How long this call waited, in seconds.
        """
        with self._lock:
            now = self._clock()
            slot = now if self._next_slot is None else max(now, self._next_slot)
            self._next_slot = slot + self._interval
        wait = slot - now
        if wait > 0:
            self._sleep(wait)
        return wait

    def __repr__(self) -> str:
        return f"RateLimiter(rate={self.rate!r})"
