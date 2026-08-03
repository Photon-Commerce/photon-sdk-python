"""Exception hierarchy for the Photon SDK.

Every error raised by the SDK derives from :class:`PhotonError`, so callers can
catch that one type to handle any SDK failure.

The Photon API reports most failures in the response body's ``message`` field —
including some that arrive with an HTTP 200 — so errors carry the ``status_code``
and decoded ``body`` alongside the message whenever they came from a response.

Note there is deliberately no rate-limit error: the API has no 429. Excess traffic
is queued server-side at ten requests per second.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "APIError",
    "AuthenticationError",
    "ConfigurationError",
    "ExtractionTimeoutError",
    "InvalidRequestError",
    "NotReadyError",
    "PhotonConnectionError",
    "PhotonError",
    "QuotaExceededError",
]


class PhotonError(Exception):
    """Base class for all exceptions raised by the Photon SDK.

    Args:
        message: Human-readable description of the failure. For errors that came
            from the API this is its ``message`` field, verbatim.
        status_code: HTTP status of the offending response, or ``None`` for errors
            raised without one (configuration, connection, timeout).
        body: The decoded JSON response body, when there was one. Useful for
            reading fields the SDK does not model.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body

    def __str__(self) -> str:
        if self.status_code is None:
            return self.message
        return f"[HTTP {self.status_code}] {self.message}"


class ConfigurationError(PhotonError):
    """The client is misconfigured — e.g. missing or invalid credentials.

    Raised locally, before any HTTP request is attempted.
    """


class AuthenticationError(PhotonError):
    """The credentials were rejected, or they do not own the target resource.

    Corresponds to HTTP 401.
    """


class QuotaExceededError(PhotonError):
    """The account's page or API-call allowance is used up.

    Corresponds to HTTP 403 with a quota message, such as the sandbox's twenty
    free pages.
    """


class InvalidRequestError(PhotonError):
    """The request was rejected as malformed, incomplete, or unprocessable.

    Covers bad parameters and unusable files — an unsupported file type, a blank
    or low-resolution page, a missing ``photon_key``. The API returns these as
    HTTP 400 or 403; the body's message says which.
    """


class APIError(PhotonError):
    """The API failed in a way the SDK does not classify further.

    Unexpected 4xx and all 5xx responses land here, carrying ``status_code`` and
    ``body`` for inspection.
    """


class NotReadyError(PhotonError):
    """The document is still being processed, so no result exists yet.

    The API signals this with an HTTP 200 and a "being processed" message rather
    than an error status. Polling catches this to decide whether to wait.
    """


class ExtractionTimeoutError(PhotonError):
    """A document was still not ready when the caller's polling deadline expired.

    The document is not lost: retrieve it later with its ``photon_key``, or have
    Photon call a webhook when it finishes.
    """


class PhotonConnectionError(PhotonError):
    """The request never produced a response — network, DNS, TLS, or timeout.

    The underlying ``httpx`` failure is kept as the exception's ``__cause__``.
    """
