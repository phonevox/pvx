import sys

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
    # sys.argv com mais de 1 item = pvx foi lançado com argumentos (CLI
    # direta, ver __main__.py) -- nunca pausa aí, o shell já devolve o
    # prompt sozinho. Só pausa quando o processo inteiro está em modo
    # interativo (`pvx` sem args). Checar sys.stdin.isatty() daria falso
    # positivo: um terminal real também é tty na CLI direta, não só no menu.
    if len(sys.argv) > 1:
        return
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


_SUCCESS_LABEL = "✓ sucesso!"
_FAILED_LABEL = "✗ falha!"
_OUTCOME_LABEL_WIDTH = max(len(_SUCCESS_LABEL), len(_FAILED_LABEL))


def _print_outcome(label, style, detail):
    line = Text()
    line.append(label.ljust(_OUTCOME_LABEL_WIDTH) if detail else label, style=style)
    if detail:
        line.append(f" {detail}")
    Console().print(line, highlight=False)


def success(detail=None):
    _print_outcome(_SUCCESS_LABEL, "bold green", detail)


def failed(detail=None):
    _print_outcome(_FAILED_LABEL, "bold red", detail)


def print_modules_table(rows):
    table = Table()
    for column in ("Módulo", "Instalado", "Disponível", "Status"):
        table.add_column(column)
    for row in rows:
        table.add_row(row["name"], row["installed_version"], row["latest_version"], row["status"])
    Console().print(table)
