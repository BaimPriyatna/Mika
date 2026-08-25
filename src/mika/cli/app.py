"""
MIKA CLI Entry Point.

Main entry point for command-line arguments, environment setup, and
launching either one-off commands or the interactive REPL session.
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from mika.cli.repl import run_repl
from mika.cli.session import ChatSession

app = typer.Typer(
    name="mika",
    help="AI-assisted MikroTik RouterOS configuration, troubleshooting, and monitoring.",
    invoke_without_command=True,
)

console = Console()

from mika.cli.commands import memory

app.add_typer(memory.app, name="memory")


def _start_chat() -> None:
    session = ChatSession.create()
    try:
        asyncio.run(run_repl(session, console))
    finally:
        session.close()


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _start_chat()


@app.command()
def chat() -> None:
    _start_chat()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
