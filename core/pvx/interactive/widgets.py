import click
from rich.console import Console

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
    Console().print(BANNER, style=theme.current_accent_color())
