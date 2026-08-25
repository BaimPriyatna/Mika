from rich.panel import Panel
from rich.text import Text
from mika.utils.printer.theme import console


def print_header(title: str, subtitle: str = None):
    title_text = Text(title.upper(), style="bold white")
    
    panel = Panel(
        title_text,
        subtitle=subtitle,
        subtitle_align="right",
        border_style="magenta",
        expand=True,
        padding=(1, 2)
    )
    console.print("")
    console.print(panel)
    console.print("")


def print_section(title: str):
    line_len = max(55 - len(title), 5)
    console.print(
        f"\n[border]───[/border] [bold white]{title}[/bold white] "
        f"[border]{'─' * line_len}[/border]"
    )
