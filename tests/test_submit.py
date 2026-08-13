"""Tests for PhotonClient.submit: input modes, validation, and the Submission model.

The API is stubbed with respx; the submit response shape comes from the
official API docs (apidocs.photoncommerce.com).
"""

from __future__ import annotations

import builtins
import io
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

import httpx
import pytest
import respx
from pydantic import ValidationError

from photon import APIError, ConfigurationError, DocType, PhotonClient, Submission
from photon.constants import SUBMIT_PATH

BASE_URL = "https://sandbox-api.photoncommerce.com"

PDF_BYTES = b"%PDF-1.4 not a real document"

SUBMIT_RESPONSE = {
    "photon_key": "pk_test_123",
    "doc_path": "uploads/2026/invoice-abc.pdf",
    "message": "success",
}


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


def mock_submit(mock: respx.MockRouter, response: httpx.Response | None = None) -> respx.Route:
    if response is None:
        response = httpx.Response(200, json=SUBMIT_RESPONSE)
    return mock.post(SUBMIT_PATH).mock(return_value=response)


# --- document input modes -------------------------------------------------


@pytest.mark.parametrize("as_type", [str, Path])
def test_path_input_uploads_multipart_pdf_field(
    tmp_path: Path, client: PhotonClient, as_type: type
) -> None:
    document = tmp_path / "invoice.pdf"
    document.write_bytes(PDF_BYTES)

    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        submission = client.submit(as_type(document))

    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="pdf"' in request.content
    assert b'filename="invoice.pdf"' in request.content
    assert PDF_BYTES in request.content
    assert submission.photon_key == "pk_test_123"
    assert submission.doc_path == "uploads/2026/invoice-abc.pdf"


def test_unnamed_file_object_is_uploaded_with_an_extension_and_left_open(
    client: PhotonClient,
) -> None:
    handle = io.BytesIO(PDF_BYTES)

    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        client.submit(handle)

    request = route.calls.last.request
    assert b'name="pdf"' in request.content
    # The API recognises file types by extension, so an unnamed stream must not
    # go out under httpx's extensionless fallback name.
    assert b'filename="upload.pdf"' in request.content
    assert PDF_BYTES in request.content
    assert not handle.closed


def test_named_file_object_keeps_its_own_filename(
    tmp_path: Path, client: PhotonClient
) -> None:
    document = tmp_path / "receipt.png"
    document.write_bytes(PDF_BYTES)

    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        with document.open("rb") as handle:
            client.submit(handle)

    assert b'filename="receipt.png"' in route.calls.last.request.content


