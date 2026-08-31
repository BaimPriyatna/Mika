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


class TestHeaderPrintedOnce:
    @pytest.mark.asyncio
    async def test_header_printed_exactly_once_before_prompt(self):
        """Regression: an earlier attempt printed the header from inside a
        render/key-binding callback, which reprinted it on every arrow-key
        press. The header must be printed exactly once, before the prompt
        starts -- never tied to navigation events."""
        session = Mock(router_alias="office", provider_name="gemini", model_name="gemini-1.5-flash")
        with create_pipe_input() as pipe_input:
            q = questionary.select(
                "pick one:",
                choices=["a", "b", "c"],
                input=pipe_input,
                output=DummyOutput(),
            )
            # Simulate a user navigating up/down several times before
            # confirming -- the header must still only appear once.
            pipe_input.send_text("\x1b[B\x1b[B\x1b[A\r")  # down, down, up, enter

            printed = []
            from mika.cli import wizard as wizard_module

            original_print = wizard_module.console.print
            wizard_module.console.print = lambda *a, **kw: printed.append(a[0] if a else "")
            try:
                await _ask(q, session=session)
            finally:
                wizard_module.console.print = original_print

        assert len(printed) == 1

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
