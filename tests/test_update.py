"""Tests for correcting extracted data: update_fields and update_line_item.

The API is stubbed with respx; the success and error bodies are the ones the
official API docs (apidocs.photoncommerce.com) show for these endpoints.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from photon import InvalidRequestError, PhotonClient
from photon.constants import UPDATE_LINE_ITEM_PATH, UPDATE_PATH

BASE_URL = "https://sandbox-api.photoncommerce.com"
KEY = "data/user@example.com/2026-10-19/10-00-00_invoice.json"


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
    with make_client(max_retries=0) as open_client:
        yield open_client


def success(message: str) -> httpx.Response:
    return httpx.Response(200, json={"message": message, "status": "success"})


# --------------------------------------------------------------------------- #
# update_fields
# --------------------------------------------------------------------------- #


def test_update_fields_puts_the_fields_with_the_key(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.put(UPDATE_PATH).mock(return_value=success("Updated successfully"))
        client.update_fields(KEY, {"Vendor_Name": "Acme Ltd", "Total": "99.00"})

    request = route.calls.last.request
    assert request.url.params["photon_key"] == KEY
    assert json.loads(request.content) == {"Vendor_Name": "Acme Ltd", "Total": "99.00"}
    assert request.headers["content-type"] == "application/json"


def test_update_fields_sends_parsed_values_back_as_strings(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.put(UPDATE_PATH).mock(return_value=success("Updated successfully"))
        client.update_fields(
            KEY, {"Total": Decimal("1397.50"), "Due_Date": date(2026, 11, 18), "Pages": 1}
        )

    assert json.loads(route.calls.last.request.content) == {
        "Total": "1397.50",
        "Due_Date": "2026-11-18",
        "Pages": 1,
    }


def test_update_fields_sends_field_names_verbatim(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.put(UPDATE_PATH).mock(return_value=success("Updated successfully"))
        client.update_fields(KEY, {"vendor_name": "x", "payerName": "y"})

    assert json.loads(route.calls.last.request.content) == {"vendor_name": "x", "payerName": "y"}


@pytest.mark.parametrize("fields", [{}, None, [("Total", "1")], "Total=1"])
def test_update_fields_rejects_empty_or_non_mapping_fields(
    client: PhotonClient, fields: Any
) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="fields"):
        client.update_fields(KEY, fields)
    assert not mock.calls


@pytest.mark.parametrize("fields", [{"": "x"}, {"  ": "x"}, {1: "x"}])
def test_update_fields_rejects_bad_field_names(client: PhotonClient, fields: Any) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="Field names"):
        client.update_fields(KEY, fields)
    assert not mock.calls


@pytest.mark.parametrize("key", ["", "   "])
def test_update_fields_rejects_an_empty_key(client: PhotonClient, key: str) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="photon_key"):
        client.update_fields(key, {"Total": "1"})
    assert not mock.calls


@pytest.mark.parametrize(
    "message", ["Data field missing!", "Photon Key missing", "Photon Key Invalid"]
)
def test_update_fields_maps_api_rejections(client: PhotonClient, message: str) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.put(UPDATE_PATH).mock(
            return_value=httpx.Response(403, json={"message": message, "status": "error"})
        )
        with pytest.raises(InvalidRequestError, match=message):
            client.update_fields(KEY, {"Total": "1"})


def test_a_2xx_reporting_failure_still_raises(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.put(UPDATE_PATH).mock(
            return_value=httpx.Response(200, json={"message": "Nothing updated", "status": "error"})
        )
        with pytest.raises(InvalidRequestError, match="Nothing updated") as caught:
            client.update_fields(KEY, {"Total": "1"})

    assert caught.value.body == {"message": "Nothing updated", "status": "error"}


def test_a_2xx_failure_without_a_message_names_the_status(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.put(UPDATE_PATH).mock(return_value=httpx.Response(200, json={"status": "failed"}))
        with pytest.raises(InvalidRequestError, match="failed"):
            client.update_fields(KEY, {"Total": "1"})


def test_a_success_body_without_a_status_is_accepted(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.put(UPDATE_PATH).mock(
            return_value=httpx.Response(200, json={"message": "Updated successfully"})
        )
        client.update_fields(KEY, {"Total": "1"})


# --------------------------------------------------------------------------- #
# update_line_item
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("line_item_id", [3, "3", " 3 "])
def test_update_line_item_puts_to_the_items_path(
    client: PhotonClient, line_item_id: int | str
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.put(f"{UPDATE_LINE_ITEM_PATH}/3").mock(
            return_value=success("Updated line item successfully")
        )
        client.update_line_item(KEY, line_item_id, {"QTY": 12, "Amount": Decimal("1380.00")})

    request = route.calls.last.request
    assert request.url.params["photon_key"] == KEY
    assert json.loads(request.content) == {"QTY": 12, "Amount": "1380.00"}


@pytest.mark.parametrize("line_item_id", ["abc", "", "-1", "1.5", "3/../4", "٣", True, 1.0, None])
def test_update_line_item_rejects_a_non_numeric_id(client: PhotonClient, line_item_id: Any) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="line_item_id"):
        client.update_line_item(KEY, line_item_id, {"QTY": 1})
    assert not mock.calls


def test_update_line_item_rejects_empty_fields(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="fields"):
        client.update_line_item(KEY, 1, {})
    assert not mock.calls


def test_update_line_item_maps_an_invalid_id(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        mock.put(f"{UPDATE_LINE_ITEM_PATH}/99").mock(
            return_value=httpx.Response(
                403, json={"message": "Line Item ID invalid", "status": "error"}
            )
        )
        with pytest.raises(InvalidRequestError, match="Line Item ID invalid"):
            client.update_line_item(KEY, 99, {"QTY": 1})
