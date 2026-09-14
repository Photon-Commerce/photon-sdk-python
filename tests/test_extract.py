"""Tests for poll() and PhotonClient.extract: the submit-then-wait flow.

The polling primitive is exercised directly with a fake clock and a recording
sleep, so the deadline and backoff maths are asserted without real waiting.
The client-level tests drive it through respx, with ``time.sleep`` stubbed out.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from photon import (
    APIError,
    AuthenticationError,
    DocType,
    ExtractionTimeoutError,
    NotReadyError,
    PhotonClient,
    Submission,
)
from photon._polling import poll
from photon.constants import MAX_POLL_INTERVAL, RETRIEVE_PATH, SUBMIT_PATH

BASE_URL = "https://sandbox-api.photoncommerce.com"
FIXTURES = Path(__file__).parent / "fixtures"

INVOICE_READY: dict[str, Any] = json.loads((FIXTURES / "invoice_ready.json").read_text())
INVOICE_PROCESSING: dict[str, Any] = json.loads(
    (FIXTURES / "invoice_processing.json").read_text()
)

SUBMIT_RESPONSE = {
    "photon_key": "data/user@example.com/2026-08-12/13-26-39-943699_invoice.json",
    "doc_path": "data/user@example.com/2026-08-12/13-26-39-943699_invoice.pdf",
    "message": "success",
    "status": "success",
}

PDF_BYTES = b"%PDF-1.4 not a real document"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeClock:
    """A monotonic clock that only advances when something sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def not_ready() -> NotReadyError:
    return NotReadyError(
        "The document you submitted is being processed.",
        status_code=200,
        body=INVOICE_PROCESSING,
    )


def never_ready() -> str:
    """A fetch that is never finished — for exercising the deadline."""
    raise not_ready()


def fetch_after(pending: int, result: str = "done") -> Callable[[], str]:
    """A fetch that raises NotReadyError ``pending`` times, then returns."""
    calls = {"n": 0}

    def fetch() -> str:
        calls["n"] += 1
        if calls["n"] <= pending:
            raise not_ready()
        return result

    return fetch


# --------------------------------------------------------------------------- #
# poll()
# --------------------------------------------------------------------------- #


def test_poll_returns_immediately_when_the_first_attempt_succeeds() -> None:
    clock = FakeClock()

    assert poll(lambda: "done", timeout=60, clock=clock, sleep=clock.sleep) == "done"
    assert clock.slept == []


def test_poll_retries_until_the_document_is_ready() -> None:
    clock = FakeClock()
    fetch = fetch_after(2)

    result = poll(fetch, timeout=60, interval=2, clock=clock, sleep=clock.sleep)

    assert result == "done"
    assert clock.slept == [2, 3]  # interval, then interval * 1.5 backoff


def test_poll_raises_extraction_timeout_once_the_deadline_passes() -> None:
    clock = FakeClock()

    with pytest.raises(ExtractionTimeoutError) as caught:
        poll(never_ready, timeout=10, interval=4, clock=clock, sleep=clock.sleep)

    assert caught.value.status_code == 200
    assert caught.value.body == INVOICE_PROCESSING
    assert "being processed" in caught.value.message
    # 4s then 6s (clamped from 6 to what remained): 2 waits, 3 attempts.
    assert clock.slept == [4, 6]


def test_poll_always_attempts_once_even_with_no_time_left() -> None:
    clock = FakeClock()
    fetch = fetch_after(0)

    assert poll(fetch, timeout=0, clock=clock, sleep=clock.sleep) == "done"


def test_poll_makes_a_final_attempt_at_the_deadline() -> None:
    clock = FakeClock()
    # Ready on the third call, with a deadline that lands exactly on it.
    result = poll(
        fetch_after(2), timeout=5, interval=2, clock=clock, sleep=clock.sleep
    )

    assert result == "done"
    assert clock.slept == [2, 3]


def test_poll_never_sleeps_past_the_deadline() -> None:
    clock = FakeClock()

    with pytest.raises(ExtractionTimeoutError):
        poll(never_ready, timeout=5, interval=60, clock=clock, sleep=clock.sleep)

    assert clock.slept == [5]  # clamped from 60 down to what remained


def test_poll_backoff_is_capped_at_the_maximum_interval() -> None:
    clock = FakeClock()

    with pytest.raises(ExtractionTimeoutError):
        poll(
            never_ready,
            timeout=10_000,
            interval=1,
            backoff=10,
            clock=clock,
            sleep=clock.sleep,
        )

    assert max(clock.slept) <= MAX_POLL_INTERVAL
    assert clock.slept[:4] == [1, 10, 30, 30]


def test_poll_with_backoff_of_one_keeps_a_fixed_interval() -> None:
    clock = FakeClock()

    with pytest.raises(ExtractionTimeoutError):
        poll(
            never_ready,
            timeout=9,
            interval=3,
            backoff=1,
            clock=clock,
            sleep=clock.sleep,
        )

    assert clock.slept == [3, 3, 3]


