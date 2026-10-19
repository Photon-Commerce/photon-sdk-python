"""The public synchronous client.

:class:`PhotonClient` is the SDK's front door: configure it once with the five
Photon credentials, then call its methods. HTTP mechanics and error
classification live in :mod:`photon._transport`; this module owns argument
validation, request shaping, and response models.
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from types import TracebackType
from typing import IO, TYPE_CHECKING, Any, cast, overload

from ._polling import poll, validate_settings
from ._transport import Transport
from .config import Config
from .constants import (
    ADD_LINE_ITEM_PATH,
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_MAX_RETRIES,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLL_TIMEOUT,
    DEFAULT_TIMEOUT,
    RETRIEVE_PATH,
    SUBMIT_PATH,
    UPDATE_LINE_ITEM_PATH,
    UPDATE_PATH,
    DocType,
    Environment,
)
from .exceptions import APIError, InvalidRequestError
from .models import BaseDocument, Submission, document_for

if TYPE_CHECKING:
    # typing.Self only exists from 3.11; type checkers bundle typing_extensions,
    # so this needs no runtime dependency.
    from typing_extensions import Self

__all__ = ["PhotonClient"]

# What ``submit`` accepts as a document: a filesystem path, an open binary file
# object, or the file's bytes.
DocumentInput = str | os.PathLike[str] | IO[bytes] | bytes

# The multipart form field the API expects the uploaded file in, whatever the
# actual file type.
_FILE_FIELD = "pdf"

# Filename sent for raw bytes and unnamed file objects. The API recognises file
# types by extension, so the upload must carry one; callers whose content is not
# a PDF should pass a path or a named file object instead.
_DEFAULT_FILENAME = "upload.pdf"

_SUBACCOUNT_MAX_LEN = 50
_SUBACCOUNT_RE = re.compile(r"[A-Za-z0-9-]+")

# Line item IDs are the API's own numbering: ASCII digits only.
_LINE_ITEM_ID_RE = re.compile(r"[0-9]+")


class PhotonClient:
    """Synchronous client for the Photon Commerce API.

    Use it as a context manager, or call :meth:`close` when finished, so the
    connection pool is released.

    Args:
        client_id: The ``CLIENT-ID`` credential.
        username: The account username (email).
        api_key: The API key.
        password: The ``PASSWORD`` credential.
        secret_key: The ``SECRET-KEY`` credential.
        environment: Which API environment to target, ``"sandbox"`` (default)
            or ``"production"``.
        base_url: Overrides the environment's base URL when set.
        timeout: Per-request timeout, in seconds.
        max_retries: How many times to retry transient failures.
        backoff_factor: Base delay (seconds) for exponential retry backoff.

    Raises:
        ConfigurationError: If a credential is missing or the environment is
            unknown.
    """

    def __init__(
        self,
        client_id: str = "",
        username: str = "",
        api_key: str = "",
        password: str = "",
        secret_key: str = "",
        *,
        environment: Environment | str = Environment.SANDBOX,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    ) -> None:
        self.config = Config(
            client_id=client_id,
            username=username,
            api_key=api_key,
            password=password,
            secret_key=secret_key,
            # Config coerces a string environment itself, with a better error.
            environment=cast(Environment, environment),
            base_url=base_url or "",
            timeout=timeout,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
        )
        self._transport = Transport(self.config)

    @classmethod
    def from_env(cls, **overrides: Any) -> PhotonClient:
        """Build a client from ``PHOTON_*`` environment variables.

        See :meth:`Config.from_env` for the variables read. Explicit keyword
        ``overrides`` take precedence over the environment, e.g.
        ``PhotonClient.from_env(environment="production")``.
        """
        config = Config.from_env(**overrides)
        return cls(
            client_id=config.client_id,
            username=config.username,
            api_key=config.api_key,
            password=config.password,
            secret_key=config.secret_key,
            environment=config.environment,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
            backoff_factor=config.backoff_factor,
        )

    def submit(
        self,
        document: DocumentInput | None = None,
        *,
        doctype: DocType | str = DocType.INVOICE,
        url: str | None = None,
        webhook_url: str | None = None,
        auth_token: str | None = None,
        reference_id: str | None = None,
        subaccount: str | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
    ) -> Submission:
        """Submit a document for extraction.

        Exactly one of ``document`` and ``url`` must be given.

        Args:
            document: The document to upload — a path, an open binary file
                object, or raw bytes. A path is opened and closed by the
                client; a file object is read as-is and left open. The API
                recognises file types by filename extension, so raw bytes and
                unnamed file objects are uploaded as ``upload.pdf``; for other
                file types, pass a path or a file object with a ``.name``.
            doctype: What kind of document this is; the API defaults to
                invoice. Any string is passed through, so doctypes newer than
                this SDK still work.
            url: Publicly fetchable URL of the document, as an alternative to
                uploading it.
            webhook_url: Endpoint Photon calls (POST) when processing finishes.
            auth_token: Value Photon echoes back in the webhook's
                ``Authorization`` header, so the receiver can verify the sender.
            reference_id: Your own correlation ID, echoed in the webhook body.
                Sent to the API as ``ID``.
            subaccount: Sub-account to attribute this call to. Letters, digits,
                and hyphens; at most 50 characters.
            page_start: First page to process (1-based, inclusive).
            page_end: Last page to process (1-based, inclusive).

        Returns:
            A :class:`Submission` carrying the ``photon_key`` (to retrieve the
            result) and ``doc_path`` (to fetch or delete the original later).

        Raises:
            ValueError: Neither or both of ``document``/``url`` given, or an
                invalid ``subaccount`` — checked before any I/O.
            PhotonError: See :meth:`Transport.request_json` for the mapping.
        """
        if (document is None) == (url is None):
            raise ValueError("Pass exactly one of 'document' or 'url'.")
        if subaccount is not None and not _is_valid_subaccount(subaccount):
            raise ValueError("subaccount must be 1-50 characters of letters, digits, or hyphens.")

        params: dict[str, Any] = {
            "doctype": doctype.value if isinstance(doctype, DocType) else str(doctype),
            "url": url,
            "webhook_url": webhook_url,
            "auth_token": auth_token,
            "ID": reference_id,
            "subaccount": subaccount,
            "page_start": page_start,
            "page_end": page_end,
        }

        # A path is opened (and closed) here; a caller's file object is not ours
        # to close, so it never enters the stack.
        with contextlib.ExitStack() as cleanup:
            files: Any = None
            if isinstance(document, bytes):
                files = {_FILE_FIELD: (_DEFAULT_FILENAME, document)}
            elif isinstance(document, (str, os.PathLike)):
                handle = cleanup.enter_context(open(document, "rb"))
                files = {_FILE_FIELD: (os.path.basename(os.fspath(document)), handle)}
            elif document is not None:
                files = {_FILE_FIELD: (_filename_for(document), document)}

            body = self._transport.request_json("POST", SUBMIT_PATH, params=params, files=files)

        return Submission.from_response(body)

    def retrieve(
        self,
        photon_key: str,
        *,
        doctype: DocType | str = DocType.INVOICE,
    ) -> BaseDocument:
        """Fetch the extraction result for a submitted document.

        Args:
            photon_key: The key from :attr:`Submission.photon_key`.
            doctype: The doctype this document was submitted as. It decides how
                the result is typed — the API's response carries no doctype of
                its own — so pass the same value you submitted with.

        Returns:
            The extracted document: an :class:`InvoiceDocument` for invoices and
            receipt-expenses, otherwise a :class:`RawDocument`. Either way the
            API's own field names work as keys (``doc["Vendor_Name"]``) and the
            untouched payload is on ``doc.raw``.

        Raises:
            ValueError: ``photon_key`` is empty — checked before any I/O.
            NotReadyError: The document is still being processed; retry later,
                or let :meth:`extract` do the waiting.
            APIError: The response reported success but carried no ``data``
                object.
            PhotonError: See :meth:`Transport.request_json` for the rest of
                the mapping.
        """
        _check_photon_key(photon_key)

        body = self._transport.request_json("GET", RETRIEVE_PATH, params={"photon_key": photon_key})

        data = body.get("data")
        if not isinstance(data, dict):
            raise APIError(
                "The response reported success but did not include a 'data' object.",
                body=body,
            )
        return document_for(data, doctype)

    @overload
    def extract(
        self,
        document: DocumentInput | None = ...,
        *,
        doctype: DocType | str = ...,
        poll_interval: float = ...,
        timeout: float = ...,
        **submit_kwargs: Any,
    ) -> BaseDocument: ...

    @overload
    def extract(
        self,
        document: DocumentInput | None = ...,
        *,
        doctype: DocType | str = ...,
        poll_interval: float = ...,
        timeout: None,
        **submit_kwargs: Any,
    ) -> Submission: ...

    def extract(
        self,
        document: DocumentInput | None = None,
        *,
        doctype: DocType | str = DocType.INVOICE,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float | None = DEFAULT_POLL_TIMEOUT,
        **submit_kwargs: Any,
    ) -> BaseDocument | Submission:
        """Submit a document and wait for its extracted result.

        The one-call form of :meth:`submit` followed by :meth:`retrieve`: it
        polls until the document finishes processing, on a capped exponential
        backoff, and returns the result.

        Args:
            document: The document to extract — a path, an open binary file
                object, or raw bytes. See :meth:`submit`.
            doctype: What kind of document this is.
            poll_interval: Seconds to wait before the first re-check. Later
                waits grow geometrically, capped at
                :data:`~photon.constants.MAX_POLL_INTERVAL`.
            timeout: How long to keep polling, in seconds. The default suits
                AI-only extraction, which finishes in seconds; accounts with
                human verification can take minutes to hours, so raise it (or
                use a webhook). ``None`` skips polling entirely and returns the
                :class:`Submission`, for webhook-driven flows.
            **submit_kwargs: Any other :meth:`submit` argument — ``url``,
                ``webhook_url``, ``auth_token``, ``reference_id``,
                ``subaccount``, ``page_start``, ``page_end``.

        Returns:
            The extracted document, as :meth:`retrieve` returns it — or the
            :class:`Submission`, when ``timeout`` is ``None``.

        Raises:
            ValueError: An invalid argument, as for :meth:`submit`, or a
                ``poll_interval`` that is not positive — both checked before
                anything is uploaded.
            ExtractionTimeoutError: Still processing when ``timeout`` expired.
                The document is not lost: retrieve it later with its
                ``photon_key``, which the error's submission carries.
            PhotonError: See :meth:`submit` and :meth:`retrieve`.
        """
        if timeout is not None:
            # Check before submitting: otherwise a bad interval costs an upload
            # and an API call before poll() ever sees it.
            validate_settings(interval=poll_interval)

        submission = self.submit(document, doctype=doctype, **submit_kwargs)
        if timeout is None:
            return submission

        if not submission.photon_key:
            raise APIError(
                "The submission succeeded but returned no 'photon_key', "
                "so the result cannot be retrieved.",
                body=submission.raw,
            )

        return poll(
            lambda: self.retrieve(submission.photon_key, doctype=doctype),
            timeout=timeout,
            interval=poll_interval,
        )

    def update_fields(self, photon_key: str, fields: Mapping[str, Any]) -> None:
        """Correct extracted fields on a processed document.

        Keys are the **API's own field names**, exactly as the result spells
        them — ``{"Vendor_Name": ..., "Total": ...}`` for an invoice. They are
        sent as given: the SDK does not translate attribute names such as
        ``vendor_name``, because the same word means different fields in
        different doctype families (``total`` is a check's field, ``Total`` an
        invoice's). :class:`~decimal.Decimal` and :class:`~datetime.date`
        values are sent as strings (``"1397.50"``, ``"2026-10-19"``).

        Args:
            photon_key: The document's key, from :attr:`Submission.photon_key`.
            fields: The fields to change, by API field name.

        Raises:
            ValueError: ``photon_key`` or ``fields`` is empty, or a field name
                is not a non-empty string — checked before any I/O.
            InvalidRequestError: The API rejected the update.
            PhotonError: See :meth:`Transport.request_json` for the rest of
                the mapping.
        """
        _check_photon_key(photon_key)
        body = _json_fields(fields)
        response = self._transport.request_json(
            "PUT", UPDATE_PATH, params={"photon_key": photon_key}, json=body
        )
        _expect_success(response)

    def update_line_item(
        self, photon_key: str, line_item_id: int | str, fields: Mapping[str, Any]
    ) -> None:
        """Correct fields on one of a document's line items.

        Args:
            photon_key: The document's key.
            line_item_id: The line's ID — its ``Line`` number on an invoice.
            fields: The line fields to change, by API field name, e.g.
                ``{"QTY": 12, "Amount": "1380.00"}``. Sent as for
                :meth:`update_fields`.

        Raises:
            ValueError: An empty ``photon_key`` or ``fields``, or a
                ``line_item_id`` that is not a whole number — checked before
                any I/O.
            InvalidRequestError: The API rejected the update, e.g. no line has
                that ID.
            PhotonError: See :meth:`Transport.request_json` for the rest of
                the mapping.
        """
        _check_photon_key(photon_key)
        path = _line_item_path(line_item_id)
        body = _json_fields(fields)
        response = self._transport.request_json(
            "PUT", path, params={"photon_key": photon_key}, json=body
        )
        _expect_success(response)

    def add_line_item(
        self, photon_key: str, fields: Mapping[str, Any], *, url: str | None = None
    ) -> None:
        """Add a line item to an invoice or receipt.

        This is the invoice-family endpoint. Checks and remittances add lines
        through a different one, which this release does not wrap.

        Not retried after a server error or a lost response: the line may
        already have been added, and a second request would add it twice.

        Args:
            photon_key: The document's key.
            fields: The new line, by API field name, e.g.
                ``{"Line": 3, "SKU": "WID-300", "Description": "Widget",
                "QTY": 1, "Price": "10.00", "Amount": "10.00"}``. Sent as for
                :meth:`update_fields`.
            url: The document's URL, for documents submitted by URL.

        Raises:
            ValueError: An empty ``photon_key`` or ``fields`` — checked before
                any I/O.
            InvalidRequestError: The API rejected the line, e.g. one with that
                ``Line`` number already exists.
            PhotonError: See :meth:`Transport.request_json` for the rest of
                the mapping.
        """
        _check_photon_key(photon_key)
        body = _json_fields(fields)
        response = self._transport.request_json(
            "POST", ADD_LINE_ITEM_PATH, params={"photon_key": photon_key, "url": url}, json=body
        )
        _expect_success(response)

    def delete_line_item(self, photon_key: str, line_item_id: int | str) -> None:
        """Delete one of a document's line items.

        Not retried after a server error or a lost response. The first request
        may have succeeded, and if the API renumbers the remaining lines, a
        repeat would delete a different one.

        Args:
            photon_key: The document's key.
            line_item_id: The line's ID — its ``Line`` number on an invoice.

        Raises:
            ValueError: An empty ``photon_key``, or a ``line_item_id`` that is
                not a whole number — checked before any I/O.
            InvalidRequestError: The API rejected the delete, e.g. no line has
                that ID.
            PhotonError: See :meth:`Transport.request_json` for the rest of
                the mapping.
        """
        _check_photon_key(photon_key)
        path = _line_item_path(line_item_id)
        response = self._transport.request_json(
            "DELETE", path, params={"photon_key": photon_key}, idempotent=False
        )
        _expect_success(response)

    def close(self) -> None:
        """Close the underlying connection pool. Safe to call more than once."""
        self._transport.close()

    @property
    def is_closed(self) -> bool:
        """Whether :meth:`close` has been called."""
        return self._transport.is_closed

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
        return (
            f"PhotonClient(environment={self.config.environment.value!r}, "
            f"base_url={self.config.base_url!r})"
        )


def _filename_for(document: IO[bytes]) -> str:
    """The filename to upload a file object under.

    The API recognises file types by the uploaded filename's extension, so an
    unnamed stream (``BytesIO``, a pipe, a fd-opened file) gets the default
    rather than httpx's extensionless fallback.
    """
    name = getattr(document, "name", None)
    if isinstance(name, str) and os.path.basename(name):
        return os.path.basename(name)
    return _DEFAULT_FILENAME


def _is_valid_subaccount(subaccount: str) -> bool:
    # fullmatch, not match: with match, "$" would accept a trailing newline.
    return len(subaccount) <= _SUBACCOUNT_MAX_LEN and bool(_SUBACCOUNT_RE.fullmatch(subaccount))


def _check_photon_key(photon_key: str) -> None:
    if not isinstance(photon_key, str) or not photon_key.strip():
        raise ValueError("photon_key must be a non-empty string.")


def _line_item_path(line_item_id: int | str) -> str:
    """The update/delete path for a line item, after checking its ID."""
    # bool is an int subclass; True is a mistake, not line 1.
    valid_type = isinstance(line_item_id, (int, str)) and not isinstance(line_item_id, bool)
    text = str(line_item_id).strip() if valid_type else ""
    if not _LINE_ITEM_ID_RE.fullmatch(text):
        raise ValueError(f"line_item_id must be a whole number, got {line_item_id!r}.")
    return f"{UPDATE_LINE_ITEM_PATH}/{text}"


def _json_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Check an update's fields and make their values JSON-serialisable."""
    if not isinstance(fields, Mapping) or not fields:
        raise ValueError("fields must be a non-empty mapping of API field names to values.")
    body: dict[str, Any] = {}
    for name, value in fields.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Field names must be non-empty strings, got {name!r}.")
        body[name] = _json_value(value)
    return body


def _json_value(value: Any) -> Any:
    # The models parse amounts to Decimal and dates to date; accept them back.
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _expect_success(body: dict[str, Any]) -> None:
    """Raise if a 2xx response's body still reports a failure."""
    status = body.get("status")
    if status is None or (isinstance(status, str) and status.lower() == "success"):
        return
    message = body.get("message")
    raise InvalidRequestError(
        message if isinstance(message, str) and message else f"Request failed: {status!r}",
        body=body,
    )
