import collections
import sys
import time

import click
from rich.console import Console, Group
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
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


class _ElapsedColumn(TimeElapsedColumn):
    # TimeElapsedColumn nativa mostra "0:05:02" (hora sem zero à esquerda) --
    # HH:MM:SS fixo fica mais fácil de escanear numa lista de etapas.
    def render(self, task):
        elapsed = task.finished_time if task.finished else task.elapsed
        if elapsed is None:
            return Text("--:--:--", style="progress.elapsed")
        hours, remainder = divmod(max(0, int(elapsed)), 3600)
        minutes, seconds = divmod(remainder, 60)
        return Text(f"{hours:02d}:{minutes:02d}:{seconds:02d}", style="progress.elapsed")


class Step:
    # como spinner(), mas com timer ao vivo (rich.progress já resolve isso via
    # _ElapsedColumn -- sem reinventar contador com thread própria) e expõe
    # .elapsed pra quem chama (ver widgets.success() depois do with).
    def __init__(self, message):
        self._message = message
        self._progress = Progress(
            SpinnerColumn(style=theme.current_accent_color()),
            TextColumn("{task.description}"),
            _ElapsedColumn(),
            transient=True,  # apaga a linha do spinner ao sair -- só sobra a sequência de sucesso/falha.
        )
        self.elapsed = None

    def __enter__(self):
        self._start = time.monotonic()
        self._progress.start()
        self._progress.add_task(self._message, total=None)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.elapsed = time.monotonic() - self._start
        self._progress.stop()
        return False


def step(message):
    return Step(message)


class StepWithLog:
    # como Step, mas com as últimas `tail` linhas de saída em cinza embaixo do spinner
    # (docker-build-style) -- reaproveita o mesmo Progress (spinner + timer) de Step,
    # só que renderizado dentro de um Live próprio junto com o rastro de linhas, em vez
    # de deixar o Progress gerenciar seu próprio Live sozinho.
    def __init__(self, message, tail=5):
        self._lines = collections.deque(maxlen=tail)
        self._progress = Progress(
            SpinnerColumn(style=theme.current_accent_color()),
            TextColumn("{task.description}"),
            _ElapsedColumn(),
        )
        self._progress.add_task(message, total=None)
        self._live = Live(self._render(), console=Console(), refresh_per_second=8, transient=True)
        self.elapsed = None

    def _render(self):
        tail_text = Text("\n".join(f"  {line}" for line in self._lines), style=theme.SEPARATOR_COLOR)
        return Group(self._progress, tail_text)

    def feed(self, line):
        self._lines.append(line)
        self._live.update(self._render())

    def __enter__(self):
        self._start = time.monotonic()
        self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.elapsed = time.monotonic() - self._start
        self._live.__exit__(exc_type, exc, tb)
        return False


def step_with_log(message, tail=5):
    return StepWithLog(message, tail)


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


def _answer_line(msg, text):
    line = Text()
    line.append("? ", style=QMARK_COLOR)
    line.append(f"{msg} ", style="bold")
    line.append(text, style=f"{theme.current_accent_color()} bold")
    return line


def checkbox_answer(msg, selected):
    # substitui o "done (N selections)" default do questionary.checkbox() -- não dá pra
    # customizar isso via parâmetro da lib, então ask_checkbox() apaga a linha padrão
    # (erase_when_done=True) e chama isto pra imprimir a nossa por cima, no mesmo estilo
    # qmark+pergunta+resposta do breadcrumb().
    text = ", ".join(str(v) for v in selected) if selected else "nenhum"
    Console().print(_answer_line(msg, text), highlight=False)


def select_answer(msg, title):
    # mesmo motivo do checkbox_answer -- ask_select() usa um controle próprio
    # (viewport com scroll, ver inputs.py), erase_when_done=True apaga o
    # widget inteiro ao confirmar, isto imprime o resumo de uma linha só.
    Console().print(_answer_line(msg, str(title) if title is not None else "nenhum"), highlight=False)


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


def crash(traceback_text):
    # catch global de exceção não tratada -- precisa saltar aos olhos, nunca
    # se misturar com o resto da saída do terminal.
    line = Text()
    line.append(traceback_text, style="red")
    Console().print(line, highlight=False)


def state(text, ok):
    # pra reportar um FATO/estado (ex.: resultado de uma consulta), não o
    # resultado de uma ação -- diferente de success()/failed(), sem rótulo
    # "sucesso!"/"falha!" (usar isso numa consulta não faz sentido, não
    # houve ação nenhuma pra "ter sucesso" ou "falhar").
    line = Text()
    line.append(text, style="bold green" if ok else "bold red")
    Console().print(line, highlight=False)


_CHECK_RESULT_STYLE = {
    "ok": ("✓", "bold green"),
    "warn": ("!", "bold yellow"),  # reprova mas não bloqueia (ex.: RAM baixa no preflight)
    "error": ("✗", "bold red"),
}


def check_result(text, level):
    icon, style = _CHECK_RESULT_STYLE[level]
    line = Text()
    line.append(f"{icon} {text}", style=style)
    Console().print(line, highlight=False)


def _status_style(status, accent):
    return {
        "atualizado": "bold green",
        "atualização disponível": "bold yellow",
        "à frente do registry": f"bold {accent}",
        "local": f"bold {accent}",
        "disponível": theme.SEPARATOR_COLOR,
    }.get(status, "")


def print_modules_table(rows):
    accent = theme.current_accent_color()
    table = Table()
    for column in ("Módulo", "Instalado", "Disponível", "Status"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            row["name"], row["installed_version"], row["latest_version"],
            Text(row["status"], style=_status_style(row["status"], accent)),
        )
    Console().print(table)
