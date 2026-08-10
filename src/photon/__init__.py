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
from .models import Submission

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
    "PhotonClient",
    "PhotonConnectionError",
    "PhotonError",
    "QuotaExceededError",
    "Submission",
    "__version__",
]
