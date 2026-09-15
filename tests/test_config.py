"""Tests for Config: defaults, environment handling, validation, masking, from_env."""

from __future__ import annotations

import dataclasses

import pytest

from photon.config import Config
from photon.constants import Environment
from photon.exceptions import ConfigurationError


def make_config(
    client_id: str = "AAA111",
    username: str = "user@example.com",
    api_key: str = "BBB222",
    password: str = "CCC333",
    secret_key: str = "DDD444",
    environment: Environment = Environment.SANDBOX,
    base_url: str = "",
) -> Config:
    return Config(
        client_id=client_id,
        username=username,
        api_key=api_key,
        password=password,
        secret_key=secret_key,
        environment=environment,
        base_url=base_url,
    )


def test_defaults_to_sandbox() -> None:
    config = make_config()
    assert config.environment is Environment.SANDBOX
    assert config.base_url == "https://sandbox-api.photoncommerce.com"


def test_production_base_url() -> None:
    config = make_config(environment=Environment.PRODUCTION)
    assert config.base_url == "https://api.photoncommerce.com"


def test_explicit_base_url_overrides_environment() -> None:
    config = make_config(base_url="https://example.test")
    assert config.base_url == "https://example.test"


def test_replace_with_a_new_environment_rejects_the_stale_base_url() -> None:
    config = make_config(environment=Environment.PRODUCTION)
    with pytest.raises(ConfigurationError, match="base_url"):
        dataclasses.replace(config, environment=Environment.SANDBOX)


def test_replace_with_a_new_environment_and_cleared_base_url_rederives() -> None:
    config = make_config(environment=Environment.PRODUCTION)
    replaced = dataclasses.replace(config, environment=Environment.SANDBOX, base_url="")
    assert replaced.base_url == "https://sandbox-api.photoncommerce.com"


def test_custom_base_url_survives_replace() -> None:
    config = make_config(base_url="https://proxy.example.test")
    replaced = dataclasses.replace(config, environment=Environment.PRODUCTION)
    assert replaced.base_url == "https://proxy.example.test"


def test_the_other_environments_stock_url_is_rejected() -> None:
    # environment defaults to sandbox; the production URL contradicts it.
    with pytest.raises(ConfigurationError, match="production"):
        make_config(base_url="https://api.photoncommerce.com")


def test_the_matching_environments_stock_url_is_accepted() -> None:
    config = make_config(base_url="https://sandbox-api.photoncommerce.com")
    assert config.environment is Environment.SANDBOX


def test_missing_client_id_raises() -> None:
    with pytest.raises(ConfigurationError, match="client_id"):
        make_config(client_id="")


def test_missing_username_raises() -> None:
    with pytest.raises(ConfigurationError, match="username"):
        make_config(username="")


def test_missing_api_key_raises() -> None:
    with pytest.raises(ConfigurationError, match="api_key"):
        make_config(api_key="")


def test_missing_password_raises() -> None:
    with pytest.raises(ConfigurationError, match="password"):
        make_config(password="")


def test_missing_secret_key_raises() -> None:
    with pytest.raises(ConfigurationError, match="secret_key"):
        make_config(secret_key="")


def test_repr_masks_secrets_but_shows_username() -> None:
    config = make_config()
    text = repr(config)
    for secret in ("AAA111", "BBB222", "CCC333", "DDD444"):
        assert secret not in text
    assert "***" in text
    assert "user@example.com" in text
    assert "sandbox" in text


def test_from_env_reads_all_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHOTON_CLIENT_ID", "cid")
    monkeypatch.setenv("PHOTON_USERNAME", "user")
    monkeypatch.setenv("PHOTON_API_KEY", "key")
    monkeypatch.setenv("PHOTON_PASSWORD", "pw")
    monkeypatch.setenv("PHOTON_SECRET_KEY", "sk")
    monkeypatch.setenv("PHOTON_ENVIRONMENT", "production")

    config = Config.from_env()

    assert config.client_id == "cid"
    assert config.username == "user"
    assert config.environment is Environment.PRODUCTION
    assert config.base_url == "https://api.photoncommerce.com"


def test_from_env_coerces_uppercase_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "CLIENT_ID": "cid",
        "USERNAME": "user",
        "API_KEY": "key",
        "PASSWORD": "pw",
        "SECRET_KEY": "sk",
        "ENVIRONMENT": "PRODUCTION",
    }.items():
        monkeypatch.setenv("PHOTON_" + name, value)

    assert Config.from_env().environment is Environment.PRODUCTION


def test_from_env_unknown_environment_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "CLIENT_ID": "cid",
        "USERNAME": "user",
        "API_KEY": "key",
        "PASSWORD": "pw",
        "SECRET_KEY": "sk",
        "ENVIRONMENT": "staging",
    }.items():
        monkeypatch.setenv("PHOTON_" + name, value)

    with pytest.raises(ConfigurationError, match="Unknown environment"):
        Config.from_env()


def test_from_env_empty_environment_falls_back_to_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {
        "CLIENT_ID": "cid",
        "USERNAME": "user",
        "API_KEY": "key",
        "PASSWORD": "pw",
        "SECRET_KEY": "sk",
        "ENVIRONMENT": "",
    }.items():
        monkeypatch.setenv("PHOTON_" + name, value)

    config = Config.from_env()

    assert config.environment is Environment.SANDBOX
    assert config.base_url == "https://sandbox-api.photoncommerce.com"


def test_from_env_reads_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "CLIENT_ID": "cid",
        "USERNAME": "user",
        "API_KEY": "key",
        "PASSWORD": "pw",
        "SECRET_KEY": "sk",
        "BASE_URL": "https://proxy.example.test",
    }.items():
        monkeypatch.setenv("PHOTON_" + name, value)
    monkeypatch.delenv("PHOTON_ENVIRONMENT", raising=False)

    assert Config.from_env().base_url == "https://proxy.example.test"


def test_from_env_empty_base_url_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "CLIENT_ID": "cid",
        "USERNAME": "user",
        "API_KEY": "key",
        "PASSWORD": "pw",
        "SECRET_KEY": "sk",
        "BASE_URL": "",
    }.items():
        monkeypatch.setenv("PHOTON_" + name, value)
    monkeypatch.delenv("PHOTON_ENVIRONMENT", raising=False)

    assert Config.from_env().base_url == "https://sandbox-api.photoncommerce.com"


def test_from_env_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CLIENT_ID", "USERNAME", "API_KEY", "PASSWORD", "SECRET_KEY", "ENVIRONMENT"):
        monkeypatch.delenv("PHOTON_" + name, raising=False)

    with pytest.raises(ConfigurationError):
        Config.from_env()


def test_from_env_explicit_overrides_take_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHOTON_CLIENT_ID", "env-cid")
    monkeypatch.setenv("PHOTON_USERNAME", "user")
    monkeypatch.setenv("PHOTON_API_KEY", "key")
    monkeypatch.setenv("PHOTON_PASSWORD", "pw")
    monkeypatch.setenv("PHOTON_SECRET_KEY", "sk")

    config = Config.from_env(client_id="explicit-cid")

    assert config.client_id == "explicit-cid"
