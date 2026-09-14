"""Static facts about the Photon Commerce API.

Environments, endpoint paths, document types, and default client tunables. These
mirror the verified API reference; keep them in sync with it.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "ADD_LINE_ITEM_PATH",
    "DEFAULT_BACKOFF_FACTOR",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_POLL_BACKOFF",
    "DEFAULT_POLL_INTERVAL",
    "DEFAULT_POLL_TIMEOUT",
    "DEFAULT_TIMEOUT",
    "DELETE_PATH",
    "DOWNLOAD_PATH",
    "HEALTH_PATH",
    "MAX_POLL_INTERVAL",
    "PROCESSING_MARKER",
    "PROCESSING_MESSAGE",
    "RATE_LIMIT_PER_SEC",
    "RETRIEVE_PATH",
    "SUBMIT_PATH",
    "UPDATE_LINE_ITEM_PATH",
    "UPDATE_PATH",
    "DocType",
    "Environment",
]


class Environment(str, Enum):
    """A Photon API environment. Each maps to a base URL."""

    SANDBOX = "sandbox"
    PRODUCTION = "production"

    @property
    def base_url(self) -> str:
        """The HTTPS base URL for this environment."""
        return _BASE_URLS[self]


_BASE_URLS = {
    Environment.SANDBOX: "https://sandbox-api.photoncommerce.com",
    Environment.PRODUCTION: "https://api.photoncommerce.com",
}


class DocType(str, Enum):
    """A document type accepted by the ``doctype`` submit parameter.

    The API defaults to :attr:`INVOICE` when no doctype is supplied.
    """

    INVOICE = "invoice"
    CHECK = "check"
    REMITTANCE = "remittance"
    STATEMENT = "statement"
    RECEIPT_EXPENSE = "receipt-expense"
    BOL = "bol"
    HBL = "hbl"
    MBL = "mbl"
    BILL_UTILITY = "bill-utility"


# Endpoint paths, relative to ``Environment.base_url``.
SUBMIT_PATH = "/api/pro"
RETRIEVE_PATH = "/api/v4/json"
UPDATE_PATH = "/api/v4/update"
UPDATE_LINE_ITEM_PATH = "/api/v4/update/line-items"
ADD_LINE_ITEM_PATH = "/api/v4/line-items"
DOWNLOAD_PATH = "/download-file"
DELETE_PATH = "/delete-file"
HEALTH_PATH = "/health"

# Body ``message`` returned (with HTTP 200) while a document is still processing.
# Detecting this is how polling knows the result is not ready yet.
PROCESSING_MESSAGE = "The document you submitted is being processed."
# The distinctive part of that sentence, matched case-insensitively so detection
# survives wording changes around it.
PROCESSING_MARKER = "being processed"

# Client defaults.
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.5

# Polling defaults, tuned for AI-only extraction, which finishes in seconds.
# Accounts with human verification can take minutes to hours, so those callers
# should raise ``timeout`` or receive a webhook instead of polling.
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_POLL_BACKOFF = 1.5
MAX_POLL_INTERVAL = 30.0
DEFAULT_POLL_TIMEOUT = 300.0
# The API accepts up to this many requests per second; excess is queued server-side.
RATE_LIMIT_PER_SEC = 10
