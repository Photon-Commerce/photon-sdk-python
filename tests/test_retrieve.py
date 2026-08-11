"""Tests for PhotonClient.retrieve: the data payload, the processing signal, errors.

Response bodies come from ``tests/fixtures/`` (see the README there for their
provenance) and are served via respx.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from photon import (
    APIError,
    AuthenticationError,
    InvalidRequestError,
    NotReadyError,
    PhotonClient,
)
from photon.constants import PROCESSING_MESSAGE, RETRIEVE_PATH

BASE_URL = "https://sandbox-api.photoncommerce.com"
FIXTURES = Path(__file__).parent / "fixtures"

INVOICE_READY: dict[str, Any] = json.loads((FIXTURES / "invoice_ready.json").read_text())
INVOICE_PROCESSING: dict[str, Any] = json.loads(
    (FIXTURES / "invoice_processing.json").read_text()
)


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


def mock_retrieve(mock: respx.MockRouter, response: httpx.Response) -> respx.Route:
    return mock.get(RETRIEVE_PATH).mock(return_value=response)


def test_ready_document_returns_the_data_dict(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_retrieve(mock, httpx.Response(200, json=INVOICE_READY))
        data = client.retrieve("pk_fixture_0001")

    assert route.calls.last.request.url.params["photon_key"] == "pk_fixture_0001"
    assert data == INVOICE_READY["data"]
    assert data["Vendor_Name"] == "Acme Supplies Ltd"
    assert data["Line_Items"][0]["Amount"] == "1150.00"


def test_processing_document_raises_not_ready(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock_retrieve(mock, httpx.Response(200, json=INVOICE_PROCESSING))
        with pytest.raises(NotReadyError) as caught:
            client.retrieve("pk_fixture_0001")

    assert caught.value.message == PROCESSING_MESSAGE
    assert caught.value.status_code == 200


@pytest.mark.parametrize("photon_key", ["", "   "])
def test_empty_photon_key_is_a_value_error_before_any_io(
    client: PhotonClient, photon_key: str
) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="photon_key"):
        client.retrieve(photon_key)
    assert not mock.calls


def test_success_body_without_data_is_an_api_error_not_a_key_error(
    client: PhotonClient,
) -> None:
    body = {"message": "success", "status": "success"}
    with respx.mock(base_url=BASE_URL) as mock:
        mock_retrieve(mock, httpx.Response(200, json=body))
        with pytest.raises(APIError) as caught:
            client.retrieve("pk_fixture_0001")

    assert caught.value.body == body


def test_success_body_with_non_dict_data_is_an_api_error(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock_retrieve(mock, httpx.Response(200, json={"data": "oops", "message": "success"}))
        with pytest.raises(APIError):
            client.retrieve("pk_fixture_0001")


def test_error_payloads_map_to_typed_exceptions(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock_retrieve(mock, httpx.Response(403, json={"message": "Photon Key missing"}))
        with pytest.raises(InvalidRequestError, match="Photon Key missing"):
            client.retrieve("pk_wrong")


def test_authentication_failure_propagates(client: PhotonClient) -> None:
    message = "Authentication failed. Please check your credentials"
    with respx.mock(base_url=BASE_URL) as mock:
        mock_retrieve(mock, httpx.Response(401, json={"message": message}))
        with pytest.raises(AuthenticationError):
            client.retrieve("pk_fixture_0001")
