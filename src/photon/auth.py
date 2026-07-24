"""Authentication headers for the Photon API.

Every request (except account registration and key rotation) carries these four
headers.
"""

from __future__ import annotations

from .config import Config

__all__ = ["build_auth_headers"]


def build_auth_headers(config: Config) -> dict[str, str]:
    """Return the four authentication headers required by the Photon API."""
    return {
        "CLIENT-ID": config.client_id,
        "AUTHORIZATION": f"apikey {config.username}:{config.api_key}",
        "PASSWORD": config.password,
        "SECRET-KEY": config.secret_key,
    }
