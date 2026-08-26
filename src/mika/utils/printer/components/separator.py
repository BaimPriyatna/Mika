from rich.text import Text
from rich.markup import escape
from mika.utils.printer.theme import console, Symbols


def print_post_command():
    width = console.width or 80
    console.print()
    console.print(f"[border]{'─' * width}[/border]")
    console.print()


def print_section_header(label: str):
    label_upper = label.upper()
    pad = max(0, (console.width or 80) - len(label_upper) - 6)
    console.print(
        f"\n[border_accent]──[/border_accent] "
        f"[bold white]{escape(label_upper)}[/bold white] "
        f"[border]{'─' * pad}[/border]"
    )


def print_subsection(label: str):
    console.print(f"\n  [label]{Symbols.DIAMOND} {escape(label)}[/label]")


def print_rule(style: str = "border"):
    width = console.width or 80
    console.print(f"[{style}]{'─' * width}[/{style}]")
