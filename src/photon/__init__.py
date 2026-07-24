"""Photon SDK — Python client for Photon Commerce document processing."""

from __future__ import annotations

from .config import Config
from .constants import DocType, Environment
from .exceptions import ConfigurationError, PhotonError

__version__ = "0.0.1"

__all__ = [
    "Config",
    "ConfigurationError",
    "DocType",
    "Environment",
    "PhotonError",
    "__version__",
]
