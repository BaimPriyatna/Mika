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
def temp_memory_db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "memory.db"


@pytest.fixture
def session_with_mock_router(temp_config_path, temp_memory_db_path):
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
    session = ChatSession.create(temp_config_path, temp_memory_db_path)
    return session


def test_session_create_empty_config(temp_config_path, temp_memory_db_path):
    temp_config_path.unlink()
    session = ChatSession.create(temp_config_path, temp_memory_db_path)
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


def test_session_create_stale_active_router_does_not_crash(temp_config_path, temp_memory_db_path):
    """active_router pointing at a profile that no longer exists must not
    crash startup — it should fall back to "no active router" instead."""
    cfg = cli_config.AppConfig(
        routers={},
        active_router="ghost-router",
    )
    cli_config.save_config(cfg, temp_config_path)

    session = ChatSession.create(temp_config_path, temp_memory_db_path)

    assert session.router_alias is None
    assert session.config.active_router is None


@patch("mika.cli.env_secrets.get_router_secret", return_value="password123")
def test_session_connect_rest_router(mock_get_secret, temp_config_path, temp_memory_db_path):
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
    session = ChatSession.create(temp_config_path, temp_memory_db_path)
    session.connect_router("lab")
    assert session.router_alias == "lab"
    assert session.router_client is not None
    mock_get_secret.assert_called_once_with("lab")


@patch("mika.cli.env_secrets.get_router_secret", return_value=None)
def test_session_connect_rest_without_password_raises(mock_get_secret, temp_config_path, temp_memory_db_path):
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
    session = ChatSession.create(temp_config_path, temp_memory_db_path)
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


def test_add_history_persists_to_session_store(session_with_mock_router):
    session = session_with_mock_router
    session.add_history("user", "hello router")

    messages = session.session_store.get_messages(session.session_id)
    assert [(m.role, m.text) for m in messages] == [("user", "hello router")]


def test_recent_context_turns_respects_limit(session_with_mock_router):
    session = session_with_mock_router
    for i in range(5):
        session.add_history("user", f"msg{i}")

    turns = session.recent_context_turns(limit=2)
    assert [t.text for t in turns] == ["msg3", "msg4"]


def test_recent_context_turns_zero_limit_returns_empty(session_with_mock_router):
    session = session_with_mock_router
    session.add_history("user", "hello")
    assert session.recent_context_turns(limit=0) == []


def test_start_new_session_clears_history_and_gets_new_id(session_with_mock_router):
    session = session_with_mock_router
    old_id = session.session_id
    session.add_history("user", "old session message")

    session.start_new_session()

    assert session.session_id != old_id
    assert session.history == []
    # old session's message is still persisted, just not active anymore
    old_messages = session.session_store.get_messages(old_id)
    assert [m.text for m in old_messages] == ["old session message"]


@pytest.mark.asyncio
async def test_start_new_session_preserves_router_and_provider_state(session_with_mock_router):
    """Regression / documentation of investigated behavior: /clear (which
    calls start_new_session()) must only reset the conversation, never the
    active router connection, provider, or model. A user reporting
    'router: none' after /clear was seeing accurate state (no router had
    ever been selected in that run) -- not a bug in start_new_session()
    clobbering an already-active router."""
    session = session_with_mock_router
    session.connect_router("mock-router")
    session.activate_provider("gemini", "gemini-1.5-flash", api_key="test-key")
    router_client_before = session.router_client

    session.start_new_session()

    assert session.router_alias == "mock-router"
    assert session.router_client is router_client_before
    assert session.provider_name == "gemini"
    assert session.model_name == "gemini-1.5-flash"
    assert session.provider is not None
    # only the conversation actually resets
    assert session.history == []


def test_start_new_session_default_tags_with_current_router_alias(session_with_mock_router):
    session = session_with_mock_router
    session.router_alias = "mock-router"

    session.start_new_session()
    session.add_history("user", "hello")  # sessions need >=1 message to be listed

    groups = {g.router_alias: g.session_count for g in session.session_store.list_routers_with_sessions()}
    assert "mock-router" in groups


def test_start_new_session_explicit_router_alias_overrides_current(session_with_mock_router):
    """Regression: callers switching to a *different* router (e.g.
    /router select) must be able to tag the new session with the *target*
    router, not whatever session.router_alias still holds (the old router,
    since connect_router() hasn't run yet at that point)."""
    session = session_with_mock_router
    session.router_alias = "old-router"  # simulates state before connect_router() runs

    session.start_new_session(router_alias="new-router")
    session.add_history("user", "hello")  # sessions need >=1 message to be listed

    groups = {g.router_alias: g.session_count for g in session.session_store.list_routers_with_sessions()}
    assert "new-router" in groups
    assert "old-router" not in groups


