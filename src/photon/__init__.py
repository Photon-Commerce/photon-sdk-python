"""Photon SDK — Python client for Photon Commerce document processing."""

from __future__ import annotations

from ._version import __version__
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

__all__ = [
    "APIError",
    "AuthenticationError",
    "Config",
    "ConfigurationError",
    "DocType",
    "Environment",
    "ExtractionTimeoutError",
    "InvalidRequestError",
    "NotReadyError",
    "PhotonConnectionError",
    "PhotonError",
    "QuotaExceededError",
    "__version__",
]
