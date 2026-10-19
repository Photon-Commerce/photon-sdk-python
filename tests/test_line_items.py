"""Tests for add_line_item and delete_line_item.

The API is stubbed with respx; bodies follow the official API docs
(apidocs.photoncommerce.com).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from photon import APIError, InvalidRequestError, PhotonClient
from photon.constants import ADD_LINE_ITEM_PATH, UPDATE_LINE_ITEM_PATH

BASE_URL = "https://sandbox-api.photoncommerce.com"
KEY = "data/user@example.com/2026-10-19/10-00-00_invoice.json"
LINE = {"Line": 3, "SKU": "WID-300", "Description": "Widget", "Price": "10.00", "Amount": "10.00"}


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
    # backoff_factor=0: a retry, if one happened, would not slow the suite.
    with make_client(backoff_factor=0) as open_client:
        yield open_client


def success(message: str) -> httpx.Response:
    return httpx.Response(200, json={"message": message, "status": "success"})


# --------------------------------------------------------------------------- #
# add_line_item
# --------------------------------------------------------------------------- #


def test_add_line_item_posts_to_the_invoice_path(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post(ADD_LINE_ITEM_PATH).mock(
            return_value=success("Added line item successfully")
        )
        client.add_line_item(KEY, {**LINE, "QTY": Decimal("1.5")})

    request = route.calls.last.request
    assert request.url.params["photon_key"] == KEY
    assert "url" not in request.url.params
    assert json.loads(request.content) == {**LINE, "QTY": "1.5"}


def test_add_line_item_passes_the_documents_url(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post(ADD_LINE_ITEM_PATH).mock(
            return_value=success("Added line item successfully")
        )
        client.add_line_item(KEY, LINE, url="https://example.com/invoice.pdf")

    assert route.calls.last.request.url.params["url"] == "https://example.com/invoice.pdf"


def test_a_duplicate_line_id_raises_invalid_request(client: PhotonClient) -> None:
    message = "Line Item with specified line ID already exists"
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post(ADD_LINE_ITEM_PATH).mock(
            return_value=httpx.Response(403, json={"message": message, "status": "error"})
        )
        with pytest.raises(InvalidRequestError, match=message):
            client.add_line_item(KEY, LINE)


def test_add_line_item_is_not_retried_after_a_5xx(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post(ADD_LINE_ITEM_PATH).mock(return_value=httpx.Response(500))
        with pytest.raises(APIError):
            client.add_line_item(KEY, LINE)

    assert route.call_count == 1


@pytest.mark.parametrize(("key", "fields"), [("", LINE), (KEY, {}), (KEY, None)])
def test_add_line_item_validates_before_any_io(client: PhotonClient, key: str, fields: Any) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError):
        client.add_line_item(key, fields)
    assert not mock.calls


# --------------------------------------------------------------------------- #
# delete_line_item
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("line_item_id", [2, "2"])
def test_delete_line_item_hits_the_items_url(client: PhotonClient, line_item_id: int | str) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.delete(f"{UPDATE_LINE_ITEM_PATH}/2").mock(
            return_value=success("Deleted line item successfully")
        )
        client.delete_line_item(KEY, line_item_id)

    request = route.calls.last.request
    assert request.url.params["photon_key"] == KEY
    assert request.content == b""


@pytest.mark.parametrize("line_item_id", ["two", "", "-2", True, None])
def test_delete_line_item_rejects_a_non_numeric_id(client: PhotonClient, line_item_id: Any) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="line_item_id"):
        client.delete_line_item(KEY, line_item_id)
    assert not mock.calls


def test_delete_line_item_is_not_retried_after_a_5xx(client: PhotonClient) -> None:
    # A repeat could delete a different line if the API renumbers after the first.
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.delete(f"{UPDATE_LINE_ITEM_PATH}/2").mock(return_value=httpx.Response(503))
        with pytest.raises(APIError):
            client.delete_line_item(KEY, 2)

    assert route.call_count == 1


def test_delete_line_item_is_retried_when_the_connection_failed(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.delete(f"{UPDATE_LINE_ITEM_PATH}/2").mock(
            side_effect=[httpx.ConnectError("refused"), success("Deleted line item successfully")]
        )
        client.delete_line_item(KEY, 2)

    assert route.call_count == 2


def test_delete_line_item_maps_an_invalid_id(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.delete(f"{UPDATE_LINE_ITEM_PATH}/9").mock(
            return_value=httpx.Response(
                403, json={"message": "Line Item ID invalid", "status": "error"}
            )
        )
        with pytest.raises(InvalidRequestError, match="Line Item ID invalid"):
            client.delete_line_item(KEY, 9)
