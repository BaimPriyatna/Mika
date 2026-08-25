from __future__ import annotations

from prompt_toolkit.document import Document

from mika.cli.input import MikaCompleter


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
