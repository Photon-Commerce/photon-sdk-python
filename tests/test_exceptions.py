"""Tests for the exception hierarchy: inheritance, payload, and exports."""

from __future__ import annotations

import pytest

import photon
from photon.exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    ExtractionTimeoutError,
    InvalidRequestError,
    NotReadyError,
    PhotonConnectionError,
    PhotonError,
    QuotaExceededError,
)

ERROR_CLASSES = (
    APIError,
    AuthenticationError,
    ConfigurationError,
    ExtractionTimeoutError,
    InvalidRequestError,
    NotReadyError,
    PhotonConnectionError,
    QuotaExceededError,
)


@pytest.mark.parametrize("error_class", ERROR_CLASSES)
def test_every_error_is_catchable_as_photon_error(error_class: type[PhotonError]) -> None:
    with pytest.raises(PhotonError):
        raise error_class("boom")


@pytest.mark.parametrize("error_class", ERROR_CLASSES)
def test_every_error_is_exported(error_class: type[PhotonError]) -> None:
    name = error_class.__name__
    assert name in photon.__all__
    assert getattr(photon, name) is error_class


def test_photon_error_is_exported() -> None:
    assert "PhotonError" in photon.__all__
    assert photon.PhotonError is PhotonError


def test_message_only_error_has_no_response_context() -> None:
    error = PhotonError("something went wrong")

    assert error.message == "something went wrong"
    assert error.status_code is None
    assert error.body is None
    assert str(error) == "something went wrong"


def test_error_carries_status_and_body() -> None:
    body = {"message": "Photon Key missing", "status": "error"}
    error = InvalidRequestError("Photon Key missing", status_code=403, body=body)

    assert error.status_code == 403
    assert error.body == body
    assert error.message == "Photon Key missing"


def test_str_includes_status_code_when_present() -> None:
    error = APIError("Internal Server Error", status_code=500)

    assert str(error) == "[HTTP 500] Internal Server Error"


def test_no_rate_limit_error_exists() -> None:
    # The API has no 429 — rate limiting is queue-based — so the SDK must not
    # invite callers to handle one.
    assert not hasattr(photon, "RateLimitError")
