from __future__ import annotations

from unittest.mock import Mock

import pytest
from rich.console import Console

from mika.utils import printer as printer_module
from mika.utils.printer import (
    log_error,
    log_info,
    log_step,
    log_success,
    log_tree,
    log_warning,
    status_spinner,
)
from mika.utils.printer.components.panel import print_header, print_section
from mika.utils.printer.components.separator import (
    print_section_header,
    print_subsection,
)


@pytest.fixture
def patched_console(monkeypatch):
    """Route the shared printer console to an in-memory, non-terminal console
    so markup rendering still runs (and would still raise MarkupError on bad
    input) without writing to real stdout."""
    console = Console(file=Mock(), force_terminal=False)
    monkeypatch.setattr(printer_module, "console", console)
    monkeypatch.setattr("mika.utils.printer.components.panel.console", console)
    monkeypatch.setattr("mika.utils.printer.components.separator.console", console)
    return console


# A message containing a RouterOS-style path, which previously crashed
# rendering with rich.errors.MarkupError because it looks like an unmatched
# closing markup tag.
_DANGEROUS_MESSAGE = "Check the rule under [/ip firewall filter] before proceeding."


@pytest.mark.parametrize(
    "log_fn",
    [log_info, log_success, log_warning, log_error, log_step],
)
def test_log_functions_do_not_crash_on_markup_like_text(patched_console, log_fn):
    log_fn(_DANGEROUS_MESSAGE)


def test_log_tree_does_not_crash_on_markup_like_text(patched_console):
    log_tree(_DANGEROUS_MESSAGE)


def test_status_spinner_does_not_crash_on_markup_like_text(patched_console):
    with status_spinner(_DANGEROUS_MESSAGE):
        pass


def test_print_header_does_not_crash_on_markup_like_subtitle(patched_console):
    print_header("Title", subtitle=_DANGEROUS_MESSAGE)


def test_print_section_does_not_crash_on_markup_like_title(patched_console):
    print_section(_DANGEROUS_MESSAGE)


def test_print_section_header_does_not_crash_on_markup_like_label(patched_console):
    print_section_header(_DANGEROUS_MESSAGE)


def test_print_subsection_does_not_crash_on_markup_like_label(patched_console):
    print_subsection(_DANGEROUS_MESSAGE)
