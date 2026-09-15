"""Wait-until-ready polling, shared by the sync and async clients.

Photon has no "is it done yet" endpoint: asking for a result that is still
being processed returns the result endpoint's ordinary 200 with a *"being
processed"* message, which the transport turns into :class:`NotReadyError`.
Polling is therefore just "call the fetch again until it stops raising that",
which is what :func:`poll` does — on a capped exponential backoff, bounded by
the caller's deadline.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from .constants import (
    DEFAULT_POLL_BACKOFF,
    DEFAULT_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
)
from .exceptions import ExtractionTimeoutError, NotReadyError

__all__ = ["poll", "validate_settings"]

T = TypeVar("T")


def validate_settings(
    *,
    interval: float,
    backoff: float = DEFAULT_POLL_BACKOFF,
    max_interval: float = MAX_POLL_INTERVAL,
) -> None:
    """Check polling settings, so callers can reject them before doing any I/O.

    :func:`poll` applies these itself, but by then a caller like
    ``PhotonClient.extract`` has already uploaded a document and spent an API
    call. Validating up front keeps a bad argument cheap.

    Raises:
        ValueError: A setting that would make polling impossible.
    """
    if interval <= 0:
        raise ValueError("interval must be greater than zero.")
    if backoff < 1:
        raise ValueError("backoff must be 1 or greater.")
    if max_interval <= 0:
        raise ValueError("max_interval must be greater than zero.")


def poll(
    fetch: Callable[[], T],
    *,
    timeout: float,
    interval: float = DEFAULT_POLL_INTERVAL,
    backoff: float = DEFAULT_POLL_BACKOFF,
    max_interval: float = MAX_POLL_INTERVAL,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> T:
    """Call ``fetch`` until it produces a result or the deadline passes.

    ``fetch`` is always called at least once, however small ``timeout`` is, and
    once more at the deadline itself — so a document that finishes during the
    final wait is still returned rather than timing out.

    Args:
        fetch: The operation to repeat. Raising :class:`NotReadyError` means
            "not finished, try again"; any other exception propagates
            immediately, since retrying it would not help.
        timeout: How long to keep trying, in seconds, measured from the first
            attempt. Negative values are treated as zero.
        interval: Seconds to wait after the first unsuccessful attempt.
        backoff: Multiplier applied to the wait after each attempt. ``1.0``
            polls at a fixed ``interval``.
        max_interval: Ceiling on the wait between attempts, so backoff cannot
            grow without bound on a long deadline.
        sleep: Override for :func:`time.sleep`, for tests.
        clock: Override for :func:`time.monotonic`, for tests. Must be
            monotonic; wall-clock time would make the deadline jump.

    Returns:
        Whatever ``fetch`` returns on its first successful attempt.

    Raises:
        ValueError: ``interval`` is not positive, or ``backoff`` is below 1.
        ExtractionTimeoutError: The deadline passed with the document still
            processing. It is not lost — retrieve it later by its
            ``photon_key``.
    """
    validate_settings(interval=interval, backoff=backoff, max_interval=max_interval)

    do_sleep = time.sleep if sleep is None else sleep
    now = time.monotonic if clock is None else clock

    started = now()
    deadline = started + max(timeout, 0.0)
    delay = min(interval, max_interval)
    attempts = 0

    while True:
        attempts += 1
        try:
            return fetch()
        except NotReadyError as not_ready:
            remaining = deadline - now()
            if remaining <= 0:
                raise ExtractionTimeoutError(
                    f"Still processing after {now() - started:.1f}s "
                    f"and {attempts} attempt(s): {not_ready.message}",
                    status_code=not_ready.status_code,
                    body=not_ready.body,
                ) from not_ready
            # Never sleep past the deadline: the clamp buys one last attempt
            # exactly when the caller's patience runs out.
            do_sleep(min(delay, remaining))
            delay = min(delay * backoff, max_interval)
