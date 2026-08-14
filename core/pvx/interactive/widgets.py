import click
from rich.console import Console

from pvx.interactive import theme


def clear():
    click.clear()


def spinner(message):
    return Console().status(message, spinner_style=theme.current_accent_color())
