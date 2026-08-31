from __future__ import annotations

from pathlib import Path

from unittest.mock import AsyncMock, Mock, patch

import pytest
from rich.console import Console

from mika.cli import slash_commands
from mika.cli.errors import NoActiveRouterError
from mika.cli.session import ChatSession, HistoryEntry


@pytest.fixture
def console():
    return Console(file=Mock(), force_terminal=False)


@pytest.fixture
def mock_session():
    session = Mock(spec=ChatSession)
    session.router_alias = None
    session.provider_name = None
    session.model_name = None
    session.history = []
    session.last_backup = None
    session.config = Mock(routers={})
    session.config_path = Path("/tmp/mock_config.toml")
    session.session_store = Mock()
    session.session_id = "current-session-id"
    return session


def test_is_slash_command():
    assert slash_commands.is_slash_command("/help")
    assert slash_commands.is_slash_command("  /router list")
    assert not slash_commands.is_slash_command("normal message")
    assert not slash_commands.is_slash_command("")


@pytest.mark.asyncio
async def test_dispatch_help(console, mock_session):
    await slash_commands.dispatch("/help", mock_session, console)


@pytest.mark.asyncio
async def test_dispatch_unknown_command(console, mock_session):
    await slash_commands.dispatch("/unknown", mock_session, console)


@pytest.mark.asyncio
async def test_dispatch_exit_raises(console, mock_session):
    with pytest.raises(slash_commands.ExitRepl):
        await slash_commands.dispatch("/exit", mock_session, console)


