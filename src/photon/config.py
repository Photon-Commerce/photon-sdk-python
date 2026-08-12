"""Client configuration and credential handling.

:class:`Config` bundles the five Photon credentials with connection settings. It
validates that credentials are present, derives the base URL from the environment,
and never exposes secrets in its ``repr``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .constants import (
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    Environment,
)
from .exceptions import ConfigurationError

__all__ = ["Config"]

_ENV_PREFIX = "PHOTON_"
_REQUIRED_CREDENTIALS = ("client_id", "username", "api_key", "password", "secret_key")
_SECRET_FIELDS = frozenset({"client_id", "api_key", "password", "secret_key"})


@dataclass(frozen=True, repr=False)
class Config:
    """Immutable client configuration.

    Args:
        client_id: The ``CLIENT-ID`` credential.
        username: The account username (email); used in the ``AUTHORIZATION`` header.
        api_key: The API key; used in the ``AUTHORIZATION`` header.
        password: The ``PASSWORD`` credential.
        secret_key: The ``SECRET-KEY`` credential.
        environment: Which API environment to target. Defaults to sandbox.
        base_url: Overrides the environment's base URL when set.
        timeout: Per-request timeout, in seconds.
        max_retries: How many times to retry transient failures.
        backoff_factor: Base delay (seconds) for exponential retry backoff.

    Raises:
        ConfigurationError: If a credential is missing or the environment is unknown.
    """

    client_id: str
    username: str
    api_key: str
    password: str
    secret_key: str
    environment: Environment = Environment.SANDBOX
    base_url: str = ""
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR

    def __post_init__(self) -> None:
        # Coerce a string environment (e.g. from an env var) to the enum.
        if not isinstance(self.environment, Environment):
            try:
                coerced = Environment(str(self.environment).lower())
            except ValueError as exc:
                valid = ", ".join(env.value for env in Environment)
                raise ConfigurationError(
                    f"Unknown environment {self.environment!r}. Valid options: {valid}."
                ) from exc
            object.__setattr__(self, "environment", coerced)

        missing = [name for name in _REQUIRED_CREDENTIALS if not getattr(self, name)]
        if missing:
            raise ConfigurationError(
                "Missing required credential(s): " + ", ".join(missing) + "."
            )

        # Derive the base URL from the environment unless one was given explicitly.
        if not self.base_url:
            object.__setattr__(self, "base_url", self.environment.base_url)
            return

        # An explicit base_url that is really the *other* environment's stock URL
        # would silently send this environment's traffic to the wrong host — the
        # easy way to hit it is dataclasses.replace(config, environment=...),
        # which copies the already-derived base_url along. Refuse loudly.
        for env in Environment:
            if self.base_url == env.base_url and env is not self.environment:
                raise ConfigurationError(
                    f"base_url {self.base_url!r} is the {env.value} environment's URL, "
                    f"but environment is {self.environment.value!r}. Set "
                    f"environment={env.value!r} instead, or pass base_url='' to derive "
                    "the URL from the environment."
                )

    @classmethod
    def from_env(cls, **overrides: Any) -> Config:
        """Build a Config from ``PHOTON_*`` environment variables.

        Reads ``PHOTON_CLIENT_ID``, ``PHOTON_USERNAME``, ``PHOTON_API_KEY``,
        ``PHOTON_PASSWORD``, ``PHOTON_SECRET_KEY`` and, optionally,
        ``PHOTON_ENVIRONMENT`` / ``PHOTON_BASE_URL``. Explicit keyword ``overrides``
        take precedence over the environment.
        """
        values: dict[str, Any] = {
            name: os.environ.get(_ENV_PREFIX + name.upper(), "")
            for name in _REQUIRED_CREDENTIALS
        }
        # An empty value means unset, same as PHOTON_BASE_URL below — a blank
        # line in a .env file should fall back to the default, not error.
        environment = os.environ.get(_ENV_PREFIX + "ENVIRONMENT")
        if environment:
            values["environment"] = environment
        base_url = os.environ.get(_ENV_PREFIX + "BASE_URL")
        if base_url:
            values["base_url"] = base_url
        values.update(overrides)
        return cls(**values)

    def __repr__(self) -> str:
        def show(name: str) -> str:
            value = getattr(self, name)
            if name in _SECRET_FIELDS:
                return "'***'" if value else "''"
            return repr(value)

        fields = (
            f"username={show('username')}",
            f"environment={self.environment.value!r}",
            f"base_url={self.base_url!r}",
            f"client_id={show('client_id')}",
            f"api_key={show('api_key')}",
            f"password={show('password')}",
            f"secret_key={show('secret_key')}",
        )
        return f"Config({', '.join(fields)})"
