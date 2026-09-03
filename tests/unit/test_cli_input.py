from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from prompt_toolkit.document import Document

from mika.cli.input import _COMMANDS, MikaCompleter, build_prompt_session, read_line


def _get_completions(text: str) -> list[str]:
    completer = MikaCompleter()
    doc = Document(text, cursor_position=len(text))
    return [c.text for c in completer.get_completions(doc, None)]


def test_completer_main_command_prefix():
    completions = _get_completions("/rou")
    assert "/router" in completions


def test_completer_subcommand_space_shows_all_subcommands():
    completions = _get_completions("/router ")
    assert "add" in completions
    assert "select" in completions
    assert "list" in completions
    assert "remove" in completions
    assert "status" in completions


def test_completer_subcommand_prefix_filters():
    completions = _get_completions("/router rem")
    assert completions == ["remove"]


def test_completer_subcommand_already_finished_does_not_suggest_subcommands():
    completions = _get_completions("/router remove ")
    assert completions == []


def test_completer_subcommand_with_arg_does_not_suggest_subcommands():
    completions = _get_completions("/router remove lab")
    assert completions == []


def test_completer_add_subcommand_finished_does_not_resuggest_all_subcommands():
    """Regression: typing '/router add' then a space must not resuggest the
    full subcommand list — this exact scenario is what the threaded-completer
    race (see test_prompt_session_disables_completion_threading) could
    surface, even though the completer's own logic here is already correct
    in isolation."""
    completions = _get_completions("/router add ")
    assert completions == []


def test_prompt_session_disables_completion_threading():
    """MikaCompleter does pure in-memory dict/string lookups with no I/O, so
    it must run synchronously (complete_in_thread=False). Running it in a
    background thread (complete_in_thread=True) introduces scheduling
    latency that lets prompt_toolkit's own completion throttling
    (`_only_one_at_a_time`) silently drop completion requests for
    intermediate keystrokes while an earlier, slower request is still in
    flight. When that earlier request finally resolves, it can apply stale
    completions (e.g. the full '/router ' subcommand list reappearing even
    though the user has already typed '/router add ') to the buffer. Keeping
    completion synchronous keeps the in-flight window negligible."""
    session = build_prompt_session()
    assert session.complete_in_thread is False
    assert session.complete_while_typing is True


def test_every_slash_command_has_a_completer_entry():
    """Regression: _HANDLERS (slash_commands.py) and _COMMANDS (input.py's
    completer) are two independently-maintained registries with no shared
    source of truth. Both /rewind and /troubleshoot were added to
    _HANDLERS but silently missing from _COMMANDS, so they worked as
    commands but never showed up in tab-completion. This test fails
    immediately (instead of only being noticed by a human) if a future
    command is added to one but not the other."""
    from mika.cli.slash_commands import _HANDLERS

    handler_commands = set(_HANDLERS.keys())
    completer_commands = set(_COMMANDS.keys())
    missing_from_completer = handler_commands - completer_commands
    assert not missing_from_completer, (
        f"Commands registered in _HANDLERS but missing from input._COMMANDS "
        f"(won't tab-complete): {sorted(missing_from_completer)}"
    )


@pytest.mark.asyncio
async def test_read_line_passes_default_to_prompt_async():
    """/rewind's draft auto-fill relies on read_line forwarding `default`
    straight into PromptSession.prompt_async so the text is pre-filled
    and editable, not just a placeholder."""
    prompt_session = Mock()
    prompt_session.prompt_async = AsyncMock(return_value="edited text")

    result = await read_line(prompt_session, default="original draft")

    prompt_session.prompt_async.assert_called_once_with(default="original draft")
    assert result == "edited text"


@pytest.mark.asyncio
async def test_read_line_defaults_to_empty_string():
    prompt_session = Mock()
    prompt_session.prompt_async = AsyncMock(return_value="typed")

    await read_line(prompt_session)

    prompt_session.prompt_async.assert_called_once_with(default="")
