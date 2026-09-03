"""
Regression test for run_repl()'s main loop resilience.

A bug inside any /slash command handler must not crash the whole REPL
with a raw traceback -- the natural-language path already recovers
from exceptions, and the slash-command path must behave the same way.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rich.console import Console

from mika.cli.repl import run_repl
from mika.cli.session import ChatSession


@pytest.mark.asyncio
async def test_broken_slash_command_does_not_crash_repl_loop(tmp_path):
    session = ChatSession.create(config_path=tmp_path / "config.toml", memory_db_path=tmp_path / "memory.db")
    console = Console(record=True)

    lines = iter(["/broken", "/exit"])

    async def fake_read_line(_prompt_session, default=""):
        return next(lines)

    async def fake_dispatch(line, _session, _console):
        if line == "/broken":
            raise RuntimeError("boom")
        from mika.cli.slash_commands import ExitRepl

        raise ExitRepl()

    with (
        patch("mika.cli.repl.read_line", fake_read_line),
        patch("mika.cli.repl.build_prompt_session", return_value=None),
        patch("mika.cli.repl.dispatch", fake_dispatch),
        patch("mika.cli.repl._print_startup_message"),
        patch("mika.cli.repl._print_startup_status"),
    ):
        await run_repl(session, console)

    output = console.export_text()
    assert "boom" in output
    assert "Session continues" in output
    assert "Goodbye" in output


@pytest.mark.asyncio
async def test_pending_draft_is_passed_to_read_line_and_consumed_once(tmp_path):
    """/rewind sets session.pending_draft so the next prompt is pre-filled
    with the rewound message's original text. The main loop must forward
    it as read_line's `default` exactly once, then clear it so it doesn't
    leak into subsequent prompts."""
    session = ChatSession.create(config_path=tmp_path / "config.toml", memory_db_path=tmp_path / "memory.db")
    session.pending_draft = "original request text"
    console = Console(record=True)

    seen_defaults = []
    lines = iter(["edited request", "/exit"])

    async def fake_read_line(_prompt_session, default=""):
        seen_defaults.append(default)
        return next(lines)

    async def fake_handle_chat_turn(_line, _session, _console):
        pass

    with (
        patch("mika.cli.repl.read_line", fake_read_line),
        patch("mika.cli.repl.build_prompt_session", return_value=None),
        patch("mika.cli.repl._handle_chat_turn", fake_handle_chat_turn),
        patch("mika.cli.repl._print_startup_message"),
        patch("mika.cli.repl._print_startup_status"),
    ):
        await run_repl(session, console)

    assert seen_defaults == ["original request text", ""]
    assert session.pending_draft is None
