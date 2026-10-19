"""Tests for the client-side rate limiter, driven by a fake clock."""

from __future__ import annotations

import threading

import pytest

from photon._ratelimit import RateLimiter
from photon.constants import RATE_LIMIT_PER_SEC


class FakeClock:
    """A monotonic clock that only moves when something sleeps on it."""

    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make_limiter(clock: FakeClock, rate: float = 10) -> RateLimiter:
    return RateLimiter(rate, sleep=clock.sleep, clock=clock)


def test_defaults_to_the_apis_rate() -> None:
    assert RateLimiter().rate == RATE_LIMIT_PER_SEC == 10


def test_the_first_call_goes_through_immediately() -> None:
    clock = FakeClock()
    assert make_limiter(clock).acquire() == 0
    assert clock.slept == []


def test_back_to_back_calls_are_spaced_by_the_interval() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)

    for _ in range(4):
        limiter.acquire()

    assert clock.slept == pytest.approx([0.1, 0.1, 0.1])
    assert clock.now == pytest.approx(100.3)


def test_never_more_than_rate_calls_in_any_second() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)

    started = []
    for _ in range(25):
        limiter.acquire()
        started.append(clock.now)

    for i, start in enumerate(started):
        in_window = [t for t in started[i:] if t < start + 1.0 - 1e-9]
        assert len(in_window) <= 10


def test_time_already_spent_counts_toward_the_interval() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)

    limiter.acquire()
    clock.now += 0.06  # the caller's own request took 60 ms
    waited = limiter.acquire()

    assert waited == pytest.approx(0.04)


def test_an_idle_limiter_does_not_bank_a_burst() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)

    limiter.acquire()
    clock.now += 60  # a long idle spell
    assert limiter.acquire() == 0
    assert limiter.acquire() == pytest.approx(0.1)


@pytest.mark.parametrize("rate", [0, -1, float("nan")])
def test_a_non_positive_rate_is_rejected(rate: float) -> None:
    with pytest.raises(ValueError, match="rate"):
        RateLimiter(rate)


def test_concurrent_callers_get_distinct_slots() -> None:
    clock = FakeClock()
    waits: list[float] = []
    record = threading.Lock()
    # Sleep is a no-op so the clock stays put and every reservation stacks.
    limiter = RateLimiter(10, sleep=lambda _: None, clock=clock)

    def worker() -> None:
        wait = limiter.acquire()
        with record:
            waits.append(wait)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(waits) == pytest.approx([i * 0.1 for i in range(20)])


def test_repr_shows_the_rate() -> None:
    assert repr(RateLimiter(5)) == "RateLimiter(rate=5)"
