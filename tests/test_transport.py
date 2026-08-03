"""Tests for the HTTP transport: headers, response classification, lifecycle.

The API is stubbed with respx, so these assert the SDK's behaviour against the
responses recorded in ``plans/API-REFERENCE.md`` — including the ones that report
failure with an HTTP 200.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from photon._transport import USER_AGENT, Transport
from photon.config import Config
from photon.constants import DOWNLOAD_PATH, PROCESSING_MESSAGE, RETRIEVE_PATH, SUBMIT_PATH
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


@pytest.fixture
def transport() -> Iterator[Transport]:
    with Transport(make_config()) as open_transport:
        yield open_transport


def test_sends_the_four_auth_headers_and_a_user_agent(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(200, json={"message": "success"})
        )
        transport.request_json("GET", RETRIEVE_PATH, params={"photon_key": "pk_1"})

    headers = route.calls.last.request.headers
    assert headers["CLIENT-ID"] == "AAA111"
    assert headers["AUTHORIZATION"] == "apikey user@example.com:BBB222"
    assert headers["PASSWORD"] == "CCC333"
    assert headers["SECRET-KEY"] == "DDD444"
    assert headers["user-agent"] == USER_AGENT
    assert USER_AGENT.startswith("photon-sdk-python/")


def test_request_json_returns_the_decoded_body(transport: Transport) -> None:
    payload = {"data": {"Vendor_Name": "Acme"}, "message": "success", "status": "success"}
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(return_value=httpx.Response(200, json=payload))
        body = transport.request_json("GET", RETRIEVE_PATH, params={"photon_key": "pk_1"})

    assert body == payload


def test_created_response_is_a_success(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post(SUBMIT_PATH).mock(
            return_value=httpx.Response(201, json={"photon_key": "pk_1", "message": "success"})
        )
        body = transport.request_json("POST", SUBMIT_PATH)

    assert body["photon_key"] == "pk_1"


def test_processing_message_raises_not_ready(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(200, json={"message": PROCESSING_MESSAGE})
        )
        with pytest.raises(NotReadyError) as caught:
            transport.request_json("GET", RETRIEVE_PATH, params={"photon_key": "pk_1"})

    error = caught.value
    assert error.status_code == 200
    assert error.message == PROCESSING_MESSAGE
    assert error.body == {"message": PROCESSING_MESSAGE}


def test_processing_detection_tolerates_reworded_messages(transport: Transport) -> None:
    reworded = "The document is Being Processed, please try again shortly"
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(return_value=httpx.Response(200, json={"message": reworded}))
        with pytest.raises(NotReadyError):
            transport.request_json("GET", RETRIEVE_PATH, params={"photon_key": "pk_1"})


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (401, "Authentication failed. Please check your credentials", AuthenticationError),
        (401, "You are not authorized to delete this file", AuthenticationError),
        (403, "The free trial includes 20 pages. Please upgrade your plan", QuotaExceededError),
        (403, "Photon Key missing", InvalidRequestError),
        (403, "Both document path and URL are missing", InvalidRequestError),
        (400, "This file type is not supported.", InvalidRequestError),
        (400, "Blank PDF submitted!", InvalidRequestError),
        (404, "Unable to retrieve file. It was deleted on 2026-07-01", APIError),
        (500, "Internal server error", APIError),
        (503, "Service unavailable", APIError),
    ],
)
def test_error_responses_map_to_typed_exceptions(
    transport: Transport,
    status: int,
    message: str,
    expected: type[PhotonError],
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(status, json={"message": message, "status": "error"})
        )
        with pytest.raises(PhotonError) as caught:
            transport.request_json("GET", RETRIEVE_PATH, params={"photon_key": "pk_1"})

    error = caught.value
    assert type(error) is expected
    assert error.status_code == status
    assert error.message == message
    assert str(error) == f"[HTTP {status}] {message}"


def test_error_body_is_preserved_for_inspection(transport: Transport) -> None:
    body = {"message": "Line Item ID invalid", "status": "error", "line_item_id": "li_9"}
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(return_value=httpx.Response(403, json=body))
        with pytest.raises(InvalidRequestError) as caught:
            transport.request_json("GET", RETRIEVE_PATH)

    assert caught.value.body == body


def test_non_json_error_body_falls_back_to_its_text(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(
                502, text="<html>Bad Gateway</html>", headers={"content-type": "text/html"}
            )
        )
        with pytest.raises(APIError) as caught:
            transport.request_json("GET", RETRIEVE_PATH)

    assert "Bad Gateway" in caught.value.message
    assert caught.value.body is None


def test_empty_error_body_falls_back_to_the_reason_phrase(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(return_value=httpx.Response(500))
        with pytest.raises(APIError) as caught:
            transport.request_json("GET", RETRIEVE_PATH)

    assert caught.value.message == "Internal Server Error"


def test_network_failure_raises_connection_error(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(side_effect=httpx.ConnectError("name resolution failed"))
        with pytest.raises(PhotonConnectionError) as caught:
            transport.request_json("GET", RETRIEVE_PATH)

    error = caught.value
    assert error.status_code is None
    assert "name resolution failed" in error.message
    assert isinstance(error.__cause__, httpx.ConnectError)


def test_timeout_raises_connection_error(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(RETRIEVE_PATH).mock(side_effect=httpx.ReadTimeout("timed out"))
        with pytest.raises(PhotonConnectionError):
            transport.request_json("GET", RETRIEVE_PATH)


def test_request_returns_the_raw_response_for_binary_downloads(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(DOWNLOAD_PATH).mock(
            return_value=httpx.Response(
                200, content=b"%PDF-1.7 ...", headers={"content-type": "application/pdf"}
            )
        )
        response = transport.request("GET", DOWNLOAD_PATH, params={"doc_path": "docs/1.pdf"})

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7 ..."


def test_request_json_rejects_a_non_json_response(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(DOWNLOAD_PATH).mock(
            return_value=httpx.Response(
                200, content=b"%PDF-1.7 ...", headers={"content-type": "application/pdf"}
            )
        )
        with pytest.raises(APIError) as caught:
            transport.request_json("GET", DOWNLOAD_PATH)

    assert "application/pdf" in caught.value.message


def test_unset_query_parameters_are_dropped(transport: Transport) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post(SUBMIT_PATH).mock(
            return_value=httpx.Response(200, json={"message": "success"})
        )
        transport.request_json(
            "POST",
            SUBMIT_PATH,
            params={"doctype": "invoice", "subaccount": None, "page_start": 1},
        )

    params = route.calls.last.request.url.params
    assert "subaccount" not in params
    assert params["doctype"] == "invoice"
    assert params["page_start"] == "1"


def test_requests_go_to_the_configured_base_url() -> None:
    with (
        Transport(make_config(base_url="https://example.test")) as transport,
        respx.mock(base_url="https://example.test") as mock,
    ):
        route = mock.get(RETRIEVE_PATH).mock(
            return_value=httpx.Response(200, json={"message": "success"})
        )
        transport.request_json("GET", RETRIEVE_PATH)

    assert str(route.calls.last.request.url).startswith("https://example.test/api/v4/json")


def test_context_manager_closes_the_client() -> None:
    with Transport(make_config()) as transport:
        assert not transport.is_closed
    assert transport.is_closed


def test_close_is_idempotent() -> None:
    transport = Transport(make_config())
    transport.close()
    transport.close()
    assert transport.is_closed


def test_repr_names_the_base_url_and_hides_credentials() -> None:
    with Transport(make_config()) as transport:
        text = repr(transport)

    assert text == "Transport(base_url='https://sandbox-api.photoncommerce.com')"
    assert "BBB222" not in text
