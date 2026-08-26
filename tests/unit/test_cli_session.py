from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from mika.cli import config as cli_config
from mika.cli import env_secrets
from mika.cli.errors import NoActiveRouterError, SecretNotFoundError
from mika.cli.session import ChatSession
from mika.router.mock import MockRouterClient


@pytest.fixture
def temp_config_path():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        path = Path(f.name)
    try:
        yield path
    finally:
        if path.exists():
            path.unlink()


@pytest.fixture
def session_with_mock_router(temp_config_path):
    cfg = cli_config.AppConfig(
        routers={
            "mock-router": cli_config.RouterProfileConfig(
                host="192.168.88.1",
                username="admin",
                port=443,
                backend="mock",
            )
        }
    )
    cli_config.save_config(cfg, temp_config_path)
    session = ChatSession.create(temp_config_path)
    return session


def test_session_create_empty_config(temp_config_path):
    temp_config_path.unlink()
    session = ChatSession.create(temp_config_path)
    assert session.router_alias is None
    assert session.provider is None
    assert session.history == []


def test_session_connect_mock_router(session_with_mock_router):
    session = session_with_mock_router
    session.connect_router("mock-router")
    assert session.router_alias == "mock-router"
    assert isinstance(session.router_client, MockRouterClient)


def test_session_connect_unknown_router_raises(session_with_mock_router):
    session = session_with_mock_router
    with pytest.raises(cli_config.RouterProfileNotFoundError):
        session.connect_router("unknown")


def test_session_create_stale_active_router_does_not_crash(temp_config_path):
    """active_router pointing at a profile that no longer exists must not
    crash startup — it should fall back to "no active router" instead."""
    cfg = cli_config.AppConfig(
        routers={},
        active_router="ghost-router",
    )
    cli_config.save_config(cfg, temp_config_path)

    session = ChatSession.create(temp_config_path)

    assert session.router_alias is None
    assert session.config.active_router is None


@patch("mika.cli.env_secrets.get_router_secret", return_value="password123")
def test_session_connect_rest_router(mock_get_secret, temp_config_path):
    cfg = cli_config.AppConfig(
        routers={
            "lab": cli_config.RouterProfileConfig(
                host="192.168.88.1",
                username="admin",
                port=443,
                backend="rest",
            )
        }
    )
    cli_config.save_config(cfg, temp_config_path)
    session = ChatSession.create(temp_config_path)
    session.connect_router("lab")
    assert session.router_alias == "lab"
    assert session.router_client is not None
    mock_get_secret.assert_called_once_with("lab")


@patch("mika.cli.env_secrets.get_router_secret", return_value=None)
def test_session_connect_rest_without_password_raises(mock_get_secret, temp_config_path):
    cfg = cli_config.AppConfig(
        routers={
            "lab": cli_config.RouterProfileConfig(
                host="192.168.88.1",
                username="admin",
                backend="rest",
            )
        }
    )
    cli_config.save_config(cfg, temp_config_path)
    session = ChatSession.create(temp_config_path)
    with pytest.raises(SecretNotFoundError, match="No stored password"):
        session.connect_router("lab")


def test_session_require_router_raises_when_no_client(session_with_mock_router):
    session = session_with_mock_router
    with pytest.raises(NoActiveRouterError):
        session.require_router()


def test_session_require_router_returns_client(session_with_mock_router):
    session = session_with_mock_router
    session.connect_router("mock-router")
    client = session.require_router()
    assert client is not None


@patch("mika.cli.env_secrets.get_provider_secret", return_value="test-api-key")
def test_session_activate_gemini_provider(mock_get_secret, session_with_mock_router):
    session = session_with_mock_router
    session.activate_provider("gemini", "gemini-1.5-flash")
    assert session.provider is not None
    assert session.provider_name == "gemini"
    assert session.model_name == "gemini-1.5-flash"
    mock_get_secret.assert_called_once_with("gemini")


@patch("mika.cli.env_secrets.get_provider_secret", return_value=None)
def test_session_activate_provider_without_api_key_raises(mock_get_secret, session_with_mock_router):
    session = session_with_mock_router
    with pytest.raises(SecretNotFoundError, match="No stored API key"):
        session.activate_provider("gemini", "gemini-1.5-flash")


def test_session_activate_provider_with_explicit_key_skips_keyring(session_with_mock_router):
    session = session_with_mock_router
    with patch("mika.cli.env_secrets.get_provider_secret") as mock_get_secret:
        session.activate_provider("gemini", "gemini-2.5-flash", api_key="freshly-entered-key")
    mock_get_secret.assert_not_called()
    assert session.provider is not None
    assert session.provider_name == "gemini"
    assert session.model_name == "gemini-2.5-flash"


def test_session_activate_provider_caches_key_for_later_calls(session_with_mock_router):
    session = session_with_mock_router
    session.activate_provider("gemini", "gemini-2.5-flash", api_key="freshly-entered-key")

    with patch("mika.cli.env_secrets.get_provider_secret") as mock_get_secret:
        session.activate_provider("gemini", "gemini-2.5-pro")
    mock_get_secret.assert_not_called()
    assert session.model_name == "gemini-2.5-pro"


@patch(
    "mika.cli.env_secrets.get_provider_secret",
    side_effect=env_secrets.EnvFileError("permission denied"),
)
def test_session_activate_provider_env_file_error_without_cache_raises_clear_error(
    mock_get_secret, session_with_mock_router
):
    session = session_with_mock_router
    with pytest.raises(SecretNotFoundError, match="Could not read .env"):
        session.activate_provider("gemini", "gemini-1.5-flash")


def test_session_cached_provider_secret(session_with_mock_router):
    session = session_with_mock_router
    assert session.cached_provider_secret("gemini") is None
    session.activate_provider("gemini", "gemini-2.5-flash", api_key="freshly-entered-key")
    assert session.cached_provider_secret("gemini") == "freshly-entered-key"


def test_session_require_provider_raises_when_no_provider(session_with_mock_router):
    session = session_with_mock_router
    with pytest.raises(SecretNotFoundError):
        session.require_provider()


def test_session_add_history(session_with_mock_router):
    session = session_with_mock_router
    session.add_history("user", "hello")
    session.add_history("assistant", "hi")
    assert len(session.history) == 2
    assert session.history[0].role == "user"
    assert session.history[0].text == "hello"


def test_session_history_truncation(session_with_mock_router):
    session = session_with_mock_router
    for i in range(300):
        session.add_history("user", f"msg{i}")
    assert len(session.history) == 200


def test_session_persist_active_selection(session_with_mock_router, temp_config_path):
    session = session_with_mock_router
    session.router_alias = "mock-router"
    session.provider_name = "gemini"
    session.model_name = "gemini-1.5-flash"
    session.persist_active_selection()

    loaded = cli_config.load_config(temp_config_path)
    assert loaded.active_router == "mock-router"
    assert loaded.active_provider == "gemini"
    assert loaded.active_model == "gemini-1.5-flash"


def test_session_close(session_with_mock_router):
    session = session_with_mock_router
    session.close()
