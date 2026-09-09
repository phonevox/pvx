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


def _outcomes():
    # os 3 estados de _print_outcome, na ordem success/failed/warning -- usado
    # só pra calcular alinhamento entre eles (ver _verbose_prefix/_v2_prefix
    # abaixo), nunca pra decidir QUAL deles imprimir.
    return (
        ("✓", "sucesso", "bold green"),
        ("✗", "falha", "bold red"),
        (theme.current_symbols()["warning"], "aviso", "bold yellow"),
    )


def _verbose_prefix(symbol, category):
    return f"{symbol} {category}!"


def _verbose_v2_prefix(symbol, category):
    return f"[{symbol}] {category}"


def _fallback_text(category, detail):
    # formatos sem um slot de categoria dedicado (ultra-minimal/modern/...)
    # caem pra categoria como texto quando a chamada não passou detail (ex.:
    # success() sem argumento) -- igual "verbose" mostra só o prefixo sozinho.
    return detail if detail is not None else category


def _line_verbose(symbol, category, style, detail):
    prefix = _verbose_prefix(symbol, category)
    width = max(len(_verbose_prefix(s, c)) for s, c, _ in _outcomes())
    line = _styled(prefix.ljust(width) if detail else prefix, style)
    if detail:
        line.append(f" {detail}")
    return line


def _line_verbose_v2(symbol, category, style, detail):
    prefix = _verbose_v2_prefix(symbol, category)
    width = max(len(_verbose_v2_prefix(s, c)) for s, c, _ in _outcomes())
    line = _styled(prefix.ljust(width) if detail else prefix, style)
    if detail:
        line.append(f" {detail}")
    return line


def _line_verbose_v2_full_color(symbol, category, style, detail):
    prefix = _verbose_v2_prefix(symbol, category)
    width = max(len(_verbose_v2_prefix(s, c)) for s, c, _ in _outcomes())
    text = prefix.ljust(width) if detail else prefix
    if detail:
        text += f" {detail}"
    return _styled(text, style)


def _line_minimal(symbol, category, style, detail):
    line = Text()
    line.append(category.upper(), style=style)
    if detail:
        line.append(f" {detail}")
    return line


def _line_ultra_minimal(symbol, category, style, detail):
    line = Text()
    line.append(symbol, style=style)
    line.append(f" {_fallback_text(category, detail)}")
    return line


def _line_modern(symbol, category, style, detail):
    line = Text()
    line.append("[")
    line.append(symbol, style=style)
    line.append(f"] {_fallback_text(category, detail)}")
    return line


def _line_modern_colored_brackets(symbol, category, style, detail):
    line = Text()
    line.append(f"[{symbol}]", style=style)
    line.append(f" {_fallback_text(category, detail)}")
    return line


def _line_modern_full_color(symbol, category, style, detail):
    return _styled(f"[{symbol}] {_fallback_text(category, detail)}", style)


_LINE_BUILDERS = {
    "verbose": _line_verbose,
    "verbose-v2": _line_verbose_v2,
    "verbose-v2-full-color": _line_verbose_v2_full_color,
    "minimal": _line_minimal,
    "ultra-minimal": _line_ultra_minimal,
    "modern": _line_modern,
    "modern-colored-brackets": _line_modern_colored_brackets,
    "modern-full-color": _line_modern_full_color,
}


def preview_outcome_line(format_name, symbol="✓", category="sucesso", detail=None):
    # usado por pvx.interactive.screens.theme_settings pra montar o preview
    # (on-hover) de cada preset de "pvx > tema > formato" -- plain, sem cor,
    # já que a description do questionary não renderiza estilo.
    builder = _LINE_BUILDERS.get(format_name, _line_modern)
    return builder(symbol, category, "", detail).plain


def _print_outcome(symbol, category, style, detail):
    builder = _LINE_BUILDERS.get(theme.current_line_format(), _line_modern)
    Console().print(builder(symbol, category, style, detail), highlight=False)


def success(detail=None):
    _print_outcome("✓", "sucesso", "bold green", detail)


def failed(detail=None):
    _print_outcome("✗", "falha", "bold red", detail)


def warning(detail=None):
    _print_outcome(theme.current_symbols()["warning"], "aviso", "bold yellow", detail)


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
    "ok": ("✓", "ok", "bold green"),
    # reprova mas não bloqueia (ex.: RAM baixa no preflight) -- mesmo símbolo
    # temável de warning() (SYMBOL_SETS), resolvido abaixo por nível.
    "warn": (None, "aviso", "bold yellow"),
    "error": ("✗", "erro", "bold red"),
}


def check_result(text, level):
    # mesmo pipeline de success()/failed()/warning() -- respeita o "formato"
    # do tema (achado ao vivo: ficava com layout fixo, alheio ao resto).
    fixed_symbol, category, style = _CHECK_RESULT_STYLE[level]
    symbol = fixed_symbol or theme.current_symbols()["warning"]
    _print_outcome(symbol, category, style, text)


_TITLE_WIDTH = 70


def _styled(text, style):
    line = Text()
    line.append(text, style=style)
    return line


def title(text):
    accent = theme.current_accent_color()
    char = theme.current_border_char()
    bar = _styled(char * _TITLE_WIDTH, accent)
    console = Console()
    console.print(bar, highlight=False)
    console.print(_styled(text.center(_TITLE_WIDTH), f"bold {accent}"), highlight=False)
    console.print(bar, highlight=False)


def section(text):
    accent = theme.current_accent_color()
    marker = theme.current_symbols()["section"]
    Console().print(_styled(f"{marker} {text}", f"bold {accent}"), highlight=False)


def description(text):
    Console().print(_styled(f"  {text}", theme.SEPARATOR_COLOR), highlight=False)


def item(text, comment=None):
    accent = theme.current_accent_color()
    symbol = theme.current_symbols()["item"]
    line = Text()
    line.append(f"  {symbol} ", style=accent)
    line.append(text)
    if comment:
        line.append(f"  # {comment}", style=theme.SEPARATOR_COLOR)
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