@pytest.mark.asyncio
async def test_dispatch_quit_is_unknown(console, mock_session):
    await slash_commands.dispatch("/quit", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_clear(console, mock_session):
    mock_session.history = [HistoryEntry("user", "test")]
    await slash_commands._cmd_clear("", mock_session, console)
    mock_session.start_new_session.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_history_no_store(console, mock_session):
    mock_session.session_store = None
    await slash_commands._cmd_history("", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_history_no_saved_sessions(console, mock_session):
    mock_session.session_store.list_routers_with_sessions.return_value = []
    await slash_commands._cmd_history("", mock_session, console)


def _router_group(router_alias, count):
    from mika.memory.sessions import RouterSessionGroup

    return RouterSessionGroup(router_alias=router_alias, session_count=count)


def _mock_question(return_value):
    """A fake questionary.Question-like object matching what wizard._ask()
    needs: .application.key_bindings.add(...) (sync, chained call) plus an
    async .ask_async()."""
    q = AsyncMock()
    q.ask_async = AsyncMock(return_value=return_value)
    q.application = Mock()
    q.application.key_bindings.add = Mock(return_value=Mock())
    return q


def _two_selects(router_return, session_return):
    """questionary.select is called twice by _cmd_history (router picker,
    then session picker) -- return a factory yielding one mock per call."""
    calls = iter([router_return, session_return])

    def _factory(*args, **kwargs):
        return _mock_question(next(calls))

    return _factory


@pytest.mark.asyncio
async def test_cmd_history_cancel_at_router_step(console, mock_session):
    mock_session.session_store.list_routers_with_sessions.return_value = [_router_group("lab", 1)]
    with patch("questionary.select", side_effect=_two_selects(None, "unused")):
        await slash_commands._cmd_history("", mock_session, console)
    mock_session.session_store.list_sessions.assert_not_called()
    mock_session.resume_session.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_history_cancel_at_session_step(console, mock_session):
    from mika.memory.sessions import SessionSummary

    mock_session.session_store.list_routers_with_sessions.return_value = [_router_group("lab", 1)]
    mock_session.session_store.list_sessions.return_value = [
        SessionSummary(
            id="current-session-id",
            title="fix vlan 10",
            started_at="2026-08-27T00:00:00",
            updated_at="2026-08-27T00:05:00",
            message_count=4,
            router_alias="lab",
        ),
    ]
    with patch("questionary.select", side_effect=_two_selects("lab", None)):
        await slash_commands._cmd_history("", mock_session, console)
    mock_session.resume_session.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_history_no_router_bucket_uses_sentinel_not_none(console, mock_session):
    """The '(no router)' group's value must not be confused with Esc/None."""
    from mika.memory.sessions import SessionSummary

    mock_session.session_store.list_routers_with_sessions.return_value = [_router_group(None, 1)]
    mock_session.session_store.list_sessions.return_value = [
        SessionSummary(
            id="current-session-id",
            title="no router yet",
            started_at="2026-08-27T00:00:00",
            updated_at="2026-08-27T00:05:00",
            message_count=1,
            router_alias=None,
        ),
    ]
    mock_session.history = [HistoryEntry("user", "no router yet")]

    with patch("questionary.select", side_effect=_two_selects(slash_commands._NO_ROUTER_SENTINEL, "current-session-id")):
        await slash_commands._cmd_history("", mock_session, console)

    mock_session.session_store.list_sessions.assert_called_once_with(router_alias=None)
    mock_session.resume_session.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_history_select_current_session_just_shows_transcript(console, mock_session):
    from mika.memory.sessions import SessionSummary

    mock_session.session_store.list_routers_with_sessions.return_value = [_router_group("lab", 1)]
    mock_session.session_store.list_sessions.return_value = [
        SessionSummary(
            id="current-session-id",
            title="fix vlan 10",
            started_at="2026-08-27T00:00:00",
            updated_at="2026-08-27T00:05:00",
            message_count=1,
            router_alias="lab",
        ),
    ]
    mock_session.history = [HistoryEntry("user", "fix vlan 10")]
    with patch("questionary.select", side_effect=_two_selects("lab", "current-session-id")):
        await slash_commands._cmd_history("", mock_session, console)
    mock_session.resume_session.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_history_select_other_session_switches(console, mock_session):
    from mika.memory.sessions import SessionSummary

    mock_session.session_store.list_routers_with_sessions.return_value = [_router_group("lab", 2)]
    mock_session.session_store.list_sessions.return_value = [
        SessionSummary(
            id="current-session-id",
            title="fix vlan 10",
            started_at="2026-08-27T00:00:00",
            updated_at="2026-08-27T00:05:00",
            message_count=1,
            router_alias="lab",
        ),
        SessionSummary(
            id="other-id",
            title="check firewall",
            started_at="2026-08-26T00:00:00",
            updated_at="2026-08-26T00:05:00",
            message_count=2,
            router_alias="lab",
        ),
    ]
    with patch("questionary.select", side_effect=_two_selects("lab", "other-id")):
        await slash_commands._cmd_history("", mock_session, console)
    mock_session.resume_session.assert_called_once_with("other-id")


@pytest.mark.asyncio
async def test_cmd_history_switch_not_found_error(console, mock_session):
    from mika.cli.errors import SessionNotFoundError
    from mika.memory.sessions import SessionSummary

    mock_session.session_store.list_routers_with_sessions.return_value = [_router_group("lab", 1)]
    mock_session.session_store.list_sessions.return_value = [
        SessionSummary(
            id="other-id",
            title="check firewall",
            started_at="2026-08-26T00:00:00",
            updated_at="2026-08-26T00:05:00",
            message_count=2,
            router_alias="lab",
        ),
    ]
    mock_session.resume_session.side_effect = SessionNotFoundError("no such session")
    with patch("questionary.select", side_effect=_two_selects("lab", "other-id")):
        await slash_commands._cmd_history("", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_history_router_removed_label(console, mock_session):
    mock_session.config.routers = {}  # "lab" no longer registered
    mock_session.session_store.list_routers_with_sessions.return_value = [_router_group("lab", 1)]
    mock_session.session_store.list_sessions.return_value = []
    with patch("questionary.select", side_effect=_two_selects("lab", None)) as mock_select:
        await slash_commands._cmd_history("", mock_session, console)
    router_call_kwargs = mock_select.call_args_list[0]
    labels = [c.title for c in router_call_kwargs.kwargs["choices"]]
    assert any("(router removed)" in label for label in labels)


@pytest.mark.asyncio
async def test_cmd_history_prints_conversation_transcript_not_table(console, mock_session):
    """Regression: /history used to dump a plain Role/Message Rich table
    after switching sessions, which didn't read like an actual resumed
    conversation. It should print each turn as a chat line instead."""
    from mika.memory.sessions import SessionSummary

    mock_session.session_store.list_routers_with_sessions.return_value = [_router_group("lab", 1)]
    mock_session.session_store.list_sessions.return_value = [
        SessionSummary(
            id="current-session-id",
            title="fix vlan 10",
            started_at="2026-08-27T00:00:00",
            updated_at="2026-08-27T00:05:00",
            message_count=2,
            router_alias="lab",
        ),
    ]
    mock_session.history = [
        HistoryEntry("user", "fix vlan 10"),
        HistoryEntry("assistant", "Sure, here's how to configure VLAN 10."),
    ]
    printed = []
    console.print = lambda *args, **kwargs: printed.append(str(args[0]) if args else "")

    with patch("questionary.select", side_effect=_two_selects("lab", "current-session-id")):
        await slash_commands._cmd_history("", mock_session, console)

    combined = "\n".join(printed)
    assert "fix vlan 10" in combined
    assert "Sure, here's how to configure VLAN 10." in combined
    assert "◆ Mika:" in combined
    assert "Conversation History" not in combined  # old table title must be gone


def test_truncate_label_short_text_unchanged():
    assert slash_commands.truncate_label("membuat vlan 10") == "membuat vlan 10"


def test_truncate_label_long_text_truncated_with_ellipsis():
    long_title = "membuat firewall rule untuk memblokir semua trafik dari luar"
    result = slash_commands.truncate_label(long_title, max_len=15)
    assert result == "membuat fire..."
    assert len(result) == 15


@pytest.mark.asyncio
async def test_cmd_model_no_arg_opens_selection_menu(console, mock_session):
    mock_session.config.models = []
    mock_session.activate_provider = Mock()
    mock_session.persist_active_selection = Mock()
    with patch(
        "mika.cli.slash_commands.wizard.select_model",
        new_callable=AsyncMock,
        return_value=("gemini", "gemini-1.5-pro"),
    ) as m:
        await slash_commands._cmd_model("", mock_session, console)
    m.assert_called_once_with(mock_session.config, session=mock_session)
    mock_session.activate_provider.assert_called_once_with("gemini", "gemini-1.5-pro")
    mock_session.persist_active_selection.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_model_no_arg_esc_cancels_silently(console, mock_session):
    mock_session.activate_provider = Mock()
    with patch("mika.cli.slash_commands.wizard.select_model", new_callable=AsyncMock, return_value=None):
        await slash_commands._cmd_model("", mock_session, console)
    mock_session.activate_provider.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_model_change(console, mock_session):
    mock_session.provider_name = "gemini"
    mock_session.model_name = "gemini-1.5-flash"
    mock_session.activate_provider = Mock()
    mock_session.persist_active_selection = Mock()
    await slash_commands._cmd_model("gemini-2.0-flash", mock_session, console)
    mock_session.activate_provider.assert_called_once_with("gemini", "gemini-2.0-flash")
    mock_session.persist_active_selection.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_router_list_empty(console, mock_session):
    mock_session.config.routers = {}
    await slash_commands._cmd_router("list", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_router_status_no_active(console, mock_session):
    await slash_commands._cmd_router("status", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_router_select(console, mock_session):
    mock_session.connect_router = Mock()
    mock_session.persist_active_selection = Mock()
    await slash_commands._cmd_router("select lab", mock_session, console)
    mock_session.connect_router.assert_called_once_with("lab")
    mock_session.persist_active_selection.assert_called_once()


@pytest.mark.asyncio
@patch("mika.cli.wizard.run_router_wizard", new_callable=AsyncMock)
@patch("mika.cli.config.save_config")
async def test_cmd_router_add(mock_save, mock_wizard, console, mock_session):
    from mika.cli.config import RouterProfileConfig
    from unittest.mock import AsyncMock

    mock_wizard.return_value = (
        "lab",
        RouterProfileConfig(host="192.168.88.1", username="admin", backend="rest"),
    )
    mock_session.connect_router = Mock()
    mock_session.persist_active_selection = Mock()
    mock_session.config_path = Mock()

    with patch("questionary.select", return_value=_mock_question("manual")):
        await slash_commands._cmd_router("add", mock_session, console)

    assert "lab" in mock_session.config.routers
    mock_session.connect_router.assert_called_once_with("lab")


@pytest.mark.asyncio
@patch("mika.cli.wizard.scan_and_select_router", new_callable=AsyncMock)
@patch("mika.cli.wizard.run_router_wizard", new_callable=AsyncMock)
@patch("mika.cli.config.save_config")
async def test_cmd_router_add_with_scan(mock_save, mock_wizard, mock_scan, console, mock_session):
    from mika.cli.config import RouterProfileConfig
    from mika.router.mndp import MndpDevice
    from unittest.mock import AsyncMock

    device = MndpDevice(mac_address="00:11:22:33:44:55", identity="office", ip_address="192.168.1.1")
    mock_scan.return_value = device
    mock_wizard.return_value = (
        "office",
        RouterProfileConfig(host="192.168.1.1", username="admin", backend="rest"),
    )
    mock_session.connect_router = Mock()
    mock_session.persist_active_selection = Mock()
    mock_session.config_path = Mock()

    with patch("questionary.select", return_value=_mock_question("scan")):
        await slash_commands._cmd_router("add", mock_session, console)

    mock_scan.assert_awaited_once()
    mock_wizard.assert_awaited_once_with(
        existing_aliases=[],
        discovered=device,
        session=mock_session,
    )
    assert "office" in mock_session.config.routers


@pytest.mark.asyncio
async def test_cmd_inspect_without_target_opens_selection_menu(console, mock_session):
    mock_session.require_router = Mock(return_value=Mock())
    with patch("mika.cli.slash_commands.wizard.select_inspect_target", new_callable=AsyncMock, return_value=None) as m:
        await slash_commands._cmd_inspect("", mock_session, console)
    m.assert_called_once()
    mock_session.require_router.assert_not_called()


@pytest.mark.asyncio
@patch("mika.cli.slash_commands.discover", new_callable=AsyncMock)
@patch("mika.cli.render.render_inspect")
async def test_cmd_inspect_with_target(mock_render, mock_discover, console, mock_session):
    mock_ctx = Mock()
    mock_discover.return_value = mock_ctx
    mock_session.require_router = Mock(return_value=Mock())
    await slash_commands._cmd_inspect("router", mock_session, console)
    mock_discover.assert_called_once()
    mock_render.assert_called_once_with(console, "router", mock_ctx)


@pytest.mark.asyncio
async def test_cmd_inspect_no_router_raises(console, mock_session):
    mock_session.require_router = Mock(side_effect=NoActiveRouterError("no router"))
    with pytest.raises(NoActiveRouterError):
        await slash_commands._cmd_inspect("router", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_status(console, mock_session):
    await slash_commands._cmd_status("", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_backup_no_backup(console, mock_session):
    mock_session.last_backup = None
    await slash_commands._cmd_backup("", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_backup_with_backup(console, mock_session):
    from datetime import datetime, timezone

    mock_backup = Mock()
    mock_backup.plan_id = "test-plan"
    mock_backup.created_at = datetime.now(timezone.utc)
    mock_session.last_backup = mock_backup
    await slash_commands._cmd_backup("", mock_session, console)


@pytest.mark.asyncio
@patch("mika.cli.config.save_config")
async def test_cmd_router_remove_with_arg(mock_save, console, mock_session):
    from mika.cli.config import RouterProfileConfig

    mock_session.config.routers = {
        "lab": RouterProfileConfig(host="192.168.88.1", username="admin", backend="rest"),
        "office": RouterProfileConfig(host="192.168.1.1", username="admin", backend="rest"),
    }
    mock_session.router_alias = "lab"
    mock_session.router_client = Mock()

    await slash_commands._cmd_router("remove lab", mock_session, console)

    assert "lab" not in mock_session.config.routers
    assert "office" in mock_session.config.routers
    assert mock_session.router_alias is None
    assert mock_session.router_client is None
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_router_remove_not_found(console, mock_session):
    from mika.cli.config import RouterProfileConfig

    mock_session.config.routers = {
        "office": RouterProfileConfig(host="192.168.1.1", username="admin", backend="rest"),
    }
    await slash_commands._cmd_router("remove non_existent", mock_session, console)
    assert "office" in mock_session.config.routers


@pytest.mark.asyncio
@patch("mika.cli.config.save_config")
async def test_cmd_router_remove_interactive(mock_save, console, mock_session):
    from mika.cli.config import RouterProfileConfig
    from unittest.mock import AsyncMock

    mock_session.config.routers = {
        "lab": RouterProfileConfig(host="192.168.88.1", username="admin", backend="rest"),
    }
    mock_session.router_alias = "lab"

    with patch("questionary.select", return_value=_mock_question("lab")):
        await slash_commands._cmd_router("remove", mock_session, console)

    assert "lab" not in mock_session.config.routers
    assert mock_session.router_alias is None
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_reset(console, mock_session):
    from mika.cli.config import RouterProfileConfig
    from unittest.mock import AsyncMock
    from pathlib import Path

    mock_session.config.routers = {
        "lab": RouterProfileConfig(host="192.168.88.1", username="admin", backend="rest"),
    }
    mock_session.config.models = []
    mock_session.router_alias = "lab"
    mock_session.provider_name = "gemini"
    mock_session.model_name = "gemini-1.5-flash"
    mock_session.config_path = Path("/tmp/dummy_config.toml")

    with patch("questionary.confirm", return_value=_mock_question(True)), patch("mika.cli.config.save_config"):
        await slash_commands._cmd_reset("", mock_session, console)

    assert len(mock_session.config.routers) == 0
    assert mock_session.router_alias is None
    assert mock_session.provider_name is None


def _pick(*values):
    """Sequential questionary mock: nth call to .ask_async() returns values[n]."""
    calls = iter(values)

    def _factory(*args, **kwargs):
        return _mock_question(next(calls))

    return _factory


@pytest.mark.asyncio
async def test_cmd_rewind_no_history(console, mock_session):
    mock_session.history = []
    await slash_commands._cmd_rewind("", mock_session, console)
    mock_session.rewind_to.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_rewind_no_rewindable_entries(console, mock_session):
    # History entries with message_id=None (e.g. never persisted) can't be
    # rewind targets.
    mock_session.history = [HistoryEntry("user", "hi", message_id=None)]
    await slash_commands._cmd_rewind("", mock_session, console)
    mock_session.rewind_to.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_rewind_cancel_at_picker(console, mock_session):
    mock_session.history = [HistoryEntry("user", "hi", message_id=1)]
    with patch("questionary.select", side_effect=_pick(None)):
        await slash_commands._cmd_rewind("", mock_session, console)
    mock_session.rewind_to.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_rewind_cancel_at_confirm(console, mock_session):
    mock_session.history = [HistoryEntry("user", "hi", message_id=1)]
    with (
        patch("questionary.select", side_effect=_pick(0)),
        patch("questionary.confirm", side_effect=_pick(False)),
    ):
        await slash_commands._cmd_rewind("", mock_session, console)
    mock_session.rewind_to.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_rewind_success(console, mock_session):
    from mika.cli.session import RewindResult

    mock_session.history = [HistoryEntry("user", "hi", message_id=1)]
    mock_session.rewind_to = AsyncMock(
        return_value=RewindResult(attempted=2, succeeded=2, stopped_early=False, errors=[])
    )
    with (
        patch("questionary.select", side_effect=_pick(0)),
        patch("questionary.confirm", side_effect=_pick(True)),
    ):
        await slash_commands._cmd_rewind("", mock_session, console)
    mock_session.rewind_to.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_cmd_rewind_nothing_to_undo(console, mock_session):
    from mika.cli.session import RewindResult

    mock_session.history = [HistoryEntry("user", "hi", message_id=1)]
    mock_session.rewind_to = AsyncMock(
        return_value=RewindResult(attempted=0, succeeded=0, stopped_early=False, errors=[])
    )
    with (
        patch("questionary.select", side_effect=_pick(0)),
        patch("questionary.confirm", side_effect=_pick(True)),
    ):
        await slash_commands._cmd_rewind("", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_rewind_stopped_early_reports_errors(console, mock_session):
    from mika.cli.session import RewindResult

    mock_session.history = [HistoryEntry("user", "hi", message_id=1)]
    mock_session.rewind_to = AsyncMock(
        return_value=RewindResult(
            attempted=2, succeeded=1, stopped_early=True, errors=["router rejected rollback"]
        )
    )
    with (
        patch("questionary.select", side_effect=_pick(0)),
        patch("questionary.confirm", side_effect=_pick(True)),
    ):
        await slash_commands._cmd_rewind("", mock_session, console)


@pytest.mark.asyncio
async def test_cmd_rewind_raises_rewind_error(console, mock_session):
    from mika.cli.errors import RewindError

    mock_session.history = [HistoryEntry("user", "hi", message_id=1)]
    mock_session.rewind_to = AsyncMock(side_effect=RewindError("cross-router range"))
    with (
        patch("questionary.select", side_effect=_pick(0)),
        patch("questionary.confirm", side_effect=_pick(True)),
    ):
        await slash_commands._cmd_rewind("", mock_session, console)
