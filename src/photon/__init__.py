"""Photon SDK — Python client for Photon Commerce document processing."""

from __future__ import annotations

from ._version import __version__
from .client import PhotonClient
from .config import Config
from .constants import DocType, Environment
from .exceptions import (
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
from .models import (
    BaseDocument,
    InvoiceDocument,
    LineItem,
    RawDocument,
    Submission,
    TaxLine,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "BaseDocument",
    "Config",
    "ConfigurationError",
    "DocType",
    "Environment",
    "ExtractionTimeoutError",
    "InvalidRequestError",
    "InvoiceDocument",
    "LineItem",
    "NotReadyError",
    "PhotonClient",
    "PhotonConnectionError",
    "PhotonError",
    "QuotaExceededError",
    "RawDocument",
    "Submission",
    "TaxLine",
    "__version__",
]
