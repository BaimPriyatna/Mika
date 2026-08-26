from __future__ import annotations

import os
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.application import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import has_completions
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.styles import Style

from mika.cli.session import ChatSession

_HISTORY_PATH = Path.home() / ".config" / "mika" / "chat_history"

_COMMANDS = {
    "/help": ("Show list of available commands", {}),
    "/exit": ("Exit MIKA REPL", {}),
    "/clear": ("Clear screen and session history", {}),
    "/history": ("Show conversation history", {}),
    "/model": ("Select or switch active AI model", {}),
    "/provider": ("Configure AI provider", {}),
    "/router": (
        "Manage router connections",
        {
            "add": "Add new router",
            "select": "Select active router",
            "list": "List all routers",
            "remove": "Remove router",
            "status": "Show active router",
        },
    ),
    "/inspect": (
        "Inspect router state (read-only)",
        {
            "router": "Router summary",
            "interfaces": "Show interfaces",
            "addresses": "Show IP addresses",
            "routes": "Show route table",
            "firewall": "Show firewall rules",
            "dhcp": "Show DHCP configuration",
            "hotspot": "Show hotspot configuration",
        },
    ),
    "/status": ("Show system status", {}),
    "/backup": ("Manage router backups", {}),
    "/reset": ("Reset all configuration and secrets to defaults", {}),
}


class MikaCompleter(Completer):

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()

        if not text.startswith("/"):
            return

        parts = text.split()
        has_space = " " in text

        if has_space and parts:
            cmd = parts[0]
            _, subcmds = _COMMANDS.get(cmd, ("", {}))
            if not subcmds:
                return

            # Case 1: "/router " (space after command, no subcommand typed yet)
            if len(parts) == 1 and text.endswith(" "):
                for subcmd, hint in subcmds.items():
                    yield Completion(
                        text=subcmd,
                        start_position=0,
                        display=subcmd,
                        display_meta=hint,
                    )
                return

            # Case 2: "/router rem" (typing a subcommand)
            if len(parts) == 2 and not text.endswith(" "):
                prefix = parts[1]
                for subcmd, hint in subcmds.items():
                    if subcmd.startswith(prefix):
                        yield Completion(
                            text=subcmd,
                            start_position=-len(prefix),
                            display=subcmd,
                            display_meta=hint,
                        )
                return

            # Case 3: Subcommand already entered (e.g. "/router remove " or "/router remove lab")
            # Do NOT suggest unrelated subcommands here
            return

        prefix = parts[0] if parts else "/"
        for cmd, (desc, _) in _COMMANDS.items():
            if cmd.startswith(prefix):
                yield Completion(
                    text=cmd,
                    start_position=-len(prefix),
                    display=cmd,
                    display_meta=desc,
                )


_STYLE = Style.from_dict(
    {
        "prompt.arrow": "bold #06b6d4",
        "prompt.line": "#27272a",
        "completion-menu": "bg:#141414 fg:#6b7280",
        "completion-menu.completion": "bg:#141414 fg:#9ca3af",
        "completion-menu.meta.completion": "bg:#141414 fg:#4b5563",
        "completion-menu.completion.current": "bg:#1e1e2e fg:#e2e8f0 bold",
        "completion-menu.meta.completion.current": "bg:#1e1e2e fg:#a78bfa",
        "completion-menu.border": "#2d2d2d",
        "scrollbar.background": "bg:#1a1a1a",
        "scrollbar.button": "bg:#4b5563",
    }
)


def _make_history() -> History:
    try:
        _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        return FileHistory(str(_HISTORY_PATH))
    except OSError:
        return InMemoryHistory()


def build_status_bar(session: ChatSession) -> str:
    router_info = session.router_alias or "none"
    model_info = (
        f"{session.provider_name}:{session.model_name}"
        if session.provider_name and session.model_name
        else "none"
    )
    return f"MIKA | router: {router_info} | model: {model_info}"


def build_header_status(session: ChatSession) -> str:
    if session.router_alias:
        router_part = f"\033[38;2;34;197;94m{session.router_alias}\033[0m"
    else:
        router_part = "\033[38;2;248;113;113mnone\033[0m"

    if session.provider_name and session.model_name:
        model_part = f"\033[38;2;34;197;94m{session.provider_name}:{session.model_name}\033[0m"
    else:
        model_part = "\033[38;2;248;113;113mnone\033[0m"

    brand = "\033[38;2;192;132;252m◈ MIKA\033[0m"
    sep = "\033[38;2;61;61;61m│\033[0m"
    
    return f" {brand}  {sep}  router: {router_part}  {sep}  model: {model_part} "


def build_prompt_message(session: ChatSession | None = None) -> callable:
    try:
        from rich import get_console
        width = get_console().width or 80
    except Exception:
        width = 80

    line = "─" * width

    def _get_prompt():
        if _is_navigating():
            status = f'<style fg="#4b5563"> ↑/↓ select  ·  Tab/Enter apply  ·  Esc cancel </style>'
        else:
            if session and session.router_alias:
                router_part = f'<style fg="#22c55e">{session.router_alias}</style>'
            else:
                router_part = '<style fg="#f87171">none</style>'

            if session and session.provider_name and session.model_name:
                model_part = f'<style fg="#22c55e">{session.provider_name}:{session.model_name}</style>'
            else:
                model_part = '<style fg="#f87171">none</style>'

            brand = '<style fg="#c084fc">◈ MIKA</style>'
            sep = '<style fg="#3d3d3d">│</style>'
            status = f' {brand}  {sep}  router: {router_part}  {sep}  model: {model_part} '

        return HTML(
            f'{status}\n'
            f'<prompt.line>{line}</prompt.line>\n'
            f'<prompt.arrow><b>></b></prompt.arrow> '
        )

    return _get_prompt


def cleanup_scroll_history(raw_input: str) -> None:
    prompt_line = f"\033[38;2;6;182;212m\033[1m>\033[0m {raw_input}"
    cleanup = f"\033[3A\033[0J{prompt_line}\n"
    try:
        os.write(1, cleanup.encode())
    except OSError:
        pass


def _is_navigating() -> bool:
    try:
        buffer = get_app().current_buffer
    except Exception:
        return False
    if buffer.complete_state is not None:
        return True
    return buffer.document.text_before_cursor.lstrip().startswith("/")


def build_prompt_session(session: ChatSession | None = None) -> PromptSession:
    return PromptSession(
        message=build_prompt_message(session),
        history=_make_history(),
        auto_suggest=AutoSuggestFromHistory(),
        completer=MikaCompleter(),
        style=_STYLE,
        complete_while_typing=True,
        complete_in_thread=True,
    )


async def read_line(session: PromptSession) -> str:
    return await session.prompt_async()
