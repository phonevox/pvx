import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from pvx.interactive import theme

QMARK_COLOR = "#5f819d"  # cor default do "?" do questionary (token "qmark")

BANNER = """\
██████   ██   ██   █████   ███   █  ███████  ██   ██   █████   ██   ██
██   ██  ██   ██  ██   ██  ████  █  ██       ██   ██  ██   ██   ██ ██
██████   ███████  ██   ██  ██ ██ █  █████    ██   ██  ██   ██    ███
██       ██   ██  ██   ██  ██  ███  ██        ██ ██   ██   ██   ██ ██
██       ██   ██   █████   ██   ██  ███████    ███     █████   ██   ██\
"""


def clear():
    click.clear()


def spinner(message):
    return Console().status(message, spinner_style=theme.current_accent_color())


def banner():
    Console().print(BANNER + "\n", style=theme.current_accent_color())


def pause():
    # highlight=False -- o ReprHighlighter automático do rich colore
    # padrões tipo "..." sozinho (achado testando: "pressione enter pra
    # continuar..." saía com as reticências amarelas, sem querer).
    Console().print("pressione enter pra continuar...", style=theme.SEPARATOR_COLOR, highlight=False)
    click.pause("")


def breadcrumb(text):
    line = Text()
    line.append("? ", style=QMARK_COLOR)
    line.append(text, style="bold")
    Console().print(line)


def message(text):
    click.echo()
    click.echo(text)
    click.echo()


def print_modules_table(rows):
    table = Table()
    for column in ("Módulo", "Instalado", "Disponível", "Status"):
        table.add_column(column)
    for row in rows:
        table.add_row(row["name"], row["installed_version"], row["latest_version"], row["status"])
    Console().print(table)
