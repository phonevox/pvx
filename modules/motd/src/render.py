from io import StringIO

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# limiar ascendente: o último cujo valor <= percent "vence" -- 80 cai em
# amarelo, 90 em vermelho, o resto fica verde.
_THRESHOLDS = ((0, "green"), (80, "yellow"), (90, "red"))

# recordings/logs/dialer raramente chegam perto de 80-90% do disco total
# (o threshold acima), mesmo quando já são "muita coisa" em termos
# absolutos -- 1GB/5GB é o critério de "isso já merece atenção".
_SIZE_THRESHOLDS = ((0, "green"), (1 * 1024**3, "yellow"), (5 * 1024**3, "red"))

_HEADER = (
    "Bem-vindo de volta! Este servidor é gerenciado pela "
    "[bold magenta]PHONEVOX GROUP TECHNOLOGY[/bold magenta] -- https://phonevox.com\n"
    "Precisa de suporte? Fala com a gente em [cyan]suporte@phonevox.com.br[/cyan]\n"
)

# pedido ao vivo: empilhado (não lado a lado), com todo painel na mesma
# largura do "system" -- evita caixas de tamanhos desencontrados na coluna.
_PANEL_WIDTH = 92


def _threshold_color(value, thresholds):
    color = thresholds[0][1]
    for threshold, c in thresholds:
        if value >= threshold:
            color = c
    return color


def bar_color(percent, thresholds=_THRESHOLDS):
    return _threshold_color(percent, thresholds)


def size_color(num_bytes, thresholds=_SIZE_THRESHOLDS):
    return _threshold_color(num_bytes, thresholds)


def human_size(num_bytes):
    value = float(num_bytes)
    for unit in ("B", "K", "M"):
        if value < 1024:
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}G"


def render_bar(percent, width=30, color=None):
    percent = max(0, min(100, percent))
    filled = round(percent * width / 100)
    empty = width - filled
    color = color or bar_color(percent)
    return (
        f"[{color}]{'#' * filled}[/{color}]"
        f"[bright_black]{'-' * empty}[/bright_black] {percent:>3.0f}%"
    )


def bar_with_size(percent, num_bytes):
    if percent is None or num_bytes is None:
        return "N/A"
    return f"{render_bar(percent, color=size_color(num_bytes))} ({human_size(num_bytes)})"


# maior rótulo do health panel ("Autobackup") -- todo mundo alinha o ":"
# na mesma coluna usando essa largura (achado ao vivo: rótulos de tamanhos
# diferentes caindo em colunas diferentes).
_LABEL_WIDTH = len("Autobackup")


def daemon_line(name, status):
    label = f"{name:<{_LABEL_WIDTH}}"
    if not status["installed"]:
        return f"{label}: [yellow]not available[/yellow]"
    if status["running"]:
        return f"{label}: [green]online[/green]"
    return f"{label}: [red]offline[/red]"


def autobackup_line(status):
    label = f"{'Autobackup':<{_LABEL_WIDTH}}"
    if status is None:
        return f"{label}: [yellow]não configurado[/yellow]"
    return (
        f"{label}: [green]{status['username']}[/green] "
        f"(cron {status['cron_hour']}:{status['cron_minute']})"
    )


def _kv_table(rows):
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="left", style="bold cyan", no_wrap=True)
    table.add_column()
    for label, value in rows:
        table.add_row(label, Text.from_markup(value))
    return table


def _panel(title, renderable):
    return Panel(
        renderable, title=f"[bold yellow]{title}[/bold yellow]", title_align="left",
        border_style="grey50", width=_PANEL_WIDTH,
    )


def _system_panel(data):
    load1, load5, load15 = data["load_average"]
    rows = [
        ("Date", f"{data['server_date']} | {data['timezone']}"),
        ("CPU", f"{render_bar(data['cpu_percent'])} | load {load1},{load5},{load15}"),
        ("RAM", f"{render_bar(data['ram_percent'])} | swap {data['swap_percent']:.0f}%"),
        ("Disk", f"{render_bar(data['disk_percent'])} | {data['disk_used_gb']}/{data['disk_total_gb']}G"),
        ("Uptime", data["uptime"]),
        ("Host", f"{data['hostname']} | {data['open_sessions']} session(s)"),
        ("OS", f"{data['os_pretty_name']} | {data['machine_id']}"),
        ("IPs", ", ".join(data["ips"]) or "N/A"),
    ]
    return _panel("system", _kv_table(rows))


def _health_panel(data):
    # asterisk/mariadb só entram aqui se estiverem instalados -- sem sentido
    # monitorar um serviço que nem existe no servidor.
    lines = []
    if data["asterisk"]["installed"]:
        lines.append(daemon_line("asterisk", data["asterisk"]))
    if data["mariadb"]["installed"]:
        lines.append(daemon_line("mariadb", data["mariadb"]))
    lines.append(autobackup_line(data.get("autobackup")))
    return _panel("health", Text.from_markup("\n".join(lines)))


def _asterisk_panel(details):
    active_calls = details.get("active_calls")
    rows = [
        ("Version", details.get("version") or "N/A"),
        ("Active Calls", str(active_calls) if active_calls is not None else "N/A"),
        ("Recordings", bar_with_size(details.get("recordings_percent"), details.get("recordings_bytes"))),
        ("Logs", bar_with_size(details.get("logs_percent"), details.get("logs_bytes"))),
        ("Dialer Logs", bar_with_size(details.get("dialer_percent"), details.get("dialer_bytes"))),
    ]
    return _panel("asterisk", _kv_table(rows))


def build_banner(data):
    sections = [_system_panel(data), _health_panel(data)]

    if data["asterisk"]["installed"] and data.get("asterisk_details"):
        sections.append(_asterisk_panel(data["asterisk_details"]))

    return Group(Text.from_markup(_HEADER), *sections)


def render_to_text(renderable, width=100):
    console = Console(record=True, width=width, file=StringIO())
    console.print(renderable)
    return console.export_text()
