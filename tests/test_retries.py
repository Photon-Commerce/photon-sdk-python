"""Tests for the transport's retry policy: what is retried, how often, how long.

Sleep and jitter are injected, so the backoff schedule is asserted exactly and
nothing actually waits.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from photon._transport import Transport
from photon.config import Config
from photon.constants import MAX_RETRY_DELAY, PROCESSING_MESSAGE, RETRIEVE_PATH, SUBMIT_PATH
from photon.exceptions import (
    APIError,
    AuthenticationError,
    InvalidRequestError,
    NotReadyError,
    PhotonConnectionError,
    PhotonError,
    QuotaExceededError,
)

BASE_URL = "https://sandbox-api.photoncommerce.com"


def ok() -> httpx.Response:
    return httpx.Response(200, json={"message": "success"})


UPDATE_PATH = "/api/v4/update"


def make_config(**overrides: Any) -> Config:
    values: dict[str, Any] = {
        "client_id": "AAA111",
        "username": "user@example.com",
        "api_key": "BBB222",
        "password": "CCC333",
        "secret_key": "DDD444",
    }
    values.update(overrides)
    return Config(**values)


class Sleeper:
    """Records requested waits instead of sleeping."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


@pytest.fixture
def sleeper() -> Sleeper:
    return Sleeper()


def make_transport(sleeper: Sleeper, *, jitter: float = 1.0, **config: Any) -> Transport:
    return Transport(make_config(**config), sleep=sleeper, jitter=lambda: jitter)


@pytest.fixture
def transport(sleeper: Sleeper) -> Iterator[Transport]:
    with make_transport(sleeper) as open_transport:
        yield open_transport


def server_error(status: int = 500) -> httpx.Response:
    return httpx.Response(status, json={"message": "Internal server error"})


# --------------------------------------------------------------------------- #
# What is retried
# --------------------------------------------------------------------------- #


def test_a_5xx_then_success_succeeds_after_one_retry(
    transport: Transport, sleeper: Sleeper
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(RETRIEVE_PATH).mock(side_effect=[server_error(), ok()])
        body = transport.request_json("GET", RETRIEVE_PATH)

    assert body == {"message": "success"}
    assert route.call_count == 2
    assert sleeper.waits == [0.5]


def test_a_persistent_5xx_raises_api_error_after_max_retries(
    transport: Transport, sleeper: Sleeper
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(RETRIEVE_PATH).mock(return_value=server_error(503))
        with pytest.raises(APIError) as caught:
            transport.request_json("GET", RETRIEVE_PATH)

    assert caught.value.status_code == 503
    assert route.call_count == 4  # the first attempt plus max_retries=3
    assert len(sleeper.waits) == 3


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("eof")],
)
def test_a_network_error_then_success_succeeds(
    transport: Transport, sleeper: Sleeper, error: Exception
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(RETRIEVE_PATH).mock(side_effect=[error, ok()])
        transport.request_json("GET", RETRIEVE_PATH)

    assert route.call_count == 2
    assert len(sleeper.waits) == 1


def test_a_persistent_network_error_raises_connection_error(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(RETRIEVE_PATH).mock(side_effect=httpx.ReadTimeout("timed out"))
        with pytest.raises(PhotonConnectionError) as caught:
            transport.request_json("GET", RETRIEVE_PATH)

    assert route.call_count == 4
    assert "after 4 attempts" in caught.value.message
    assert isinstance(caught.value.__cause__, httpx.ReadTimeout)


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (400, "This file type is not supported.", InvalidRequestError),
        (401, "Authentication failed. Please check your credentials", AuthenticationError),
        (403, "The free trial includes 20 pages. Please upgrade your plan", QuotaExceededError),
        (403, "Photon Key missing", InvalidRequestError),
        (404, "Unable to retrieve file. It was deleted on 2026-07-01", APIError),
    ],
)
def test_a_4xx_fails_fast(
    transport: Transport,
    sleeper: Sleeper,
    status: int,
    message: str,
    expected: type[PhotonError],
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(status, json={"message": message})
        )
        with pytest.raises(expected):
            transport.request_json("GET", RETRIEVE_PATH)

    assert route.call_count == 1
    assert sleeper.waits == []


def test_a_still_processing_document_is_not_retried(transport: Transport, sleeper: Sleeper) -> None:
    # Waiting for a result is extract()'s polling, not a transport retry.
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(200, json={"message": PROCESSING_MESSAGE})
        )
        with pytest.raises(NotReadyError):
            transport.request_json("GET", RETRIEVE_PATH)

    assert route.call_count == 1
    assert sleeper.waits == []


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_idempotent_writes_are_retried_on_a_5xx(transport: Transport, method: str) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.route(method=method, path=UPDATE_PATH).mock(
            side_effect=[server_error(502), ok()]
        )
        transport.request_json(method, UPDATE_PATH)

    assert route.call_count == 2


