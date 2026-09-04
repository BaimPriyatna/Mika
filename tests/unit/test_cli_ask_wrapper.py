from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest
import questionary
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mika.cli.wizard import _ask


async def _run_select_with_input(text: str, session=None):
    """Build a real questionary.select, feed it raw key input, and run it
    through _ask(). Returns whatever the prompt resolves to."""
    with create_pipe_input() as pipe_input:
        q = questionary.select(
            "pick one:",
            choices=["a", "b"],
            input=pipe_input,
            output=DummyOutput(),
        )
        pipe_input.send_text(text)
        return await _ask(q, session=session)


class TestEscapeCancels:
    @pytest.mark.asyncio
    async def test_select_escape_cancels(self):
        result = await _run_select_with_input("\x1b")  # ESC
        assert result is None

    @pytest.mark.asyncio
    async def test_select_enter_still_confirms(self):
        # No navigation, just Enter -- confirms the first (default) choice.
        result = await _run_select_with_input("\r")
        assert result == "a"

    @pytest.mark.asyncio
    async def test_confirm_escape_cancels(self):
        with create_pipe_input() as pipe_input:
            q = questionary.confirm("continue?", default=False, input=pipe_input, output=DummyOutput())
            pipe_input.send_text("\x1b")
            result = await _ask(q)
        assert result is None

    @pytest.mark.asyncio
    async def test_text_escape_cancels(self):
        with create_pipe_input() as pipe_input:
            q = questionary.text("name:", input=pipe_input, output=DummyOutput())
            pipe_input.send_text("\x1b")
            result = await _ask(q)
        assert result is None

    @pytest.mark.asyncio
    async def test_password_escape_cancels(self):
        with create_pipe_input() as pipe_input:
            q = questionary.password("key:", input=pipe_input, output=DummyOutput())
            pipe_input.send_text("\x1b")
            result = await _ask(q)
        assert result is None


class TestNoStandaloneHeaderPrinted:
    """_ask() used to print a standalone status header (router/provider/
    model) via console.print() right before opening the picker. That
    header always landed between the already-echoed command line and the
    picker itself -- never above the command, where a status bar
    belongs -- and its raw-ANSI rendering broke on terminals without VT
    processing enabled (e.g. plain Windows Command Prompt). It's been
    removed entirely: the status bar shown above the main "> " prompt
    while typing already covers this, correctly positioned, with no
    raw-ANSI codes involved."""

    @pytest.mark.asyncio
    async def test_ask_never_prints_anything_regardless_of_navigation(self):
        session = Mock(router_alias="office", provider_name="gemini", model_name="gemini-1.5-flash")
        with create_pipe_input() as pipe_input:
            q = questionary.select(
                "pick one:",
                choices=["a", "b", "c"],
                input=pipe_input,
                output=DummyOutput(),
            )
            pipe_input.send_text("\x1b[B\x1b[B\x1b[A\r")  # down, down, up, enter

            printed = []
            from mika.cli import wizard as wizard_module

            original_print = wizard_module.console.print
            wizard_module.console.print = lambda *a, **kw: printed.append(a[0] if a else "")
            try:
                await _ask(q, session=session)
            finally:
                wizard_module.console.print = original_print

        assert printed == []

    @pytest.mark.asyncio
    async def test_no_header_printed_when_session_is_none(self):
        with create_pipe_input() as pipe_input:
            q = questionary.select("pick one:", choices=["a"], input=pipe_input, output=DummyOutput())
            pipe_input.send_text("\r")

            printed = []
            from mika.cli import wizard as wizard_module

            original_print = wizard_module.console.print
            wizard_module.console.print = lambda *a, **kw: printed.append(a[0] if a else "")
            try:
                await _ask(q, session=None)
            finally:
                wizard_module.console.print = original_print

        assert printed == []