def test_poll_propagates_errors_that_retrying_cannot_fix() -> None:
    clock = FakeClock()

    def fetch() -> str:
        raise AuthenticationError("Unauthorized", status_code=401)

    with pytest.raises(AuthenticationError):
        poll(fetch, timeout=60, clock=clock, sleep=clock.sleep)

    assert clock.slept == []


@pytest.mark.parametrize("interval", [0, -1])
def test_poll_rejects_a_non_positive_interval(interval: float) -> None:
    with pytest.raises(ValueError, match="interval"):
        poll(lambda: "done", timeout=60, interval=interval)


def test_poll_rejects_a_shrinking_backoff() -> None:
    with pytest.raises(ValueError, match="backoff"):
        poll(lambda: "done", timeout=60, backoff=0.5)


# --------------------------------------------------------------------------- #
# PhotonClient.extract
# --------------------------------------------------------------------------- #


def make_client(**overrides: Any) -> PhotonClient:
    values: dict[str, Any] = {
        "client_id": "AAA111",
        "username": "user@example.com",
        "api_key": "BBB222",
        "password": "CCC333",
        "secret_key": "DDD444",
    }
    values.update(overrides)
    return PhotonClient(**values)


@pytest.fixture
def client() -> Iterator[PhotonClient]:
    with make_client() as open_client:
        yield open_client


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[float]]:
    """Record what extract() would have waited, without waiting."""
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    yield slept


def test_extract_polls_until_ready_and_returns_the_data(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post(SUBMIT_PATH).mock(return_value=httpx.Response(200, json=SUBMIT_RESPONSE))
        retrieve = mock.get(RETRIEVE_PATH).mock(
            side_effect=[
                httpx.Response(200, json=INVOICE_PROCESSING),
                httpx.Response(200, json=INVOICE_PROCESSING),
                httpx.Response(200, json=INVOICE_READY),
            ]
        )

        data = client.extract(PDF_BYTES)

    assert retrieve.call_count == 3
    assert data["Vendor_Name"] == "Acme Supplies Ltd"


def test_extract_waits_between_attempts(
    client: PhotonClient, no_real_sleeping: list[float]
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post(SUBMIT_PATH).mock(return_value=httpx.Response(200, json=SUBMIT_RESPONSE))
        mock.get(RETRIEVE_PATH).mock(
            side_effect=[
                httpx.Response(200, json=INVOICE_PROCESSING),
                httpx.Response(200, json=INVOICE_READY),
            ]
        )

        client.extract(PDF_BYTES, poll_interval=7)

    assert no_real_sleeping == [7]


def test_extract_raises_extraction_timeout_when_it_runs_out_of_time(
    client: PhotonClient,
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post(SUBMIT_PATH).mock(return_value=httpx.Response(200, json=SUBMIT_RESPONSE))
        retrieve = mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(200, json=INVOICE_PROCESSING)
        )

        with pytest.raises(ExtractionTimeoutError):
            client.extract(PDF_BYTES, timeout=0)

    assert retrieve.call_count == 1


def test_extract_with_no_timeout_submits_without_retrieving(
    client: PhotonClient,
) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        mock.post(SUBMIT_PATH).mock(return_value=httpx.Response(200, json=SUBMIT_RESPONSE))
        retrieve = mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(200, json=INVOICE_READY)
        )

        result = client.extract(PDF_BYTES, timeout=None)

    assert isinstance(result, Submission)
    assert result.photon_key == SUBMIT_RESPONSE["photon_key"]
    assert not retrieve.called


def test_extract_forwards_submit_arguments(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        submit = mock.post(SUBMIT_PATH).mock(
            return_value=httpx.Response(200, json=SUBMIT_RESPONSE)
        )
        mock.get(RETRIEVE_PATH).mock(return_value=httpx.Response(200, json=INVOICE_READY))

        client.extract(
            PDF_BYTES,
            doctype=DocType.RECEIPT_EXPENSE,
            reference_id="order-9",
            subaccount="team-a",
        )

    params = submit.calls.last.request.url.params
    assert params["doctype"] == "receipt-expense"
    assert params["ID"] == "order-9"
    assert params["subaccount"] == "team-a"


def test_extract_by_url_needs_no_document(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        submit = mock.post(SUBMIT_PATH).mock(
            return_value=httpx.Response(200, json=SUBMIT_RESPONSE)
        )
        mock.get(RETRIEVE_PATH).mock(return_value=httpx.Response(200, json=INVOICE_READY))

        data = client.extract(url="https://example.com/invoice.pdf")

    assert submit.calls.last.request.url.params["url"] == "https://example.com/invoice.pdf"
    assert data["Invoice_Number"] == "INV-2026-00042"


def test_extract_without_a_photon_key_is_an_api_error(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        mock.post(SUBMIT_PATH).mock(
            return_value=httpx.Response(200, json={"message": "success"})
        )
        retrieve = mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(200, json=INVOICE_READY)
        )

        with pytest.raises(APIError, match="photon_key"):
            client.extract(PDF_BYTES)

    assert not retrieve.called


def test_extract_validates_before_submitting(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        submit = mock.post(SUBMIT_PATH)

        with pytest.raises(ValueError, match="exactly one"):
            client.extract()

    assert not submit.called