def test_start_new_session_explicit_none_creates_no_router_session(session_with_mock_router):
    session = session_with_mock_router
    session.router_alias = "some-router"

    session.start_new_session(router_alias=None)
    session.add_history("user", "hello")  # sessions need >=1 message to be listed

    groups = {g.router_alias: g.session_count for g in session.session_store.list_routers_with_sessions()}
    assert None in groups


def test_resume_session_loads_past_messages(session_with_mock_router):
    session = session_with_mock_router
    session.add_history("user", "first message")
    session.add_history("assistant", "intent=inspect_router")
    old_id = session.session_id

    session.start_new_session()
    assert session.history == []

    count = session.resume_session(old_id)

    assert count == 2
    assert [(h.role, h.text) for h in session.history] == [
        ("user", "first message"),
        ("assistant", "intent=inspect_router"),
    ]
    assert session.session_id == old_id
    # new messages now append to the resumed session
    session.add_history("user", "continuing")
    assert session.session_store.get_messages(old_id)[-1].text == "continuing"


def test_resume_session_unknown_id_raises(session_with_mock_router):
    from mika.cli.errors import SessionNotFoundError

    session = session_with_mock_router
    with pytest.raises(SessionNotFoundError):
        session.resume_session("does-not-exist")


def test_resume_session_different_router_drops_stale_connection(session_with_mock_router):
    """Resuming a session scoped to a *different* router than the one
    currently connected must drop the live connection rather than leave
    router_client silently pointing at the wrong router."""
    session = session_with_mock_router
    session.connect_router("mock-router")
    session.add_history("user", "hello from mock-router")
    old_id = session.session_id

    session.start_new_session(router_alias="other-router")
    session.add_history("user", "hello from other-router")

    session.resume_session(old_id, router_alias="mock-router")

    assert session.router_alias == "mock-router"
    # router_client wasn't touched because it's already the right router.
    assert session.router_client is not None


def test_resume_session_switching_to_different_router_clears_client(session_with_mock_router):
    """If the session being resumed belongs to a router other than the one
    currently connected, the stale connection must be dropped so no router
    action can silently run against the wrong device."""
    session = session_with_mock_router
    session.connect_router("mock-router")
    old_id = session.session_id
    session.add_history("user", "hello")

    # Simulate having since connected to a different router.
    session.router_alias = "some-other-router"

    session.resume_session(old_id, router_alias="mock-router")

    assert session.router_alias == "mock-router"
    assert session.router_client is None


def test_resume_session_without_router_alias_arg_leaves_connection_untouched(session_with_mock_router):
    """Callers that don't pass router_alias (default _UNSET) keep the old
    behavior: router_alias/router_client are never touched by resume."""
    session = session_with_mock_router
    session.connect_router("mock-router")
    old_id = session.session_id
    session.add_history("user", "hello")
    session.start_new_session()

    session.resume_session(old_id)

    assert session.router_alias == "mock-router"
    assert session.router_client is not None


@pytest.mark.asyncio
async def test_rewind_to_no_backups_still_trims_history(session_with_mock_router):
    """When there's nothing to undo on the router (no plan backups after
    the anchor), rewind_to() must still trim history to that point --
    matching the /rewind 'no backups' edge case."""
    session = session_with_mock_router
    session.connect_router("mock-router")
    session.add_history("user", "first")
    anchor_id = session.history[-1].message_id
    session.add_history("assistant", "reply")
    session.add_history("user", "second")

    result = await session.rewind_to(anchor_id)

    assert result.attempted == 0
    assert [h.text for h in session.history] == ["first"]
    assert session.session_store.get_messages(session.session_id)[-1].text == "first"


@pytest.mark.asyncio
async def test_rewind_to_message_id_zero_trims_everything(session_with_mock_router):
    """message_id=0 is the 'rewind to the very start' anchor -- every
    history entry (real ids start at 1) must be trimmed away."""
    session = session_with_mock_router
    session.connect_router("mock-router")
    session.add_history("user", "first")
    session.add_history("assistant", "reply")

    result = await session.rewind_to(0)

    assert result.attempted == 0
    assert session.history == []