def test_bytes_input_is_uploaded_with_an_extension(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        client.submit(PDF_BYTES)

    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="pdf"' in request.content
    assert b'filename="upload.pdf"' in request.content
    assert PDF_BYTES in request.content


def test_path_input_closes_the_file_it_opened(
    tmp_path: Path, client: PhotonClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = tmp_path / "invoice.pdf"
    document.write_bytes(PDF_BYTES)

    opened: list[IO[bytes]] = []
    real_open = builtins.open

    def recording_open(*args: Any, **kwargs: Any) -> Any:
        handle = real_open(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(builtins, "open", recording_open)
    with respx.mock(base_url=BASE_URL) as mock:
        mock_submit(mock)
        client.submit(str(document))

    assert opened
    assert all(handle.closed for handle in opened)


def test_path_input_closes_the_file_even_when_the_request_fails(
    tmp_path: Path, client: PhotonClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = tmp_path / "invoice.pdf"
    document.write_bytes(PDF_BYTES)

    opened: list[IO[bytes]] = []
    real_open = builtins.open

    def recording_open(*args: Any, **kwargs: Any) -> Any:
        handle = real_open(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(builtins, "open", recording_open)
    with respx.mock(base_url=BASE_URL) as mock:
        mock_submit(mock, httpx.Response(500, json={"message": "Internal server error"}))
        with pytest.raises(APIError):
            client.submit(str(document))

    assert opened
    assert all(handle.closed for handle in opened)


def test_url_mode_sends_the_query_param_and_no_file(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        submission = client.submit(url="https://example.com/invoice.pdf")

    request = route.calls.last.request
    assert request.url.params["url"] == "https://example.com/invoice.pdf"
    assert "multipart" not in request.headers.get("content-type", "")
    assert request.content == b""
    assert submission.photon_key == "pk_test_123"


# --- validation, before any I/O -------------------------------------------


def test_neither_document_nor_url_is_a_value_error(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="exactly one"):
        client.submit()
    assert not mock.calls


def test_both_document_and_url_is_a_value_error(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="exactly one"):
        client.submit(PDF_BYTES, url="https://example.com/invoice.pdf")
    assert not mock.calls


@pytest.mark.parametrize(
    "subaccount",
    ["a" * 51, "under_score", "has space", "", "email@nope", "slash/nope", "team-1\n"],
)
def test_invalid_subaccount_is_a_value_error(client: PhotonClient, subaccount: str) -> None:
    with respx.mock(base_url=BASE_URL) as mock, pytest.raises(ValueError, match="subaccount"):
        client.submit(PDF_BYTES, subaccount=subaccount)
    assert not mock.calls


@pytest.mark.parametrize("subaccount", ["team-1", "ACME", "a" * 50, "0-0"])
def test_valid_subaccount_is_sent(client: PhotonClient, subaccount: str) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        client.submit(PDF_BYTES, subaccount=subaccount)

    assert route.calls.last.request.url.params["subaccount"] == subaccount


# --- request shaping -------------------------------------------------------


def test_reference_id_is_sent_as_the_ID_param(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        client.submit(PDF_BYTES, reference_id="order-42")

    params = route.calls.last.request.url.params
    assert params["ID"] == "order-42"
    assert "reference_id" not in params


def test_optional_params_are_omitted_when_none(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        client.submit(PDF_BYTES)

    params = route.calls.last.request.url.params
    assert dict(params) == {"doctype": "invoice"}


def test_all_optional_params_are_sent_when_given(client: PhotonClient) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        client.submit(
            PDF_BYTES,
            doctype=DocType.RECEIPT_EXPENSE,
            webhook_url="https://example.com/hook",
            auth_token="hook-token",
            reference_id="ref-1",
            subaccount="team-1",
            page_start=1,
            page_end=3,
        )

    params = dict(route.calls.last.request.url.params)
    assert params == {
        "doctype": "receipt-expense",
        "webhook_url": "https://example.com/hook",
        "auth_token": "hook-token",
        "ID": "ref-1",
        "subaccount": "team-1",
        "page_start": "1",
        "page_end": "3",
    }


@pytest.mark.parametrize(
    ("doctype", "expected"),
    [
        (DocType.INVOICE, "invoice"),
        (DocType.BILL_UTILITY, "bill-utility"),
        ("statement", "statement"),
        ("some-future-doctype", "some-future-doctype"),
    ],
)
def test_doctype_accepts_enum_or_string(
    client: PhotonClient, doctype: DocType | str, expected: str
) -> None:
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock_submit(mock)
        client.submit(PDF_BYTES, doctype=doctype)

    assert route.calls.last.request.url.params["doctype"] == expected


# --- the Submission model ---------------------------------------------------


def test_submission_tolerates_a_missing_or_reshaped_body() -> None:
    submission = Submission.from_response({})
    assert submission.photon_key == ""
    assert submission.doc_path == ""
    assert submission.message == ""
    assert submission.raw == {}


def test_submission_keeps_extra_keys_on_raw() -> None:
    body = {**SUBMIT_RESPONSE, "brand_new_field": {"nested": True}}
    submission = Submission.from_response(body)
    assert submission.photon_key == "pk_test_123"
    assert submission.raw == body
    assert submission.raw["brand_new_field"] == {"nested": True}


def test_submission_stringifies_oddly_typed_values_instead_of_raising() -> None:
    submission = Submission.from_response({"photon_key": 123, "doc_path": None})
    assert submission.photon_key == "123"
    assert submission.doc_path == ""


def test_submission_is_frozen() -> None:
    submission = Submission.from_response(SUBMIT_RESPONSE)
    with pytest.raises(ValidationError):
        submission.photon_key = "other"


# --- client construction and lifecycle --------------------------------------


def test_missing_credentials_raise_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="password"):
        make_client(password="")


def test_from_env_reads_photon_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHOTON_CLIENT_ID", "env-cid")
    monkeypatch.setenv("PHOTON_USERNAME", "env-user@example.com")
    monkeypatch.setenv("PHOTON_API_KEY", "env-key")
    monkeypatch.setenv("PHOTON_PASSWORD", "env-pass")
    monkeypatch.setenv("PHOTON_SECRET_KEY", "env-secret")
    monkeypatch.setenv("PHOTON_ENVIRONMENT", "production")

    with PhotonClient.from_env(timeout=5.0) as client:
        assert client.config.client_id == "env-cid"
        assert client.config.environment.value == "production"
        assert client.config.base_url == "https://api.photoncommerce.com"
        assert client.config.timeout == 5.0


def test_context_manager_closes_the_transport() -> None:
    client = make_client()
    with client:
        assert not client.is_closed
    assert client.is_closed
    client.close()  # safe to call again


def test_repr_shows_no_secrets() -> None:
    client = make_client()
    try:
        text = repr(client)
        for secret in ("AAA111", "BBB222", "CCC333", "DDD444"):
            assert secret not in text
        assert "sandbox" in text
    finally:
        client.close()