# --------------------------------------------------------------------------- #
# POST: never risk a duplicate submission
# --------------------------------------------------------------------------- #


def test_a_post_is_not_retried_on_a_5xx(transport: Transport, sleeper: Sleeper) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post(SUBMIT_PATH).mock(return_value=server_error())
        with pytest.raises(APIError):
            transport.request_json("POST", SUBMIT_PATH, files={"pdf": ("a.pdf", b"%PDF")})

    assert route.call_count == 1
    assert sleeper.waits == []


@pytest.mark.parametrize("error", [httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("eof")])
def test_a_post_is_not_retried_once_it_may_have_been_sent(
    transport: Transport, error: Exception
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post(SUBMIT_PATH).mock(side_effect=error)
        with pytest.raises(PhotonConnectionError) as caught:
            transport.request_json("POST", SUBMIT_PATH)

    assert route.call_count == 1
    assert "attempts" not in caught.value.message


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError("refused"), httpx.ConnectTimeout("slow"), httpx.PoolTimeout("busy")],
)
def test_a_post_is_retried_when_it_never_left(transport: Transport, error: Exception) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post(SUBMIT_PATH).mock(side_effect=[error, ok()])
        transport.request_json("POST", SUBMIT_PATH, files={"pdf": ("a.pdf", b"%PDF")})

    assert route.call_count == 2
    assert route.calls.last.request.content.count(b"%PDF") == 1


# --------------------------------------------------------------------------- #
# How long it waits
# --------------------------------------------------------------------------- #


def test_backoff_doubles_from_the_backoff_factor(sleeper: Sleeper) -> None:
    with make_transport(sleeper, jitter=1.0) as transport, respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(return_value=server_error())
        with pytest.raises(APIError):
            transport.request_json("GET", RETRIEVE_PATH)

    assert sleeper.waits == [0.5, 1.0, 2.0]


def test_jitter_draws_from_the_upper_half_of_each_wait(sleeper: Sleeper) -> None:
    with make_transport(sleeper, jitter=0.0) as transport, respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(return_value=server_error())
        with pytest.raises(APIError):
            transport.request_json("GET", RETRIEVE_PATH)

    assert sleeper.waits == [0.25, 0.5, 1.0]


def test_each_wait_is_capped(sleeper: Sleeper) -> None:
    with (
        make_transport(sleeper, backoff_factor=100, max_retries=2) as transport,
        respx.mock(base_url=BASE_URL) as mock,
    ):
        mock.get(RETRIEVE_PATH).mock(return_value=server_error())
        with pytest.raises(APIError):
            transport.request_json("GET", RETRIEVE_PATH)

    assert sleeper.waits == [MAX_RETRY_DELAY, MAX_RETRY_DELAY]


def test_max_retries_zero_disables_retrying(sleeper: Sleeper) -> None:
    with make_transport(sleeper, max_retries=0) as transport, respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(RETRIEVE_PATH).mock(return_value=server_error())
        with pytest.raises(APIError):
            transport.request_json("GET", RETRIEVE_PATH)

    assert route.call_count == 1
    assert sleeper.waits == []


def test_backoff_factor_zero_retries_without_waiting(sleeper: Sleeper) -> None:
    with (
        make_transport(sleeper, backoff_factor=0) as transport,
        respx.mock(base_url=BASE_URL) as mock,
    ):
        mock.get(RETRIEVE_PATH).mock(side_effect=[server_error(), ok()])
        transport.request_json("GET", RETRIEVE_PATH)

    assert sleeper.waits == [0]


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #


def test_retries_are_logged_at_debug_without_secrets(
    transport: Transport, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="photon")
    key = "data/user@example.com/2026-08-13/doc.json"
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(
            side_effect=[server_error(503), httpx.ConnectError(f"failed for {key}"), ok()]
        )
        transport.request_json("GET", RETRIEVE_PATH, params={"photon_key": key})

    records = [r for r in caplog.records if r.name.startswith("photon")]
    assert [r.levelno for r in records] == [logging.DEBUG, logging.DEBUG]
    text = caplog.text
    assert "GET" in text and RETRIEVE_PATH in text
    assert "HTTP 503" in text and "ConnectError" in text
    for secret in ("user@example.com", "AAA111", "BBB222", "CCC333", "DDD444"):
        assert secret not in text


def test_the_package_logger_is_silent_by_default() -> None:
    assert any(isinstance(h, logging.NullHandler) for h in logging.getLogger("photon").handlers)
