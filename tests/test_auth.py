"""Tests for building the four Photon authentication headers."""

from __future__ import annotations

from photon.auth import build_auth_headers
from photon.config import Config


def _config() -> Config:
    return Config(
        client_id="cid",
        username="user@example.com",
        api_key="key",
        password="pw",
        secret_key="sk",
    )


def test_build_auth_headers_exact_shape() -> None:
    assert build_auth_headers(_config()) == {
        "CLIENT-ID": "cid",
        "AUTHORIZATION": "apikey user@example.com:key",
        "PASSWORD": "pw",
        "SECRET-KEY": "sk",
    }


def test_authorization_header_format() -> None:
    headers = build_auth_headers(
        Config(
            client_id="cid",
            username="u",
            api_key="k",
            password="pw",
            secret_key="sk",
        )
    )
    assert headers["AUTHORIZATION"] == "apikey u:k"
