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
from types import TracebackType
from typing import IO, TYPE_CHECKING, Any, cast

from ._transport import Transport
from .config import Config
from .constants import (
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    SUBMIT_PATH,
    DocType,
    Environment,
)
from .models import Submission

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

_SUBACCOUNT_MAX_LEN = 50
_SUBACCOUNT_RE = re.compile(r"^[A-Za-z0-9-]+$")


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
                client; a file object is read as-is and left open.
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
            raise ValueError(
                "subaccount must be 1-50 characters of letters, digits, or hyphens."
            )

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
                files = {_FILE_FIELD: document}
            elif isinstance(document, (str, os.PathLike)):
                handle = cleanup.enter_context(open(document, "rb"))
                files = {_FILE_FIELD: (os.path.basename(os.fspath(document)), handle)}
            elif document is not None:
                files = {_FILE_FIELD: document}

            body = self._transport.request_json(
                "POST", SUBMIT_PATH, params=params, files=files
            )

        return Submission.from_response(body)

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


def _is_valid_subaccount(subaccount: str) -> bool:
    return len(subaccount) <= _SUBACCOUNT_MAX_LEN and bool(_SUBACCOUNT_RE.match(subaccount))
