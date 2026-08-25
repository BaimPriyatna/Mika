import contextlib
from mika.utils.printer.theme import console, Symbols
from mika.utils.printer.components.panel import print_header, print_section
from mika.utils.printer.components.separator import (
    print_post_command,
    print_section_header,
    print_subsection,
    print_rule
)


def log_info(message: str):
    console.print(f"[info]{Symbols.INFO}[/info]  {message}")


def log_success(message: str):
    console.print(f"[success]{Symbols.SUCCESS}[/success]  {message}")


def log_warning(message: str):
    console.print(f"[warning]{Symbols.WARNING}[/warning]  {message}")


def log_error(message: str):
    console.print(f"[error]{Symbols.ERROR}[/error]  {message}")


def log_step(message: str):
    console.print(f"[step]{Symbols.STEP}[/step]  {message}")


def log_tree(message: str, is_last: bool = False, level: int = 1):
    prefix = f"{Symbols.PIPE}" * (level - 1) if level > 1 else ""
    connector = Symbols.ELBOW if is_last else Symbols.TEE
    console.print(f"[muted]{prefix}{connector}[/muted] {message}")


@contextlib.contextmanager
def status_spinner(message: str):
    with console.status(
        f"[cyan]{message}[/cyan]",
        spinner="bouncingBar",
        spinner_style="bold #c084fc",
    ) as status:
        yield status


info = log_info
success = log_success
warning = log_warning
error = log_error
header = print_header
subheader = print_subsection
rule = print_rule
blank = lambda: console.print("")


__all__ = [
    "console",
    "Symbols",
    "print_header",
    "print_section",
    "print_section_header",
    "print_subsection",
    "print_rule",
    "print_post_command",
    "log_info",
    "log_success",
    "log_warning",
    "log_error",
    "log_step",
    "log_tree",
    "status_spinner",
    "info",
    "success",
    "warning",
    "error",
    "header",
    "subheader",
    "rule",
    "blank",
]
