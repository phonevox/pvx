import click
from rich.console import Console
from rich.table import Table

from pvx.interactive import theme

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


def pause(message):
    Console().print(message, style=theme.SEPARATOR_COLOR)
    click.pause("")


def breadcrumb(text):
    click.echo(f"? {text}")


def print_modules_table(rows):
    table = Table()
    for column in ("Módulo", "Instalado", "Disponível", "Status"):
        table.add_column(column)
    for row in rows:
        table.add_row(row["name"], row["installed_version"], row["latest_version"], row["status"])
    Console().print(table)
