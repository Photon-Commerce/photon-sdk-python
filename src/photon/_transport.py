"""The HTTP layer: one httpx client, plus response-to-exception classification.

Internal module. Public clients build on :class:`Transport` rather than touching
``httpx`` directly, so authentication, timeouts, and error mapping live in exactly
one place.

Classification reads the response **body** before the status code, because the API
puts the real outcome in the body's ``message``: a document that is still
processing comes back as an HTTP 200, and several genuine failures come back as
403. See the official API docs (apidocs.photoncommerce.com) for the responses.

Transient failures — a 5xx, or a request that never got an answer — are retried
with capped exponential backoff and jitter. A 4xx is never retried: it reports
a problem with the request or the account, which sending it again cannot fix.
The API has no 429; excess traffic is queued server-side instead.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING, Any

import httpx

from ._version import __version__
from .auth import build_auth_headers
from .config import Config
from .constants import MAX_RETRY_DELAY, PROCESSING_MARKER
from .exceptions import (
    APIError,
    AuthenticationError,
    InvalidRequestError,
    NotReadyError,
    PhotonConnectionError,
    QuotaExceededError,
)

if TYPE_CHECKING:
    # typing.Self only exists from 3.11; type checkers bundle typing_extensions,
    # so this needs no runtime dependency.
    from typing_extensions import Self

__all__ = ["Transport"]

logger = logging.getLogger(__name__)

USER_AGENT = f"photon-sdk-python/{__version__}"

# A 403 whose message mentions any of these is a quota problem, not a bad request.
_QUOTA_MARKERS = ("quota", "free trial", "exceeded", "upgrade")

# Body keys, in order of preference, that may hold the human-readable error text.
_MESSAGE_KEYS = ("message", "error", "detail")

# Cap on how much of a non-JSON error body is quoted back in an exception message.
_MAX_TEXT_SNIPPET = 200

# Methods that are safe to send twice: repeating one cannot create anything twice.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})

# Failures that happen before any of the request is sent, so even a POST can be
# retried after one without risk of submitting a document twice.
_NOT_SENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


class Transport:
    """Sends authenticated requests to the Photon API and raises typed errors.

    Holds an ``httpx.Client`` configured with the base URL, the four Photon auth
    headers, and the timeout from ``config``. Use it as a context manager, or call
    :meth:`close` when finished, so the connection pool is released.

    Transient failures are retried up to ``config.max_retries`` times. A GET,
    PUT, or DELETE is retried on any 5xx or network error. A POST is retried
    only when the connection itself failed: after a 5xx or a lost response the
    document may already have been accepted, and a second upload would create
    a duplicate and spend another metered call.

    Args:
        config: Credentials and connection settings.
        sleep: Override for :func:`time.sleep`, for tests.
        jitter: Override for :func:`random.random`, for tests. Must return a
            number in ``[0, 1)``.
    """

    def __init__(
        self,
        config: Config,
        *,
        sleep: Callable[[float], None] | None = None,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self.config = config
        self._sleep = time.sleep if sleep is None else sleep
        self._jitter = random.random if jitter is None else jitter
        self._client = httpx.Client(
            base_url=config.base_url,
            headers={**build_auth_headers(config), "User-Agent": USER_AGENT},
            timeout=config.timeout,
            # Never follow redirects: httpx strips only the Authorization header
            # on a cross-origin redirect, so following one would re-send the
            # CLIENT-ID, PASSWORD, and SECRET-KEY credentials to the redirect
            # target (and a redirected POST is re-issued as a bodyless GET). The
            # documented API never redirects; if an endpoint ever does, handle
            # it explicitly without credentials rather than re-enabling this.
            follow_redirects=False,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: dict[str, Any] | None = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send a request and return the successful response.

        Use this when the response is not JSON — a downloaded document, say.
        Prefer :meth:`request_json` otherwise.

        Args:
            method: HTTP method, e.g. ``"GET"``.
            path: Path relative to the base URL, e.g. ``"/api/v4/json"``.
            params: Query parameters; entries whose value is ``None`` are dropped.
            json: JSON request body.
            data: Form fields for a multipart or form-encoded body.
            files: Files for a multipart body, in httpx's format.
            headers: Extra headers, merged over the client's defaults.

        Returns:
            The response, which is guaranteed to have a 2xx status.

        Raises:
            NotReadyError: The document is still being processed.
            AuthenticationError: The credentials were rejected (401).
            QuotaExceededError: The account's allowance is used up (403).
            InvalidRequestError: The request or file was rejected (400/403).
            APIError: Any other unsuccessful response.
            PhotonConnectionError: The request never reached the API.
        """
        response, _ = self._request(
            method, path, params=params, json=json, data=data, files=files, headers=headers
        )
        return response

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: dict[str, Any] | None = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a request and return the decoded JSON object.

        Takes the same arguments as :meth:`request` and raises the same errors,
        plus an :class:`APIError` if the response body is not a JSON object.
        """
        response, body = self._request(
            method, path, params=params, json=json, data=data, files=files, headers=headers
        )
        if not isinstance(body, dict):
            raise APIError(
                f"Expected a JSON object from {method} {path}, got {_describe_content(response)}.",
                status_code=response.status_code,
                body=body,
            )
        return body

    def close(self) -> None:
        """Close the underlying connection pool. Safe to call more than once."""
        self._client.close()

    @property
    def is_closed(self) -> bool:
        """Whether the underlying client has been closed."""
        return self._client.is_closed

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Transport(base_url={self.config.base_url!r})"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: dict[str, Any] | None = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[httpx.Response, Any]:
        """Send one request, classify the result, and return it with its body."""
        response = self._send(
            method,
            path,
            params=_drop_none(params),
            json=json,
            data=data,
            files=files,
            headers=headers,
        )
        body = _decode_body(response)
        _raise_for_response(response, body)
        return response, body

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        json: Any,
        data: dict[str, Any] | None,
        files: Any,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        """Perform the network round trip, retrying transient failures.

        Returns the first response that is not retried — a success, a 4xx, or
        the last 5xx once retries run out — for the caller to classify.

        Raises:
            PhotonConnectionError: No response arrived, after any retries.
        """
        retries = 0
        while True:
            try:
                response = self._client.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    data=data,
                    files=files,
                    headers=headers,
                )
            except httpx.RequestError as exc:
                if not self._should_retry(method, retries, exc):
                    attempts = f" after {retries + 1} attempts" if retries else ""
                    raise PhotonConnectionError(f"{method} {path} failed{attempts}: {exc}") from exc
                # The exception's type, not its text: the text can quote the URL,
                # whose query string may carry a photon_key.
                reason = type(exc).__name__
            else:
                if not response.is_server_error or not self._should_retry(method, retries):
                    return response
                reason = f"HTTP {response.status_code}"

            retries += 1
            delay = self._backoff(retries)
            # Method and path only — never params, headers, or the body, which
            # carry credentials, photon_keys, and document contents.
            logger.debug(
                "Retrying %s %s after %s in %.2fs (retry %d of %d)",
                method,
                path,
                reason,
                delay,
                retries,
                self.config.max_retries,
            )
            self._sleep(delay)

    def _should_retry(
        self, method: str, retries: int, error: httpx.RequestError | None = None
    ) -> bool:
        """Whether a failed attempt may be repeated; ``error`` is ``None`` for a 5xx."""
        if retries >= self.config.max_retries:
            return False
        if method.upper() in _IDEMPOTENT_METHODS:
            return True
        return isinstance(error, _NOT_SENT_ERRORS)

    def _backoff(self, retry: int) -> float:
        """The wait before retry number ``retry`` (1-based), with "equal jitter".

        The ceiling doubles each time from ``backoff_factor``, capped at
        :data:`MAX_RETRY_DELAY`; the wait is drawn from its upper half, so
        clients that failed together spread out but never retry immediately.
        """
        ceiling = min(self.config.backoff_factor * 2.0 ** (retry - 1), MAX_RETRY_DELAY)
        return ceiling / 2 + self._jitter() * ceiling / 2


def _raise_for_response(response: httpx.Response, body: Any) -> None:
    """Raise the exception a response calls for, or return if it succeeded."""
    status = response.status_code
    message = _extract_message(response, body)

    if response.is_success:
        # A still-processing document is reported as a successful JSON response.
        # Only a JSON body can carry that signal — matching it against other
        # content would misread a downloaded document that happens to contain
        # the words.
        if isinstance(body, dict) and PROCESSING_MARKER in message.lower():
            raise NotReadyError(message, status_code=status, body=body)
        return

    if response.is_redirect:
        location = response.headers.get("location", "unknown")
        raise APIError(
            f"Unexpected redirect to {location!r}. The SDK does not follow "
            "redirects, to avoid re-sending credentials to another host.",
            status_code=status,
            body=body,
        )

    if status == httpx.codes.UNAUTHORIZED:
        raise AuthenticationError(message, status_code=status, body=body)

    if status == httpx.codes.FORBIDDEN:
        lowered = message.lower()
        if any(marker in lowered for marker in _QUOTA_MARKERS):
            raise QuotaExceededError(message, status_code=status, body=body)
        raise InvalidRequestError(message, status_code=status, body=body)

    if status == httpx.codes.BAD_REQUEST:
        raise InvalidRequestError(message, status_code=status, body=body)

    raise APIError(message, status_code=status, body=body)


def _decode_body(response: httpx.Response) -> Any:
    """Return the decoded JSON body, or ``None`` if it is not JSON.

    Only bodies the API declares as JSON are decoded, so that a downloaded
    document is never parsed as text.
    """
    if "json" not in response.headers.get("content-type", "").lower():
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _extract_message(response: httpx.Response, body: Any) -> str:
    """Find the most useful human-readable description of a response."""
    if isinstance(body, dict):
        for key in _MESSAGE_KEYS:
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value
    snippet = _text_snippet(response)
    if snippet:
        return snippet
    return response.reason_phrase or f"HTTP {response.status_code}"


def _text_snippet(response: httpx.Response) -> str:
    """Return a truncated textual body, for error pages that are not JSON."""
    if not response.headers.get("content-type", "").lower().startswith("text/"):
        return ""
    text = response.text.strip()
    if len(text) > _MAX_TEXT_SNIPPET:
        return text[:_MAX_TEXT_SNIPPET] + "…"
    return text


def _describe_content(response: httpx.Response) -> str:
    """Describe a response body that could not be used as JSON."""
    content_type = response.headers.get("content-type", "")
    if content_type:
        return f"content-type {content_type!r}"
    return "a body with no content-type" if response.content else "an empty body"


def _drop_none(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove unset query parameters so they are not sent as the string "None"."""
    if params is None:
        return None
    return {key: value for key, value in params.items() if value is not None}
