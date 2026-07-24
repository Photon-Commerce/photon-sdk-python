"""Exception hierarchy for the Photon SDK.

Every error raised by the SDK derives from :class:`PhotonError`, so callers can
catch that one type to handle any SDK failure. More specific subclasses are added
alongside the HTTP transport that raises them.
"""

from __future__ import annotations

__all__ = ["ConfigurationError", "PhotonError"]


class PhotonError(Exception):
    """Base class for all exceptions raised by the Photon SDK."""


class ConfigurationError(PhotonError):
    """The client is misconfigured — e.g. missing or invalid credentials.

    Raised locally, before any HTTP request is attempted.
    """
